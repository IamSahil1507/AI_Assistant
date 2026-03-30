import json
import time
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional

import re
import requests
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from tools.auto_runner import execute_instructions
from tools import self_improve
from tools import assistant_state

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "ollama_proxy.json"
MEMORY_PATH = Path(__file__).resolve().parents[1] / "data" / "awarenet_memory.json"
DEBUG_LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "awarenet_proxy_debug.log"


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "listen_host": "127.0.0.1",
        "listen_port": 11435,
        "awarenet_base_url": "http://127.0.0.1:8000",
        "model_id": "awarenet:v1",
        "model_name": "awarenet:v1",
    }


def _load_memory() -> Dict[str, Any]:
    if MEMORY_PATH.exists():
        try:
            return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "preferences": {},
        "phrase_map": {},
        "history": [],
        "conversation": [],
        "intent": {},
        "project": {},
    }


def _save_memory(memory: Dict[str, Any]) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(memory, indent=2), encoding="utf-8")


def _log_debug(event: str, payload: Dict[str, Any]) -> None:
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": _now(),
            "event": event,
            "payload": payload,
        }
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except Exception:
        return


def _summarize_messages(messages: Any) -> list[Dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    summary: list[Dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        content_type = type(content).__name__
        length = 0
        if isinstance(content, str):
            length = len(content)
        elif isinstance(content, list):
            length = len(content)
        elif isinstance(content, dict):
            length = len(content)
        summary.append({"role": role, "content_type": content_type, "length": length})
    return summary


def _remember_phrase(memory: Dict[str, Any], phrase: str, result: str) -> None:
    if not phrase or not result:
        return
    if _is_wrapped_request(phrase):
        return
    phrase_key = TIMESTAMP_PREFIX.sub("", phrase).strip().lower()
    if not phrase_key:
        return
    phrase_map = memory.setdefault("phrase_map", {})
    previous = phrase_map.get(phrase_key)
    phrase_map[phrase_key] = result
    history = memory.setdefault("history", [])
    history.append({"ts": _now(), "phrase": phrase_key, "result": result[:500]})
    if len(history) > 200:
        del history[:-200]
    if previous != result:
        self_improve.note_learning(
            f'Learned mapping for "{phrase_key}"',
            "Faster response next time without LLM delay.",
        )


def _append_conversation(memory: Dict[str, Any], role: str, content: str) -> None:
    if not content:
        return
    convo = memory.setdefault("conversation", [])
    cleaned = content.strip()
    if len(cleaned) > 2000:
        cleaned = cleaned[:2000]
    convo.append({"role": role, "content": cleaned, "ts": _now()})
    if len(convo) > 220:
        del convo[:-220]


def _get_recent_conversation(memory: Dict[str, Any], limit: int = 200) -> list:
    convo = memory.get("conversation") or []
    recent = convo[-limit:]
    cleaned = []
    for item in recent:
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            cleaned.append({"role": role, "content": content})
    return cleaned


def _learn_preferences(memory: Dict[str, Any], text: str) -> None:
    lowered = text.lower()
    prefs = memory.setdefault("preferences", {})
    if "default chrome account" in lowered or "default chrome profile" in lowered:
        prefs["chrome_profile"] = "Default"
        self_improve.note_learning(
            "Preferred Chrome profile set to Default",
            "Gmail and Chrome actions will target your default profile automatically.",
        )
    match = CHROME_PROFILE_HINT.search(text)
    if match:
        profile = match.group(1).strip()
        if profile:
            prefs["chrome_profile"] = profile
            self_improve.note_learning(
                f"Preferred Chrome profile set to {profile}",
                "Gmail and Chrome actions will target your chosen profile.",
            )


def _apply_preference_hints(text: str, memory: Dict[str, Any]) -> str:
    if not text:
        return text
    prefs = memory.get("preferences") or {}
    chrome_profile = str(prefs.get("chrome_profile") or "").strip()
    lowered = text.lower()
    if chrome_profile and ("chrome" in lowered or "gmail" in lowered or "mail.google.com" in lowered):
        if "profile" not in lowered and "default account" not in lowered and "default profile" not in lowered:
            return text + f" (profile: {chrome_profile})"
    return text


def _record_assistant(memory: Dict[str, Any], content: str) -> None:
    if not content:
        return
    _append_conversation(memory, "assistant", content)
    _save_memory(memory)


def _lookup_phrase(memory: Dict[str, Any], phrase: str) -> str:
    if _is_wrapped_request(phrase):
        return ""
    phrase_key = TIMESTAMP_PREFIX.sub("", phrase).strip().lower()
    if not phrase_key:
        return ""
    phrase_map = memory.get("phrase_map") or {}
    return str(phrase_map.get(phrase_key) or "")


def _now() -> int:
    return int(time.time())


app = FastAPI()
config = load_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://excel-addin.gptforwork.com",
        "https://dashboard.gptforwork.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GATEWAY_MARKERS = (
    "openclaw-control-ui",
    "Direct gateway chat session",
    "Main Session",
)

TIMESTAMP_PREFIX = re.compile(r"^\[[^\]]+\]\s*")
MODEL_TAG_PREFIX = re.compile(r"^(awarenet|ollama-proxy|assistant|system):", re.IGNORECASE)
USER_LINE_PREFIX = re.compile(r"^(user|user request|user prompt)\s*[:\-]", re.IGNORECASE)
USER_PREFIX = re.compile(r"^(user|you)\s*[:\-]\s*", re.IGNORECASE)
USERREQUEST_BLOCK = re.compile(r"<userrequest>\s*(.*?)\s*</userrequest>", re.IGNORECASE | re.DOTALL)
REQUEST_MARKERS = (
    "my request for codex:",
    "my request for copilot:",
    "my request for github copilot:",
    "user request:",
    "user prompt:",
)
WRAPPED_MARKERS = (
    "context from my ide setup",
    "<context>",
    "</context>",
    "<editorcontext>",
    "</editorcontext>",
    "<userrequest>",
    "</userrequest>",
    "active file:",
    "open tabs:",
)
CONTEXT_MARKER = "context from my ide setup"
CONFIRM_PROMPT = "this action may be sensitive. reply with 'confirm' to proceed."

RISKY_PATTERNS = re.compile(
    r"\b(delete|remove|rm|rmdir|format|wipe|shutdown|reboot|restart|install|uninstall|regedit|registry|powershell|cmd\.exe|admin|elevated|sudo|send email|send mail|submit|purchase|pay|transfer)\b",
    re.IGNORECASE,
)

EMAIL_INTENT = re.compile(r"\b(email|mail|gmail|compose|send email|send mail)\b", re.IGNORECASE)
WEBAPP_INTENT = re.compile(r"\b(webapp|web app|website|frontend)\b", re.IGNORECASE)
DATE_RANGE = re.compile(r"(\d{1,2}[-/](\d{1,2})[-/](\d{4}))", re.IGNORECASE)
PATH_HINT = re.compile(r"([a-zA-Z]:[\\/][^\s]+)")
CHROME_PROFILE_HINT = re.compile(r"profile\\s*[:=]?\\s*([\\w\\s-]+)", re.IGNORECASE)
EMAIL_DRAFT_HINT = re.compile(r"\b(draft|compose|do not send|don'?t send|no send|save as draft)\b", re.IGNORECASE)
CONFIRM_REPLY = re.compile(
    r"^(confirm|confirmed|i confirm|i confirmed|i was confirm|i already confirmed|"
    r"yes|y|ok|okay|sure|please proceed|proceed|go ahead|do it|do it now|"
    r"please do|please do it)$",
    re.IGNORECASE,
)
PROJECT_INTENT = re.compile(
    r"\b(analyze|analyse|overview|summarize|summary|inspect)\b.*\b(project|repo|codebase|workspace)\b",
    re.IGNORECASE,
)
DETAIL_INTENT = re.compile(r"\b(detail|detailed|full|complete|in[- ]depth|deep|expanded)\b", re.IGNORECASE)
FOLLOWUP_HINT = re.compile(r"\b(more|continue|expand|elaborate|again|next|full|complete|detail|detailed)\b", re.IGNORECASE)
SKILL_INTENT = re.compile(r"\b(skills\.sh|npx\s+skills|install\s+skill|find\s+skill|add\s+skill)\b", re.IGNORECASE)
TASK_CREATE_INTENT = re.compile(r"\b(task|todo|to do|remind me)\b", re.IGNORECASE)
TASK_LIST_INTENT = re.compile(r"\b(list|show|view)\s+(tasks|todos)\b", re.IGNORECASE)
AMBIGUOUS_SHORT = re.compile(r"^(yes|ok|okay|sure|continue|more|details?|full|complete|again|next)\b", re.IGNORECASE)

PENDING_TTL_SECONDS = 600
PENDING_REQUEST: Dict[str, Any] = {"text": "", "ts": 0}
INTENT_TTL_SECONDS = 7200
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "logs",
    "data",
    "backup",
}
MAX_SCAN_FILES = 5000
MAX_DETAIL_FILE_BYTES = 2_000_000
MAX_ROUTE_SCAN_BYTES = 200_000
MAX_ROUTE_COUNT = 30
MAX_HOTSPOTS = 10
BINARY_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
}
SECRET_NAME_HINTS = (
    ".env",
    ".pem",
    ".key",
    "secret",
    "secrets",
    "token",
    "apikey",
    "api_key",
    "password",
)
INTENT_LABELS = {
    "project_overview": "project overview",
    "project_detail": "project detail",
    "email_draft": "email draft",
    "webapp": "web app draft",
    "skill_request": "skills lookup",
}


def _strip_user_prefix(text: str) -> str:
    return USER_PREFIX.sub("", text).strip()


def _is_wrapped_request(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in REQUEST_MARKERS):
        return True
    if any(marker in lowered for marker in WRAPPED_MARKERS):
        return True
    return False


def _extract_request_tail(text: str) -> str:
    lowered = text.lower()
    for marker in REQUEST_MARKERS:
        idx = lowered.rfind(marker)
        if idx != -1:
            return text[idx + len(marker):].strip()
    return text


def _extract_user_request(text: str) -> str:
    if not text:
        return ""
    matches = USERREQUEST_BLOCK.findall(text)
    if matches:
        for match in reversed(matches):
            cleaned = str(match).strip()
            if cleaned:
                return cleaned
    lowered = text.lower()
    if any(marker in lowered for marker in REQUEST_MARKERS):
        return _extract_request_tail(text)
    return ""


def _parse_vscode_context(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    active_file = None
    tabs: list[str] = []
    in_tabs = False
    for line in lines:
        lower = line.lower()
        if lower.startswith("active file"):
            _, _, value = line.partition(":")
            active_file = value.strip() or None
            in_tabs = False
            continue
        if lower.startswith("open tabs"):
            in_tabs = True
            continue
        if in_tabs and line.startswith("-"):
            tabs.append(line.lstrip("-").strip())
            continue
        if in_tabs and not line.startswith("-"):
            in_tabs = False
    payload = {}
    if active_file:
        payload["active_file"] = active_file
    if tabs:
        payload["open_tabs"] = tabs[:30]
    return payload


def _maybe_record_vscode_context(text: str) -> None:
    payload = _parse_vscode_context(text)
    if payload:
        assistant_state.record_vscode_context(payload)


def _assistant_context_message() -> Optional[Dict[str, str]]:
    summary = assistant_state.summary()
    if not summary:
        return None
    vscode_state = assistant_state.get_state().get("vscode", {})
    active_file = None
    last = vscode_state.get("last") if isinstance(vscode_state, dict) else None
    if isinstance(last, dict):
        payload = last.get("payload") or {}
        if isinstance(payload, dict):
            active_file = payload.get("active_file")
    lines = [
        "Assistant context:",
        f"tasks_pending={summary.get('tasks_pending')}, tasks_completed={summary.get('tasks_completed')}",
        f"action_logs={summary.get('action_log_count')}, notes={summary.get('notes_count')}",
    ]
    if active_file:
        lines.append(f"vscode_active_file={active_file}")
    return {"role": "system", "content": "\n".join(lines)}


def _extract_task_description(text: str) -> str:
    lowered = text.lower()
    for marker in ("task:", "todo:", "to do:"):
        if marker in lowered:
            _, _, tail = text.partition(marker)
            return tail.strip()
    if "remind me to" in lowered:
        _, _, tail = text.partition("remind me to")
        return tail.strip()
    if "add task" in lowered:
        _, _, tail = text.partition("add task")
        return tail.strip()
    return ""


def _infer_workspace_root(path_text: str) -> Optional[Path]:
    if not path_text:
        return None
    candidate = Path(path_text)
    if candidate.is_file():
        candidate = candidate.parent
    roots_to_check = [candidate] + list(candidate.parents)
    for root in roots_to_check:
        if (root / ".git").exists():
            return root
        if (root / "pyproject.toml").exists() or (root / "package.json").exists():
            return root
        if (root / "requirements.txt").exists() or (root / "openclaw.json").exists():
            return root
    parts = candidate.parts
    if len(parts) >= 2 and parts[0].endswith("\\"):
        return Path(parts[0]) / parts[1]
    return candidate


def _intent_recent(ts: int, ttl: int = INTENT_TTL_SECONDS) -> bool:
    if not ts:
        return False
    return (_now() - int(ts)) <= ttl


def _get_last_intent(memory: Dict[str, Any]) -> tuple[str, int]:
    intent = memory.get("intent") or {}
    name = str(intent.get("last") or "").strip()
    ts = int(intent.get("last_ts") or 0)
    if not name:
        return "", 0
    return name, ts


def _record_intent(memory: Dict[str, Any], intent: str) -> None:
    if not intent:
        return
    store = memory.setdefault("intent", {})
    store["last"] = intent
    store["last_ts"] = _now()


def _get_last_project_root(memory: Dict[str, Any]) -> Optional[Path]:
    project = memory.get("project") or {}
    root_text = str(project.get("last_root") or "").strip()
    if not root_text:
        return None
    return Path(root_text)


def _record_project_root(memory: Dict[str, Any], root: Path) -> None:
    if not root:
        return
    project = memory.setdefault("project", {})
    project["last_root"] = str(root)
    project["last_ts"] = _now()


def _infer_intent(clean_user: str, memory: Dict[str, Any]) -> tuple[Optional[str], str, str]:
    if not clean_user:
        return None, "low", "empty"
    if PROJECT_INTENT.search(clean_user) and DETAIL_INTENT.search(clean_user):
        return "project_detail", "high", "project+detail"
    if PROJECT_INTENT.search(clean_user):
        return "project_overview", "high", "project"
    if EMAIL_INTENT.search(clean_user):
        return "email_draft", "high", "email"
    if WEBAPP_INTENT.search(clean_user):
        return "webapp", "high", "webapp"
    if TASK_LIST_INTENT.search(clean_user):
        return "task_list", "high", "task_list"
    if TASK_CREATE_INTENT.search(clean_user):
        return "task_create", "high", "task_create"
    if SKILL_INTENT.search(clean_user):
        return "skill_request", "high", "skills"
    last_intent, last_ts = _get_last_intent(memory)
    if DETAIL_INTENT.search(clean_user) and last_intent in ("project_overview", "project_detail") and _intent_recent(last_ts):
        return "project_detail", "medium", "detail_followup"
    if FOLLOWUP_HINT.search(clean_user) and last_intent and _intent_recent(last_ts):
        return last_intent, "medium", "followup"
    return None, "low", "none"


def _resolve_project_root(messages: Any, memory: Dict[str, Any], prefer_memory: bool = False) -> Path:
    root = _extract_workspace_root(messages)
    mem_root = _get_last_project_root(memory)
    if prefer_memory and mem_root is not None:
        root = mem_root
    if mem_root is not None and not root.exists() and mem_root.exists():
        root = mem_root
    return root


def _followup_prompt(intent: str) -> str:
    label = INTENT_LABELS.get(intent, "that")
    return f"Quick check — do you want me to continue with the last {label}, or do something else?"


def _extract_workspace_root(messages: Any) -> Path:
    if isinstance(messages, list):
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            if msg.get("role") != "user":
                continue
            content = msg.get("content")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, dict):
                text = str(content.get("text") or "")
            elif isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict):
                        parts.append(str(part.get("text") or ""))
                text = "\n".join(parts)
            if not text:
                continue
            match = re.search(r"(?:^|\n)\s*(?:cwd|Cwd)\s*[:=]\s*([A-Za-z]:[^\n]+)", text)
            if match:
                root = _infer_workspace_root(match.group(1).strip())
                if root:
                    return root
            match = re.search(r"current file is\s*([A-Za-z]:[^\n]+)", text, re.IGNORECASE)
            if match:
                root = _infer_workspace_root(match.group(1).strip())
                if root:
                    return root
            match = PATH_HINT.search(text)
            if match:
                root = _infer_workspace_root(match.group(1).strip())
                if root:
                    return root
    return Path(__file__).resolve().parents[1]


def _iter_project_files(root: Path):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            count += 1
            if count > MAX_SCAN_FILES:
                return
            yield Path(dirpath) / name


def _is_secret_name(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in SECRET_NAME_HINTS)


def _is_binary_ext(ext: str) -> bool:
    return ext in BINARY_EXTS


def _collect_config_files(root: Path) -> list[str]:
    configs: list[str] = []
    candidates = [root / "config", root]
    allowed_exts = {".json", ".yml", ".yaml", ".toml", ".ini", ".cfg"}
    for base in candidates:
        if not base.exists() or not base.is_dir():
            continue
        try:
            for entry in base.iterdir():
                if not entry.is_file():
                    continue
                if _is_secret_name(entry.name):
                    continue
                if entry.suffix.lower() in allowed_exts or entry.name in {"requirements.txt", "pyproject.toml", "package.json"}:
                    try:
                        configs.append(str(entry.relative_to(root)))
                    except ValueError:
                        configs.append(entry.name)
        except OSError:
            continue
    return sorted(set(configs))[:20]


def _collect_hotspots(root: Path) -> list[str]:
    items: list[tuple[int, Path]] = []
    for file_path in _iter_project_files(root):
        try:
            if _is_secret_name(file_path.name):
                continue
            if _is_binary_ext(file_path.suffix.lower()):
                continue
            size = int(file_path.stat().st_size)
        except OSError:
            continue
        items.append((size, file_path))
    items.sort(key=lambda item: item[0], reverse=True)
    lines: list[str] = []
    for size, file_path in items[:MAX_HOTSPOTS]:
        try:
            rel = file_path.relative_to(root)
        except ValueError:
            rel = file_path
        kb = max(1, size // 1024)
        lines.append(f"{rel} ({kb} KB)")
    return lines


def _extract_api_routes(root: Path) -> list[str]:
    api_dir = root / "api"
    if not api_dir.exists() or not api_dir.is_dir():
        return []
    routes: list[str] = []
    seen: set[str] = set()
    route_pattern = re.compile(r"@app\.(get|post|put|patch|delete|options|head)\(\s*[\"']([^\"']+)[\"']")
    for file_path in api_dir.rglob("*.py"):
        if file_path.name.startswith("_"):
            continue
        try:
            size = int(file_path.stat().st_size)
        except OSError:
            continue
        if size > MAX_ROUTE_SCAN_BYTES:
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in route_pattern.finditer(text):
            method = match.group(1).upper()
            route = match.group(2)
            try:
                rel = file_path.relative_to(root)
            except ValueError:
                rel = file_path
            entry = f"{method} {route} ({rel})"
            if entry in seen:
                continue
            routes.append(entry)
            seen.add(entry)
            if len(routes) >= MAX_ROUTE_COUNT:
                return routes
    return routes


def _build_project_overview(root: Path) -> str:
    if not root.exists():
        return f"Project root not found: {root}"
    entries = []
    try:
        for entry in root.iterdir():
            if entry.name in SKIP_DIRS:
                continue
            label = entry.name + ("/" if entry.is_dir() else "")
            entries.append((entry.is_dir(), label))
    except OSError:
        entries = []
    entries.sort(key=lambda item: (not item[0], item[1].lower()))
    top_level = ", ".join(label for _, label in entries[:30]) or "(empty)"
    if len(entries) > 30:
        top_level += ", ..."

    ext_counts: Counter[str] = Counter()
    for file_path in _iter_project_files(root):
        ext = file_path.suffix.lower() or "<no_ext>"
        ext_counts[ext] += 1

    ext_summary = ", ".join(f"{ext}:{count}" for ext, count in ext_counts.most_common(10)) or "(none)"

    ext_lang = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".html": "HTML",
        ".css": "CSS",
        ".ps1": "PowerShell",
        ".bat": "Batch",
        ".json": "JSON",
        ".xml": "XML",
        ".md": "Markdown",
        ".yml": "YAML",
        ".yaml": "YAML",
        ".bas": "VBA",
    }
    lang_counts: Counter[str] = Counter()
    for ext, count in ext_counts.items():
        lang = ext_lang.get(ext)
        if lang:
            lang_counts[lang] += count
    lang_summary = ", ".join(f"{lang}:{count}" for lang, count in lang_counts.most_common(6)) or "(none)"

    key_files = []
    for name in ("README.md", "requirements.txt", "pyproject.toml", "package.json", "openclaw.json", "ollama_proxy.json"):
        if (root / name).exists():
            key_files.append(name)

    components = []
    if (root / "api").is_dir():
        components.append("api/ - FastAPI server + Ollama/OpenAI proxy")
    if (root / "tools").is_dir():
        components.append("tools/ - automation and model routing helpers")
    if (root / "awarenet-model").is_dir():
        components.append("awarenet-model/ - Awarenet engine code/config")
    if (root / "office-addin").is_dir():
        components.append("office-addin/ - Excel/Word add-in assets")
    if (root / "config").is_dir():
        components.append("config/ - local settings for proxy/gateway")
    if (root / "data").is_dir():
        components.append("data/ - memory + runtime state")

    lines = [
        f"Project overview for {root}",
        "",
        f"Top-level: {top_level}",
        f"Key files: {', '.join(key_files) if key_files else '(none)'}",
        f"Primary file types: {ext_summary}",
        f"Languages (by file types): {lang_summary}",
    ]
    if components:
        lines.append("Notable components:")
        for item in components:
            lines.append(f"- {item}")
    return "\n".join(lines)


def _build_project_detail(root: Path) -> str:
    if not root.exists():
        return f"Project root not found: {root}"

    entries = []
    try:
        for entry in root.iterdir():
            if entry.name in SKIP_DIRS:
                continue
            label = entry.name + ("/" if entry.is_dir() else "")
            entries.append((entry.is_dir(), label))
    except OSError:
        entries = []
    entries.sort(key=lambda item: (not item[0], item[1].lower()))
    top_level = ", ".join(label for _, label in entries[:40]) or "(empty)"
    if len(entries) > 40:
        top_level += ", ..."

    ext_counts: Counter[str] = Counter()
    for file_path in _iter_project_files(root):
        ext = file_path.suffix.lower() or "<no_ext>"
        ext_counts[ext] += 1
    ext_summary = ", ".join(f"{ext}:{count}" for ext, count in ext_counts.most_common(12)) or "(none)"

    ext_lang = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".html": "HTML",
        ".css": "CSS",
        ".ps1": "PowerShell",
        ".bat": "Batch",
        ".json": "JSON",
        ".xml": "XML",
        ".md": "Markdown",
        ".yml": "YAML",
        ".yaml": "YAML",
        ".bas": "VBA",
    }
    lang_counts: Counter[str] = Counter()
    for ext, count in ext_counts.items():
        lang = ext_lang.get(ext)
        if lang:
            lang_counts[lang] += count
    lang_summary = ", ".join(f"{lang}:{count}" for lang, count in lang_counts.most_common(8)) or "(none)"

    entry_candidates = [
        "api/server.py",
        "api/ollama_proxy.py",
        "openclaw.local.py",
        "start_all.ps1",
        "start_all.bat",
        "awarenet-model/v1/awarenet_core.py",
    ]
    entrypoints = [path for path in entry_candidates if (root / path).exists()]

    components = []
    if (root / "api").is_dir():
        components.append("api/ - FastAPI server + Ollama/OpenAI proxy")
    if (root / "tools").is_dir():
        components.append("tools/ - automation and model routing helpers")
    if (root / "awarenet-model").is_dir():
        components.append("awarenet-model/ - Awarenet engine code/config")
    if (root / "office-addin").is_dir():
        components.append("office-addin/ - Excel/Word add-in assets")
    if (root / "config").is_dir():
        components.append("config/ - local settings for proxy/gateway")
    if (root / "data").is_dir():
        components.append("data/ - memory + runtime state")

    configs = _collect_config_files(root)
    routes = _extract_api_routes(root)
    hotspots = _collect_hotspots(root)

    lines = [
        f"Detailed project overview for {root}",
        "",
        f"Top-level: {top_level}",
        f"Primary file types: {ext_summary}",
        f"Languages (by file types): {lang_summary}",
    ]
    if entrypoints:
        lines.append(f"Key entrypoints: {', '.join(entrypoints)}")
    if configs:
        lines.append(f"Notable configs: {', '.join(configs)}")
    if components:
        lines.append("Notable components:")
        for item in components:
            lines.append(f"- {item}")
    if routes:
        lines.append("API routes (detected):")
        for item in routes[:MAX_ROUTE_COUNT]:
            lines.append(f"- {item}")
    if hotspots:
        lines.append("Hot spots (largest files):")
        for item in hotspots:
            lines.append(f"- {item}")
    return "\n".join(lines)


def _maybe_handle_project_overview(clean_user: str, messages: Any) -> Optional[str]:
    if not clean_user:
        return None
    if not PROJECT_INTENT.search(clean_user):
        return None
    root = _extract_workspace_root(messages)
    return _build_project_overview(root)


def _maybe_handle_project_detail(messages: Any, memory: Dict[str, Any], reason: str) -> Optional[str]:
    prefer_memory = reason in ("detail_followup", "followup")
    root = _resolve_project_root(messages, memory, prefer_memory=prefer_memory)
    _record_project_root(memory, root)
    _log_debug("detail_overview", {"root": str(root), "reason": reason})
    return _build_project_detail(root)


def _maybe_handle_skill_request(clean_user: str) -> Optional[str]:
    if not clean_user or not SKILL_INTENT.search(clean_user):
        return None
    config = load_config()
    base = str(config.get("awarenet_base_url") or "http://127.0.0.1:8000").rstrip("/")
    try:
        response = requests.post(
            f"{base}/assistant/skills/scan",
            json={"query": clean_user, "source": "intent"},
            timeout=10,
        )
        if response.status_code < 400:
            data = response.json()
            approvals = data.get("approvals") or []
            installed = data.get("installed") or []
            skills = data.get("skills") or []
            lines = ["Skills auto-improve scan completed."]
            if installed:
                installed_list = ", ".join(item.get("skill", "") for item in installed if isinstance(item, dict))
                if installed_list:
                    lines.append(f"Auto-installed: {installed_list}")
            if approvals:
                approval_list = ", ".join(item.get("skill", "") for item in approvals if isinstance(item, dict))
                if approval_list:
                    lines.append(f"Pending approvals: {approval_list}")
            if skills and not installed and not approvals:
                lines.append("Discovered skills: " + ", ".join(skills))
            lines.append("You can manage skills from the Awarenet UI under Skills & Auto-Improve.")
            return "\n".join(lines)
    except Exception:
        pass
    return "\n".join(
        [
            "I can search and install agent skills via the Skills CLI.",
            "",
            "Search:",
            "```bash",
            "npx skills find <keywords>",
            "```",
            "Install:",
            "```bash",
            "npx skills add <owner/repo>",
            "```",
            "If you want installs without telemetry:",
            "```bash",
            "DISABLE_TELEMETRY=1 npx skills add <owner/repo>",
            "```",
        ]
    )


def _maybe_handle_ambiguous_followup(clean_user: str, memory: Dict[str, Any]) -> Optional[str]:
    if not clean_user:
        return None
    if len(clean_user.split()) > 6 and not AMBIGUOUS_SHORT.match(clean_user.strip()):
        return None
    last_intent, last_ts = _get_last_intent(memory)
    if not last_intent or not _intent_recent(last_ts):
        return None
    return _followup_prompt(last_intent)


def _sanitize_gateway_text(text: str) -> str:
    if not text:
        return text
    wrapped = _is_wrapped_request(text)
    text = _extract_request_tail(text)
    lowered = text.lower()
    if not any(marker.lower() in lowered for marker in GATEWAY_MARKERS):
        if wrapped:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            lines = [line for line in lines if line.lower() != CONFIRM_PROMPT]
            if not lines:
                return ""
            for line in reversed(lines):
                candidate = _strip_user_prefix(TIMESTAMP_PREFIX.sub("", line).strip())
                confirm_lowered = re.sub(r"[\s\.\!\?]+$", "", candidate.lower())
                if CONFIRM_REPLY.match(confirm_lowered):
                    return candidate
            return _strip_user_prefix(TIMESTAMP_PREFIX.sub("", lines[-1]).strip())
        return _strip_user_prefix(TIMESTAMP_PREFIX.sub("", text).strip())
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return text
    lines = [line for line in lines if line.lower() != CONFIRM_PROMPT]
    if not lines:
        return ""
    user_lines = [line for line in lines if USER_LINE_PREFIX.match(line)]
    if user_lines:
        return _strip_user_prefix(TIMESTAMP_PREFIX.sub("", user_lines[-1]).strip())
    for line in reversed(lines):
        candidate = _strip_user_prefix(TIMESTAMP_PREFIX.sub("", line).strip())
        if candidate.lower() == "confirm":
            return "confirm"
    for line in reversed(lines):
        if re.match(r"^(openclaw-control-ui|assistant|you|system:)", line, re.IGNORECASE):
            continue
        if MODEL_TAG_PREFIX.match(line):
            continue
        return _strip_user_prefix(TIMESTAMP_PREFIX.sub("", line).strip())
    return _strip_user_prefix(TIMESTAMP_PREFIX.sub("", lines[-1]).strip())


def _extract_last_user(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    last_user = ""
    preferred = ""
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                last_user = content.strip()
            elif isinstance(content, dict):
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    last_user = text.strip()
            elif isinstance(content, list):
                parts: list[str] = []
                for part in content:
                    if isinstance(part, str):
                        if part.strip():
                            parts.append(part.strip())
                        continue
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                if parts:
                    last_user = " ".join(parts).strip()
            if last_user:
                extracted = _extract_user_request(last_user)
                if extracted:
                    preferred = extracted
    if preferred:
        return _sanitize_gateway_text(preferred)
    if last_user and not _is_wrapped_request(last_user):
        return _sanitize_gateway_text(last_user)
    return ""


def _get_confirm_target(user_text: str) -> str:
    cleaned = _strip_user_prefix(user_text or "")
    trimmed = cleaned.strip()
    lowered = trimmed.lower()
    if lowered.startswith("confirm:"):
        return trimmed.split(":", 1)[1].strip()
    if lowered.startswith("confirm"):
        tail = trimmed[7:].strip()
        if tail:
            return tail
        pending_text = str(PENDING_REQUEST.get("text") or "").strip()
        pending_ts = int(PENDING_REQUEST.get("ts") or 0)
        if pending_text and (_now() - pending_ts) <= PENDING_TTL_SECONDS:
            return pending_text
    pending_text = str(PENDING_REQUEST.get("text") or "").strip()
    pending_ts = int(PENDING_REQUEST.get("ts") or 0)
    if pending_text and (_now() - pending_ts) <= PENDING_TTL_SECONDS:
        confirm_lowered = re.sub(r"[\s\.\!\?]+$", "", lowered)
        if CONFIRM_REPLY.match(confirm_lowered):
            return pending_text
    return ""


def _build_direct_instructions(user_text: str) -> str:
    lowered = user_text.lower()
    steps = []
    if "open " in lowered:
        if "vmware" in lowered:
            steps.append("Open VMware.")
        if "firefox" in lowered:
            steps.append("Open Firefox.")
        if "chrome" in lowered:
            profile_match = CHROME_PROFILE_HINT.search(user_text)
            if "default account" in lowered or "default profile" in lowered:
                steps.append("Open Chrome (default profile).")
            elif profile_match:
                steps.append(f"Open Chrome (profile: {profile_match.group(1).strip()}).")
            else:
                steps.append("Open Chrome.")
        if "vscode" in lowered or "visual studio code" in lowered:
            match_path = PATH_HINT.search(user_text)
            if match_path:
                steps.append(f"Open VSCode {match_path.group(1)}.")
            else:
                steps.append("Open VSCode.")
        match_path = PATH_HINT.search(user_text)
        if match_path:
            steps.append(f"Open {match_path.group(1)}.")
    match_url = re.search(r"(https?://\S+|\b\w+\.\w+\S*)", user_text)
    if ("go to" in lowered or "open" in lowered) and match_url:
        profile_match = CHROME_PROFILE_HINT.search(user_text)
        if "default account" in lowered or "default profile" in lowered:
            steps.append(f"Go to {match_url.group(1)} (default profile).")
        elif profile_match:
            steps.append(f"Go to {match_url.group(1)} (profile: {profile_match.group(1).strip()}).")
        else:
            steps.append(f"Go to {match_url.group(1)}.")
    if not steps:
        return ""
    numbered = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(steps))
    return f"OPENCLAW_INSTRUCTIONS\n{numbered}"


def _openai_fallback_response(model_id: str, content: str) -> Dict[str, Any]:
    safe_content = content.strip() if isinstance(content, str) else str(content)
    if not safe_content:
        safe_content = "No response from model."
    return {
        "id": f"chatcmpl-{_now()}",
        "object": "chat.completion",
        "created": _now(),
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": safe_content},
                "finish_reason": "stop",
            }
        ],
    }


def _response_to_sse(response: Dict[str, Any]) -> str:
    model_id = str(response.get("model") or "awarenet:v1")
    created = int(response.get("created") or _now())
    resp_id = str(response.get("id") or f"chatcmpl-{_now()}")
    content = ""
    choices = response.get("choices") or []
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        if isinstance(message, dict):
            content = str(message.get("content") or "")

    chunks = [content] if content else [""]
    payloads = []
    for idx, part in enumerate(chunks):
        delta: Dict[str, Any] = {"content": part}
        if idx == 0:
            delta["role"] = "assistant"
        payloads.append(
            {
                "id": resp_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_id,
                "choices": [
                    {
                        "index": 0,
                        "delta": delta,
                        "finish_reason": None,
                    }
                ],
            }
        )

    payloads.append(
        {
            "id": resp_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        }
    )

    return "".join(f"data: {json.dumps(payload)}\n\n" for payload in payloads) + "data: [DONE]\n\n"


def _maybe_stream(response: Dict[str, Any], stream: bool):
    if not stream:
        return response
    payload = _response_to_sse(response)
    return StreamingResponse(iter([payload]), media_type="text/event-stream")


def _requires_confirmation(user_text: str) -> bool:
    return bool(RISKY_PATTERNS.search(user_text or ""))


def _should_confirm(model_id: str, user_text: str) -> bool:
    if not _requires_confirmation(user_text):
        return False
    model = str(model_id or "").strip().lower()
    if model.startswith("awarenet"):
        return False
    return True


def _execute_from_response(text: str) -> str:
    results = execute_instructions(text)
    if not results:
        return text
    log_lines = ["OPENCLAW_ACTION_LOG"]
    for result in results:
        detail = f" ({result.detail})" if result.detail else ""
        log_lines.append(f"- {result.action}: {result.status}{detail}")
    return text + "\n\n" + "\n".join(log_lines)


def _append_self_improve_notice(content: str) -> str:
    notices = self_improve.pop_notices()
    if not notices:
        return content
    lines = ["SELF_IMPROVE_NOTICE"]
    for notice in notices:
        detail = notice.get("detail", "").strip()
        benefit = notice.get("benefit", "").strip()
        if benefit:
            lines.append(f"- {notice.get('kind')}: {detail} | benefit: {benefit}")
        else:
            lines.append(f"- {notice.get('kind')}: {detail}")
    return content + "\n\n" + "\n".join(lines)


def _maybe_execute_direct(user_text: str) -> Optional[str]:
    instructions = _build_direct_instructions(user_text)
    if not instructions:
        return None
    results = execute_instructions(instructions)
    log_lines = ["OPENCLAW_ACTION_LOG"]
    for result in results:
        detail = f" ({result.detail})" if result.detail else ""
        log_lines.append(f"- {result.action}: {result.status}{detail}")
    return instructions + "\n\n" + "\n".join(log_lines)


def _email_draft_from_request(user_text: str) -> str:
    dates = DATE_RANGE.findall(user_text)
    date_text = ""
    if dates:
        date_text = dates[0][0]
    subject = "Leave Request"
    body = (
        "Hi [Manager/HR Name],\n\n"
        "I would like to request leave for 15 days starting from "
        + (date_text or "[start date]")
        + ".\n\n"
        "Please let me know if you need any additional information.\n\n"
        "Best regards,\n"
        "[Your Name]"
    )
    return f"Subject: {subject}\n\n{body}"


def _infer_leave_context(memory: Dict[str, Any]) -> str:
    convo = memory.get("conversation") or []
    for item in reversed(convo[-200:]):
        if item.get("role") != "user":
            continue
        content = str(item.get("content") or "")
        lowered = content.lower()
        if "leave" in lowered and DATE_RANGE.search(content):
            return content
    return ""


def _build_email_instructions(prefer_default: bool = False, profile_name: str = "") -> str:
    if profile_name:
        open_chrome = f"Open Chrome (profile: {profile_name})."
        go_gmail = f"Go to mail.google.com (profile: {profile_name})."
    else:
        open_chrome = "Open Chrome (default profile)." if prefer_default else "Open Chrome."
        go_gmail = "Go to mail.google.com (default profile)." if prefer_default else "Go to mail.google.com."
    steps = [
        open_chrome,
        go_gmail,
        "If prompted, sign in to your Gmail account.",
        "Click Compose.",
        "Enter the recipient in the To field.",
        "Enter the subject line from the draft.",
        "Paste the drafted email body.",
        "Do NOT click Send.",
    ]
    numbered = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(steps))
    return f"OPENCLAW_INSTRUCTIONS\n{numbered}"


def _confirm_message(clean_user: str) -> str:
    msg = "This action may be sensitive. Reply with 'confirm' to proceed."
    if EMAIL_INTENT.search(clean_user):
        prefer_default = "default account" in clean_user.lower() or "default profile" in clean_user.lower()
        profile_match = CHROME_PROFILE_HINT.search(clean_user)
        profile_name = profile_match.group(1).strip() if profile_match else ""
        msg += "\n\n" + _build_email_instructions(prefer_default=prefer_default, profile_name=profile_name)
    return msg


def _create_webapp(path_text: str, prompt: str) -> str:
    target = Path(path_text)
    target.mkdir(parents=True, exist_ok=True)
    (target / "assets").mkdir(exist_ok=True)
    index = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Fashion Atelier</title>
  <link rel=\"stylesheet\" href=\"styles.css\" />
</head>
<body>
  <header class=\"hero\">
    <div class=\"hero__content\">
      <p class=\"eyebrow\">New Season</p>
      <h1>Fashion Atelier</h1>
      <p class=\"lead\">Curated silhouettes, premium fabrics, and timeless edits for modern wardrobes.</p>
      <div class=\"actions\">
        <button class=\"btn primary\">Shop Lookbook</button>
        <button class=\"btn ghost\">Book Styling</button>
      </div>
    </div>
  </header>
  <section class=\"grid\">
    <article class=\"card\">
      <h3>Signature Sets</h3>
      <p>Matching ensembles built for effortless layering.</p>
    </article>
    <article class=\"card\">
      <h3>Evening Luxe</h3>
      <p>Statement pieces for gala nights and special moments.</p>
    </article>
    <article class=\"card\">
      <h3>Studio Tailoring</h3>
      <p>Precision tailoring with a made-to-measure feel.</p>
    </article>
  </section>
  <section class=\"cta\">
    <h2>Build your capsule wardrobe</h2>
    <p>Schedule a 1:1 session with our stylists.</p>
    <button class=\"btn primary\">Start Consultation</button>
  </section>
  <script src=\"app.js\"></script>
</body>
</html>"""
    styles = """@import url('https://fonts.googleapis.com/css2?family=Fraunces:wght@400;600&family=Space+Grotesk:wght@400;500;600&display=swap');
:root { --bg: #f6f1ec; --ink:#121212; --accent:#b86b4b; --muted:#8b8076; }
*{box-sizing:border-box;}
body{margin:0;font-family:'Space Grotesk',sans-serif;color:var(--ink);background:radial-gradient(circle at top,#fff 0%,#f6f1ec 55%,#efe7df 100%);} 
.hero{padding:96px 8vw;background:linear-gradient(120deg,#f7ede3, #f2d7c6);} 
.hero__content{max-width:640px;} 
.eyebrow{letter-spacing:.3em;text-transform:uppercase;color:var(--muted);} 
h1{font-family:'Fraunces',serif;font-size:64px;margin:12px 0;} 
.lead{font-size:18px;color:#3a322c;}
.actions{margin-top:24px;display:flex;gap:16px;flex-wrap:wrap;}
.btn{padding:12px 20px;border-radius:999px;border:1px solid var(--ink);background:transparent;cursor:pointer;font-weight:600;}
.btn.primary{background:var(--ink);color:white;border:none;}
.btn.ghost{border-color:var(--muted);color:var(--muted);} 
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:20px;padding:40px 8vw;} 
.card{background:white;padding:24px;border-radius:16px;box-shadow:0 12px 24px rgba(0,0,0,.08);} 
.cta{padding:64px 8vw;background:#1c1c1c;color:white;text-align:center;} 
.cta p{color:#d1c7bf;}"""
    js = """document.querySelectorAll('.btn').forEach(btn=>btn.addEventListener('click',()=>alert('Thanks! We will reach out shortly.')));"""
    (target / "index.html").write_text(index, encoding="utf-8")
    (target / "styles.css").write_text(styles, encoding="utf-8")
    (target / "app.js").write_text(js, encoding="utf-8")
    (target / "README.md").write_text(f"# Fashion Webapp\n\nGenerated from prompt: {prompt}\n", encoding="utf-8")
    return f"Created webapp at {target}" 


def _handle_confirmed_action(clean_user: str) -> Optional[str]:
    if EMAIL_INTENT.search(clean_user):
        draft = _email_draft_from_request(clean_user)
        prefer_default = "default account" in clean_user.lower() or "default profile" in clean_user.lower()
        profile_match = CHROME_PROFILE_HINT.search(clean_user)
        profile_name = profile_match.group(1).strip() if profile_match else ""
        instructions = _build_email_instructions(prefer_default=prefer_default, profile_name=profile_name)
        response = draft + "\n\n" + instructions
        return _execute_from_response(response)
    if WEBAPP_INTENT.search(clean_user):
        match_path = PATH_HINT.search(clean_user)
        if match_path:
            result = _create_webapp(match_path.group(1), clean_user)
            return result
    return None


def _maybe_handle_email_draft(clean_user: str, memory: Dict[str, Any]) -> Optional[str]:
    if not EMAIL_INTENT.search(clean_user):
        return None
    if not EMAIL_DRAFT_HINT.search(clean_user):
        return None
    context_text = clean_user
    if not DATE_RANGE.search(clean_user):
        inferred = _infer_leave_context(memory)
        if inferred:
            context_text = inferred
    draft = _email_draft_from_request(context_text)
    prefer_default = "default account" in clean_user.lower() or "default profile" in clean_user.lower()
    profile_match = CHROME_PROFILE_HINT.search(clean_user)
    profile_name = profile_match.group(1).strip() if profile_match else ""
    instructions = _build_email_instructions(prefer_default=prefer_default, profile_name=profile_name)
    response = draft + "\n\n" + instructions
    return _execute_from_response(response)


def _maybe_handle_webapp(clean_user: str) -> Optional[str]:
    if not WEBAPP_INTENT.search(clean_user):
        return None
    match_path = PATH_HINT.search(clean_user)
    if not match_path:
        return None
    return _create_webapp(match_path.group(1), clean_user)


def _awarenet_url(path: str) -> str:
    base = str(config.get("awarenet_base_url") or "http://127.0.0.1:8000").rstrip("/")
    return f"{base}{path}"


@app.get("/api/tags")
async def tags() -> Dict[str, Any]:
    model_id = str(config.get("model_id") or "awarenet:v1")
    return {
        "models": [
            {
                "name": model_id,
                "model": model_id,
                "modified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "size": 0,
                "digest": "awarenet-proxy",
                "details": {
                    "format": "proxy",
                    "family": "awarenet",
                    "parameter_size": "",
                    "quantization_level": ""
                }
            }
        ]
    }


@app.get("/api/ps")
async def ps() -> Dict[str, Any]:
    return {"models": []}


@app.post("/api/show")
async def show(payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
    model_id = str(config.get("model_id") or "awarenet:v1")
    arch = "awarenet"
    context_len = int(config.get("max_input_tokens") or 32768)
    capabilities = ["tools"]
    if str(config.get("vision") or "").lower() in ("1", "true", "yes"):
        capabilities.append("vision")
    return {
        "model": model_id,
        "modelfile": "",
        "parameters": "",
        "template": "",
        "details": {
            "format": "proxy",
            "family": "awarenet",
            "parameter_size": "",
            "quantization_level": "",
        },
        "model_info": {
            "general.architecture": arch,
            f"{arch}.context_length": context_len,
        },
        "capabilities": capabilities,
    }


@app.get("/api/version")
async def version() -> Dict[str, Any]:
    # VS Code and other clients expect a semver-like Ollama version.
    return {"version": "0.6.4"}


@app.post("/api/stop")
async def stop() -> Dict[str, Any]:
    return {"status": "stopped"}


@app.post("/api/chat")
async def chat(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    model_id = str(config.get("model_id") or "awarenet:v1")
    messages = payload.get("messages") or []
    last_user = _extract_last_user(messages)
    confirm_target = _get_confirm_target(last_user)
    clean_user = confirm_target or last_user
    memory = _load_memory()
    if clean_user:
        clean_user = _apply_preference_hints(clean_user, memory)
    intent, intent_confidence, intent_reason = _infer_intent(clean_user, memory) if clean_user else (None, "low", "empty")
    _log_debug(
        "openai_clean_user",
        {
            "last_user": (last_user[:300] if isinstance(last_user, str) else str(last_user)),
            "clean_user": (clean_user[:300] if isinstance(clean_user, str) else str(clean_user)),
            "confirm_target": bool(confirm_target),
            "requires_confirmation": _should_confirm(model_id, clean_user),
        },
    )
    _log_debug(
        "openai_clean_user",
        {
            "text": (clean_user[:300] if isinstance(clean_user, str) else str(clean_user)),
            "requires_confirmation": _should_confirm(model_id, clean_user),
        },
    )
    if clean_user:
        _log_debug(
            "intent_policy",
            {
                "intent": intent,
                "confidence": intent_confidence,
                "reason": intent_reason,
            },
        )
    if clean_user and not _is_wrapped_request(clean_user):
        _learn_preferences(memory, clean_user)
        _append_conversation(memory, "user", clean_user)
        if intent:
            _record_intent(memory, intent)
        _save_memory(memory)

    if intent == "project_detail":
        project_detail = _maybe_handle_project_detail(messages, memory, intent_reason)
        if project_detail:
            _record_assistant(memory, project_detail)
            return {
                "model": model_id,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "message": {"role": "assistant", "content": project_detail},
                "done": True,
                "total_duration": 0,
                "load_duration": 0,
                "prompt_eval_count": 0,
                "prompt_eval_duration": 0,
                "eval_count": 0,
                "eval_duration": 0,
            }

    if intent == "project_overview":
        root = _resolve_project_root(messages, memory, prefer_memory=False)
        project_overview = _build_project_overview(root)
        _record_project_root(memory, root)
        _record_assistant(memory, project_overview)
        return {
            "model": model_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "message": {"role": "assistant", "content": project_overview},
            "done": True,
            "total_duration": 0,
            "load_duration": 0,
            "prompt_eval_count": 0,
            "prompt_eval_duration": 0,
            "eval_count": 0,
            "eval_duration": 0,
        }

    if intent == "skill_request":
        skill_response = _maybe_handle_skill_request(clean_user)
        if skill_response:
            _record_assistant(memory, skill_response)
            return {
                "model": model_id,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "message": {"role": "assistant", "content": skill_response},
                "done": True,
                "total_duration": 0,
                "load_duration": 0,
                "prompt_eval_count": 0,
                "prompt_eval_duration": 0,
                "eval_count": 0,
                "eval_duration": 0,
            }

    if intent == "email_draft" and intent_reason == "followup":
        followup_msg = _followup_prompt(intent)
        _record_assistant(memory, followup_msg)
        return {
            "model": model_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "message": {"role": "assistant", "content": followup_msg},
            "done": True,
            "total_duration": 0,
            "load_duration": 0,
            "prompt_eval_count": 0,
            "prompt_eval_duration": 0,
            "eval_count": 0,
            "eval_duration": 0,
        }

    auto_email = None
    if intent in (None, "email_draft"):
        auto_email = _maybe_handle_email_draft(clean_user, memory)
    if auto_email:
        _remember_phrase(memory, clean_user, auto_email)
        _record_assistant(memory, auto_email)
        return {
            "model": model_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "message": {"role": "assistant", "content": _append_self_improve_notice(auto_email)},
            "done": True,
            "total_duration": 0,
            "load_duration": 0,
            "prompt_eval_count": 0,
            "prompt_eval_duration": 0,
            "eval_count": 0,
            "eval_duration": 0,
        }

    if not confirm_target and _should_confirm(model_id, clean_user):
        PENDING_REQUEST["text"] = clean_user
        PENDING_REQUEST["ts"] = _now()
        confirm_msg = _confirm_message(clean_user)
        _record_assistant(memory, confirm_msg)
        return {
            "model": model_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "message": {"role": "assistant", "content": _confirm_message(clean_user)},
            "done": True,
            "total_duration": 0,
            "load_duration": 0,
            "prompt_eval_count": 0,
            "prompt_eval_duration": 0,
            "eval_count": 0,
            "eval_duration": 0,
        }

    if confirm_target:
        handled = _handle_confirmed_action(clean_user)
        if handled:
            _remember_phrase(memory, clean_user, handled)
            _record_assistant(memory, handled)
            return {
                "model": model_id,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "message": {"role": "assistant", "content": _append_self_improve_notice(handled)},
                "done": True,
                "total_duration": 0,
                "load_duration": 0,
                "prompt_eval_count": 0,
                "prompt_eval_duration": 0,
                "eval_count": 0,
                "eval_duration": 0,
            }

    remembered = _lookup_phrase(memory, clean_user)
    if remembered:
        content = _execute_from_response(remembered) if "OPENCLAW_INSTRUCTIONS" in remembered else remembered
        _record_assistant(memory, content)
        return {
            "model": model_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "message": {"role": "assistant", "content": _append_self_improve_notice(content)},
            "done": True,
            "total_duration": 0,
            "load_duration": 0,
            "prompt_eval_count": 0,
            "prompt_eval_duration": 0,
            "eval_count": 0,
            "eval_duration": 0,
        }

    ambiguity = _maybe_handle_ambiguous_followup(clean_user, memory)
    if ambiguity:
        _record_assistant(memory, ambiguity)
        return {
            "model": model_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "message": {"role": "assistant", "content": ambiguity},
            "done": True,
            "total_duration": 0,
            "load_duration": 0,
            "prompt_eval_count": 0,
            "prompt_eval_duration": 0,
            "eval_count": 0,
            "eval_duration": 0,
        }

    if intent == "webapp" and intent_reason == "followup":
        followup_msg = _followup_prompt(intent)
        _record_assistant(memory, followup_msg)
        return {
            "model": model_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "message": {"role": "assistant", "content": followup_msg},
            "done": True,
            "total_duration": 0,
            "load_duration": 0,
            "prompt_eval_count": 0,
            "prompt_eval_duration": 0,
            "eval_count": 0,
            "eval_duration": 0,
        }

    direct_webapp = None
    if intent in (None, "webapp"):
        direct_webapp = _maybe_handle_webapp(clean_user)
    if direct_webapp:
        _remember_phrase(memory, clean_user, direct_webapp)
        _record_assistant(memory, direct_webapp)
        return {
            "model": model_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "message": {"role": "assistant", "content": _append_self_improve_notice(direct_webapp)},
            "done": True,
            "total_duration": 0,
            "load_duration": 0,
            "prompt_eval_count": 0,
            "prompt_eval_duration": 0,
            "eval_count": 0,
            "eval_duration": 0,
        }

    direct = _maybe_execute_direct(clean_user)
    if direct:
        _remember_phrase(memory, clean_user, direct)
        _record_assistant(memory, direct)
        return {
            "model": model_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "message": {"role": "assistant", "content": _append_self_improve_notice(direct)},
            "done": True,
            "total_duration": 0,
            "load_duration": 0,
            "prompt_eval_count": 0,
            "prompt_eval_duration": 0,
            "eval_count": 0,
            "eval_duration": 0,
        }

    if stream and clean_user:
        upstream_messages = [{"role": "user", "content": clean_user}]
    else:
        upstream_messages = _get_recent_conversation(memory, limit=200)
        if not upstream_messages and clean_user:
            upstream_messages = [{"role": "user", "content": clean_user}]
    upstream_payload: Dict[str, Any] = {
        "model": model_id,
        "messages": upstream_messages,
    }

    try:
        resp = await run_in_threadpool(
            requests.post,
            _awarenet_url("/v1/chat/completions"),
            json=upstream_payload,
            timeout=45,
        )
    except Exception as exc:  # noqa: BLE001
        return _openai_fallback_response(model_id, f"Upstream error: {exc}")

    if resp.status_code >= 400:
        return _openai_fallback_response(model_id, f"Upstream error {resp.status_code}: {resp.text}")

    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return _openai_fallback_response(model_id, f"Upstream JSON error: {exc}")
    choices = data.get("choices") or []
    content = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        if isinstance(message, dict):
            content = str(message.get("content") or "")
    if not content:
        content = "No response from model."
    if "OPENCLAW_INSTRUCTIONS" in content:
        content = _execute_from_response(content)
        if clean_user:
            _remember_phrase(memory, clean_user, content)
            _record_assistant(memory, content)
    else:
        _record_assistant(memory, content)

    return {
        "model": model_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "message": {"role": "assistant", "content": _append_self_improve_notice(content)},
        "done": True,
        "total_duration": 0,
        "load_duration": 0,
        "prompt_eval_count": 0,
        "prompt_eval_duration": 0,
        "eval_count": 0,
        "eval_duration": 0,
    }


@app.post("/v1/chat/completions")
async def openai_chat(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    model_id = str(config.get("model_id") or "awarenet:v1")
    messages = payload.get("messages") or []
    stream = bool(payload.get("stream"))
    _log_debug(
        "openai_request",
        {
            "model": payload.get("model"),
            "effective_model": model_id,
            "stream": stream,
            "messages": _summarize_messages(messages),
        },
    )
    last_user = _extract_last_user(messages)
    if isinstance(last_user, str):
        _maybe_record_vscode_context(last_user)
    confirm_target = _get_confirm_target(last_user)
    clean_user = confirm_target or last_user
    memory = _load_memory()
    if clean_user:
        clean_user = _apply_preference_hints(clean_user, memory)
    intent, intent_confidence, intent_reason = _infer_intent(clean_user, memory) if clean_user else (None, "low", "empty")
    _log_debug(
        "openai_clean_user",
        {
            "last_user": (last_user[:300] if isinstance(last_user, str) else str(last_user)),
            "clean_user": (clean_user[:300] if isinstance(clean_user, str) else str(clean_user)),
            "confirm_target": bool(confirm_target),
            "requires_confirmation": _should_confirm(model_id, clean_user),
        },
    )
    if clean_user:
        _log_debug(
            "intent_policy",
            {
                "intent": intent,
                "confidence": intent_confidence,
                "reason": intent_reason,
            },
        )
    if clean_user and not _is_wrapped_request(clean_user):
        _learn_preferences(memory, clean_user)
        _append_conversation(memory, "user", clean_user)
        if intent:
            _record_intent(memory, intent)
        _save_memory(memory)

    if intent == "project_detail":
        project_detail = _maybe_handle_project_detail(messages, memory, intent_reason)
        if project_detail:
            _record_assistant(memory, project_detail)
            return _maybe_stream({
                "id": f"chatcmpl-{_now()}",
                "object": "chat.completion",
                "created": _now(),
                "model": model_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": project_detail},
                        "finish_reason": "stop",
                    }
                ],
            }, stream)

    if intent == "project_overview":
        root = _resolve_project_root(messages, memory, prefer_memory=False)
        project_overview = _build_project_overview(root)
        _record_project_root(memory, root)
        _record_assistant(memory, project_overview)
        return _maybe_stream({
            "id": f"chatcmpl-{_now()}",
            "object": "chat.completion",
            "created": _now(),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": project_overview},
                    "finish_reason": "stop",
                }
            ],
        }, stream)

    if intent == "task_list":
        tasks = assistant_state.list_tasks(include_history=False)
        content = "Tasks:\n"
        queue = tasks.get("queue") or []
        if not queue:
            content += "- No pending tasks."
        else:
            for task in queue[:20]:
                content += f"- [{task.get('priority')}] {task.get('description')} ({task.get('id')})\n"
        _record_assistant(memory, content)
        return _maybe_stream({
            "id": f"chatcmpl-{_now()}",
            "object": "chat.completion",
            "created": _now(),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
        }, stream)

    if intent == "task_create":
        description = _extract_task_description(clean_user or "")
        if not description:
            description = clean_user or "New task"
        task = assistant_state.add_task(description, priority="medium", metadata={"source": "chat"})
        content = f"Task created: {task.get('description')} ({task.get('id')})"
        _record_assistant(memory, content)
        return _maybe_stream({
            "id": f"chatcmpl-{_now()}",
            "object": "chat.completion",
            "created": _now(),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
        }, stream)

    if intent == "skill_request":
        skill_response = _maybe_handle_skill_request(clean_user)
        if skill_response:
            _record_assistant(memory, skill_response)
            return _maybe_stream({
                "id": f"chatcmpl-{_now()}",
                "object": "chat.completion",
                "created": _now(),
                "model": model_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": skill_response},
                        "finish_reason": "stop",
                    }
                ],
            }, stream)

    if intent == "email_draft" and intent_reason == "followup":
        followup_msg = _followup_prompt(intent)
        _record_assistant(memory, followup_msg)
        return _maybe_stream({
            "id": f"chatcmpl-{_now()}",
            "object": "chat.completion",
            "created": _now(),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": followup_msg},
                    "finish_reason": "stop",
                }
            ],
        }, stream)

    auto_email = None
    if intent in (None, "email_draft"):
        auto_email = _maybe_handle_email_draft(clean_user, memory)
    if auto_email:
        _remember_phrase(memory, clean_user, auto_email)
        _record_assistant(memory, auto_email)
        return _maybe_stream({
            "id": f"chatcmpl-{_now()}",
            "object": "chat.completion",
            "created": _now(),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": _append_self_improve_notice(auto_email)},
                    "finish_reason": "stop",
                }
            ],
        }, stream)

    if not confirm_target and _should_confirm(model_id, clean_user):
        PENDING_REQUEST["text"] = clean_user
        PENDING_REQUEST["ts"] = _now()
        confirm_msg = _confirm_message(clean_user)
        _record_assistant(memory, confirm_msg)
        return _maybe_stream({
            "id": f"chatcmpl-{_now()}",
            "object": "chat.completion",
            "created": _now(),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": _confirm_message(clean_user)},
                    "finish_reason": "stop",
                }
            ],
        }, stream)

    if confirm_target:
        handled = _handle_confirmed_action(clean_user)
        if handled:
            _remember_phrase(memory, clean_user, handled)
            _record_assistant(memory, handled)
            return _maybe_stream({
                "id": f"chatcmpl-{_now()}",
                "object": "chat.completion",
                "created": _now(),
                "model": model_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": _append_self_improve_notice(handled)},
                        "finish_reason": "stop",
                    }
                ],
            }, stream)

    remembered = _lookup_phrase(memory, clean_user)
    if remembered:
        content = _execute_from_response(remembered) if "OPENCLAW_INSTRUCTIONS" in remembered else remembered
        _record_assistant(memory, content)
        return _maybe_stream({
            "id": f"chatcmpl-{_now()}",
            "object": "chat.completion",
            "created": _now(),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": _append_self_improve_notice(content)},
                    "finish_reason": "stop",
                  }
              ],
          }, stream)

    ambiguity = _maybe_handle_ambiguous_followup(clean_user, memory)
    if ambiguity:
        _record_assistant(memory, ambiguity)
        return _maybe_stream({
            "id": f"chatcmpl-{_now()}",
            "object": "chat.completion",
            "created": _now(),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": ambiguity},
                    "finish_reason": "stop",
                }
            ],
        }, stream)

    if intent == "webapp" and intent_reason == "followup":
        followup_msg = _followup_prompt(intent)
        _record_assistant(memory, followup_msg)
        return _maybe_stream({
            "id": f"chatcmpl-{_now()}",
            "object": "chat.completion",
            "created": _now(),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": followup_msg},
                    "finish_reason": "stop",
                }
            ],
        }, stream)

    direct_webapp = None
    if intent in (None, "webapp"):
        direct_webapp = _maybe_handle_webapp(clean_user)
    if direct_webapp:
        _remember_phrase(memory, clean_user, direct_webapp)
        _record_assistant(memory, direct_webapp)
        return _maybe_stream({
            "id": f"chatcmpl-{_now()}",
            "object": "chat.completion",
            "created": _now(),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": _append_self_improve_notice(direct_webapp)},
                    "finish_reason": "stop",
                }
            ],
        }, stream)

    direct = _maybe_execute_direct(clean_user)
    if direct:
        _remember_phrase(memory, clean_user, direct)
        _record_assistant(memory, direct)
        return _maybe_stream({
            "id": f"chatcmpl-{_now()}",
            "object": "chat.completion",
            "created": _now(),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": _append_self_improve_notice(direct)},
                    "finish_reason": "stop",
                }
            ],
        }, stream)

    upstream_messages = _get_recent_conversation(memory, limit=200)
    if not upstream_messages and clean_user:
        upstream_messages = [{"role": "user", "content": clean_user}]
    context_msg = _assistant_context_message()
    if context_msg:
        if upstream_messages and upstream_messages[0].get("role") == "system":
            upstream_messages.insert(1, context_msg)
        else:
            upstream_messages.insert(0, context_msg)
    upstream_payload: Dict[str, Any] = {
        "model": model_id,
        "messages": upstream_messages,
    }

    try:
        resp = await run_in_threadpool(
            requests.post,
            _awarenet_url("/v1/chat/completions"),
            json=upstream_payload,
            timeout=45,
        )
    except Exception as exc:  # noqa: BLE001
        _log_debug("openai_fallback", {"reason": f"upstream_error: {exc}"})
        return _maybe_stream(_openai_fallback_response(model_id, f"Upstream error: {exc}"), stream)

    if resp.status_code >= 400:
        _log_debug(
            "openai_fallback",
            {"reason": f"upstream_status: {resp.status_code}", "body": resp.text[:500]},
        )
        return _maybe_stream(_openai_fallback_response(model_id, f"Upstream error {resp.status_code}: {resp.text}"), stream)

    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        _log_debug("openai_fallback", {"reason": f"upstream_json_error: {exc}"})
        return _maybe_stream(_openai_fallback_response(model_id, f"Upstream JSON error: {exc}"), stream)
    if not isinstance(data, dict) or not data.get("choices"):
        fallback_content = ""
        if isinstance(data, dict):
            fallback_content = str(data.get("error") or data.get("detail") or data)
        else:
            fallback_content = str(data)
        if not fallback_content:
            fallback_content = "No response from model."
        _log_debug("openai_fallback", {"reason": "missing_choices", "body": fallback_content[:500]})
        return _maybe_stream(_openai_fallback_response(model_id, fallback_content), stream)

    choices = data.get("choices") or []
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        if isinstance(message, dict):
            content = str(message.get("content") or "")
            if "OPENCLAW_INSTRUCTIONS" in content:
                executed = _execute_from_response(content)
                choices[0]["message"] = {"role": "assistant", "content": _append_self_improve_notice(executed)}
                if clean_user:
                    _remember_phrase(memory, clean_user, executed)
                    _record_assistant(memory, executed)
            elif not content:
                choices[0]["message"] = {"role": "assistant", "content": "No response from model."}
            else:
                _record_assistant(memory, content)
    _log_debug("openai_response", {"has_choices": True, "choices": len(choices)})
    return _maybe_stream(data, stream)


@app.get("/v1/models")
async def openai_models() -> Dict[str, Any]:
    model_id = str(config.get("model_id") or "awarenet:v1")
    return {"object": "list", "data": [{"id": model_id, "object": "model", "created": _now(), "owned_by": "proxy"}]}
