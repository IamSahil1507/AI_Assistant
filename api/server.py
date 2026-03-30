import time
import asyncio
import requests
import os
from typing import Any, Dict, Optional
import re
from uuid import uuid4
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse

from tools.openclaw_bridge import OpenClawBridge
from tools import assistant_state
from tools.operator_controller import OperatorController, PlanStep
from tools.proactive_engine import ProactiveEngine
from tools.skills_manager import SkillsManager
from tools import skills_state
from tools import config_store
from tools import operator_troubleshoot
from tools import research_runner
from tools.fix_attempts import FixAttempt
from tools import fix_executor
from tools import voice
from tools.operator_tools import recipes
from tools import chat_store

AWARNET_MODELS = {"awarenet", "awarenet-v1", "awarenet:v1"}

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

bridge = OpenClawBridge()
operator = OperatorController(bridge)
skills_manager = SkillsManager(lambda: bridge.config_manager.config)
proactive = ProactiveEngine(lambda: bridge.config_manager.config, tick_callbacks=[skills_manager.scheduled_tick])
LOGS_DIR = Path(__file__).resolve().parents[1] / "logs"
UI_DIST = Path(__file__).resolve().parents[1] / "awarenet-ui" / "dist"

if UI_DIST.exists():
    app.mount("/awarenet", StaticFiles(directory=UI_DIST, html=True), name="awarenet")
GATEWAY_MARKERS = (
    "openclaw-control-ui",
    "Direct gateway chat session",
    "Main Session",
)
REQUEST_MARKERS = (
    "my request for codex:",
    "my request for copilot:",
    "my request for github copilot:",
    "user request:",
    "user prompt:",
)
CONTEXT_MARKER = "context from my ide setup"
USER_PREFIX = re.compile(r"^(user|you)\s*[:\-]\s*", re.IGNORECASE)


def _safe_log_path(path: str) -> Optional[Path]:
    if not path:
        return None
    candidate = (LOGS_DIR / path).resolve()
    try:
        candidate.relative_to(LOGS_DIR.resolve())
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


ALLOWED_CONFIG_KEYS = {
    "gateway_base_url",
    "awarenet_ui_poll_interval_seconds",
    "model_poll_interval_seconds",
    "log_retention_days",
    "log_retention_entries",
    "awarenet_ui",
    "skills",
    "assistant_policy",
    "research_enabled",
    "research_mode",
    "max_research_minutes",
    "max_fix_attempts_per_failure",
    "editor_bridge",
    "desktop",
    "voice",
    # Runtime feature flags for modular UI/backends
    "features",
}


def _apply_config_updates(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return bridge.get_safe_config()
    config = bridge.config_manager.config
    updates: Dict[str, Any] = {}
    for key in ALLOWED_CONFIG_KEYS:
        if key in payload:
            updates[key] = payload[key]
    merged = _deep_merge(config, updates)
    bridge.config_manager._config = merged
    bridge.config_manager.save_app_config()
    bridge.config_manager.update_user_config(updates)
    return bridge.get_safe_config()


def _default_features() -> Dict[str, Any]:
    # Minimal v1 shape; can be extended without breaking clients.
    return {
        "operator": {"enabled": True, "mode": "auto_unless_risky", "scope": "everything", "limits": {"max_steps": 12}},
        "chats": {"enabled": True, "mode": "ask", "scope": "everything", "limits": {}},
        "approvals": {"enabled": True, "mode": "ask", "scope": "everything", "limits": {}},
        "browser": {"enabled": True, "mode": "auto_unless_risky", "scope": "everything", "limits": {}},
        "editor": {"enabled": True, "mode": "auto_unless_risky", "scope": "workspace_only", "limits": {}},
        "desktop": {"enabled": True, "mode": "ask", "scope": "everything", "limits": {}},
        "voice": {"enabled": True, "mode": "ask", "scope": "everything", "limits": {}},
        "research": {"enabled": bool(bridge.config_manager.config.get("research_enabled", True)), "mode": "auto_unless_risky", "scope": "everything", "limits": {"max_minutes": int(bridge.config_manager.config.get("max_research_minutes", 5) or 5)}},
        "autofix": {"enabled": True, "mode": "ask", "scope": "workspace_only", "limits": {"max_attempts": int(bridge.config_manager.config.get("max_fix_attempts_per_failure", 2) or 2)}},
        "logs": {"enabled": True, "mode": "off", "scope": "everything", "limits": {}},
        "lessons": {"enabled": True, "mode": "off", "scope": "everything", "limits": {}},
    }


def _get_features() -> Dict[str, Any]:
    cfg = bridge.config_manager.config
    raw = cfg.get("features") if isinstance(cfg.get("features"), dict) else {}
    return _deep_merge(_default_features(), raw)  # defaults < overridden


def _compute_capabilities() -> Dict[str, Any]:
    cfg = bridge.config_manager.config

    def ok(reason: str = "") -> Dict[str, Any]:
        return {"available": True, "reason": reason}

    def no(reason: str) -> Dict[str, Any]:
        return {"available": False, "reason": reason}

    modules: Dict[str, Any] = {"operator": ok(), "chats": ok(), "approvals": ok(), "logs": ok(), "lessons": ok()}

    # Browser (Playwright) availability
    try:
        from tools.operator_tools import browser_playwright as _bp  # noqa: F401

        modules["browser"] = ok()
    except Exception as exc:  # noqa: BLE001
        modules["browser"] = no(f"playwright_unavailable:{exc}")

    # Editor bridge availability (VS Code/Cursor extension)
    try:
        from tools.operator_tools import editor_bridge as _eb

        health = _eb.health(config=cfg)
        modules["editor"] = ok() if bool(health.get("ok")) else no(str(health.get("error") or "editor_bridge_unreachable"))
    except Exception as exc:  # noqa: BLE001
        modules["editor"] = no(f"editor_bridge_error:{exc}")

    # Desktop automation availability (pywinauto)
    try:
        from tools.operator_tools import desktop_windows as _dw  # noqa: F401

        modules["desktop"] = ok()
    except Exception as exc:  # noqa: BLE001
        modules["desktop"] = no(f"desktop_unavailable:{exc}")

    # Voice availability (provider + model path)
    try:
        voice_cfg = cfg.get("voice") if isinstance(cfg.get("voice"), dict) else {}
        enabled = bool(voice_cfg.get("enabled", False))
        if not enabled:
            modules["voice"] = no("voice_disabled_in_config")
        else:
            stt = str(voice_cfg.get("stt_provider") or "").strip().lower()
            if stt == "vosk":
                model_path = str(voice_cfg.get("vosk_model_path") or "").strip()
                if not model_path:
                    modules["voice"] = no("missing_vosk_model_path")
                else:
                    modules["voice"] = ok()
            else:
                modules["voice"] = ok()
    except Exception as exc:  # noqa: BLE001
        modules["voice"] = no(f"voice_unavailable:{exc}")

    # Research/autofix are logic modules (always available if code present)
    modules["research"] = ok() if bool(cfg.get("research_enabled", True)) else no("research_disabled_in_config")
    modules["autofix"] = ok()

    return {"ok": True, "modules": modules}


@app.get("/assistant/health")
async def assistant_health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "ts": time.time(),
        "policy": bridge.get_policy_state(),
    }


@app.get("/assistant/manifest")
async def assistant_manifest() -> Dict[str, Any]:
    caps = _compute_capabilities()
    return {
        "status": "ok",
        "ts": time.time(),
        "baseUrls": {
            "assistant_api": "http://127.0.0.1:8000",
            "ollama_proxy": "http://127.0.0.1:11435",
        },
        "capabilities": caps.get("modules", {}),
    }


@app.get("/assistant/capabilities")
async def assistant_capabilities() -> Dict[str, Any]:
    return {"status": "ok", **_compute_capabilities()}


@app.get("/assistant/features")
async def assistant_features_get() -> Dict[str, Any]:
    return {"status": "ok", "features": _get_features()}


@app.post("/assistant/features")
async def assistant_features_post(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    current = _get_features()
    merged = _deep_merge(current, payload)
    updated = _apply_config_updates({"features": merged})
    return {"status": "ok", "features": updated.get("features", merged)}


@app.post("/assistant/chat/send")
async def assistant_chat_send(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")

    chat_id = str(payload.get("chat_id") or "").strip()
    if not chat_id:
        chat_id = chat_store.new_chat_id()

    model_id = str(payload.get("model") or "assistant").strip()
    system_prompt = payload.get("system_prompt")
    if system_prompt is not None and not isinstance(system_prompt, str):
        system_prompt = None

    user_text = str(payload.get("message") or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="missing_message")

    attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
    attachments = [a for a in attachments if isinstance(a, dict)]

    if model_id in AWARNET_MODELS:
        user_text_clean = _sanitize_gateway_text(user_text)
        result = bridge.execute_awarenet(user_text_clean, runtime_overrides=None)
        assistant_text = str(result.get("response") or "")
        used_model = model_id
    else:
        result = bridge.run_model(model_id, user_text, system_prompt=system_prompt, temperature=payload.get("temperature"))
        assistant_text = str(result.get("response") or result.get("error") or "")
        used_model = model_id

    root = Path(__file__).resolve().parents[1]
    chat_store.record_user_and_assistant(
        root,
        chat_id,
        user_text=user_text,
        assistant_text=assistant_text,
        model=used_model,
        system_prompt=system_prompt if system_prompt else None,
        attachments=attachments,
    )
    return {"status": "ok", "chat_id": chat_id, "model": used_model, "response": assistant_text}


@app.post("/assistant/chat/send_stream")
async def assistant_chat_send_stream(request: Request) -> Any:
    """
    SSE streaming version of chat send. (Today: chunks the final response.)
    """
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    chat_id = str(payload.get("chat_id") or "").strip()
    if not chat_id:
        chat_id = chat_store.new_chat_id()
    model_id = str(payload.get("model") or "assistant").strip()
    user_text = str(payload.get("message") or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="missing_message")
    attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
    attachments = [a for a in attachments if isinstance(a, dict)]

    # Compute full response first (v1). Then stream chunks for UX.
    if model_id in AWARNET_MODELS:
        user_text_clean = _sanitize_gateway_text(user_text)
        result = bridge.execute_awarenet(user_text_clean, runtime_overrides=None)
        assistant_text = str(result.get("response") or "")
        used_model = model_id
    else:
        result = bridge.run_model(model_id, user_text, system_prompt=None, temperature=payload.get("temperature"))
        assistant_text = str(result.get("response") or result.get("error") or "")
        used_model = model_id

    root = Path(__file__).resolve().parents[1]
    chat_store.record_user_and_assistant(
        root,
        chat_id,
        user_text=user_text,
        assistant_text=assistant_text,
        model=used_model,
        system_prompt=None,
        attachments=attachments,
    )

    async def gen():
        # Envelope: data: {"type":"meta|delta|final", ...}\n\n
        yield f"data: {json.dumps({'type':'meta','chat_id':chat_id,'model':used_model})}\n\n"
        chunk = ""
        for ch in assistant_text:
            chunk += ch
            if len(chunk) >= 48:
                yield f"data: {json.dumps({'type':'delta','delta':chunk})}\n\n"
                chunk = ""
                await asyncio.sleep(0.01)
        if chunk:
            yield f"data: {json.dumps({'type':'delta','delta':chunk})}\n\n"
        yield f"data: {json.dumps({'type':'final','chat_id':chat_id})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/assistant/chat/history")
async def assistant_chat_history(chat_id: str, limit: int = 200) -> Dict[str, Any]:
    chat_id = str(chat_id or "").strip()
    if not chat_id:
        raise HTTPException(status_code=400, detail="missing_chat_id")
    root = Path(__file__).resolve().parents[1]
    events = chat_store.list_events(root, chat_id, limit=limit)
    return {"status": "ok", "chat_id": chat_id, "events": events}


@app.get("/assistant/chat/list")
async def assistant_chat_list(limit: int = 200) -> Dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    d = root / "data" / "chats"
    if not d.exists():
        return {"status": "ok", "chats": []}
    chats = []
    for p in sorted(d.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        chats.append({"chat_id": p.stem, "mtime": p.stat().st_mtime, "size": p.stat().st_size})
    return {"status": "ok", "chats": chats[: max(1, int(limit))]}


@app.post("/assistant/chat/attachments")
async def assistant_chat_attachments(
    chat_id: str = Form(""),
    upload: UploadFile = File(...),
) -> Dict[str, Any]:
    """
    Upload an attachment for a chat. Stored locally and referenced by id.
    """
    chat_id = str(chat_id or "").strip() or chat_store.new_chat_id()
    root = Path(__file__).resolve().parents[1]
    base = root / "data" / "chat_attachments" / chat_id
    base.mkdir(parents=True, exist_ok=True)
    name = Path(upload.filename or "file").name
    att_id = f"att-{uuid4().hex}"
    out_path = base / f"{att_id}-{name}"
    content = await upload.read()
    out_path.write_bytes(content)
    return {
        "status": "ok",
        "chat_id": chat_id,
        "attachment": {
            "id": att_id,
            "name": name,
            "path": str(out_path),
            "size": out_path.stat().st_size,
            "content_type": str(upload.content_type or ""),
        },
    }


@app.get("/assistant/operator/artifacts")
async def assistant_operator_artifacts(task_id: str, tail: int = 50) -> Dict[str, Any]:
    """
    List recent artifact files for an operator task.
    """
    task_id = str(task_id or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="missing_task_id")
    root = Path(__file__).resolve().parents[1]
    d = (root / ".superpowers" / "operator" / task_id).resolve()
    if not d.exists():
        return {"status": "ok", "task_id": task_id, "artifacts_dir": str(d), "files": []}

    files = []
    try:
        for p in sorted(d.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_file():
                continue
            files.append(
                {
                    "name": p.name,
                    "size": p.stat().st_size,
                    "mtime": p.stat().st_mtime,
                    "path": str(p),
                }
            )
    except OSError:
        files = []
    if tail and tail > 0:
        files = files[: int(tail)]
    return {"status": "ok", "task_id": task_id, "artifacts_dir": str(d), "files": files}


@app.get("/assistant/operator/artifact/text")
async def assistant_operator_artifact_text(task_id: str, name: str, tail: int = 200) -> Dict[str, Any]:
    """
    Read a text artifact file under the operator artifacts directory.
    """
    task_id = str(task_id or "").strip()
    name = str(name or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="missing_task_id")
    if not name:
        raise HTTPException(status_code=400, detail="missing_name")
    root = Path(__file__).resolve().parents[1]
    d = (root / ".superpowers" / "operator" / task_id).resolve()
    p = (d / name).resolve()
    try:
        p.relative_to(d)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_path")
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="not_found")
    try:
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if tail and tail > 0:
        lines = lines[-int(tail) :]
    return {"status": "ok", "task_id": task_id, "name": name, "lines": lines}


@app.get("/assistant/operator/artifact/file")
async def assistant_operator_artifact_file(task_id: str, name: str) -> Any:
    """
    Download an artifact file under the operator artifacts directory (images, json, txt).
    """
    task_id = str(task_id or "").strip()
    name = str(name or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="missing_task_id")
    if not name:
        raise HTTPException(status_code=400, detail="missing_name")
    root = Path(__file__).resolve().parents[1]
    d = (root / ".superpowers" / "operator" / task_id).resolve()
    p = (d / name).resolve()
    try:
        p.relative_to(d)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_path")
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="not_found")
    return FileResponse(p)


@app.get("/assistant/desktop/windows")
async def assistant_desktop_windows() -> Dict[str, Any]:
    from tools.operator_tools import desktop_windows

    try:
        result = desktop_windows.list_windows()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "ok", "result": result}


@app.post("/assistant/desktop/launch")
async def assistant_desktop_launch(request: Request) -> Dict[str, Any]:
    from tools.operator_tools import desktop_windows

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    command = str(payload.get("command") or "").strip()
    if not command:
        raise HTTPException(status_code=400, detail="missing_command")
    try:
        result = desktop_windows.launch_app(command=command)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "ok", "result": result}


@app.post("/assistant/desktop/screenshot_full")
async def assistant_desktop_screenshot_full() -> Dict[str, Any]:
    from tools.operator_tools import desktop_windows

    try:
        result = desktop_windows.screenshot_full()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "ok", "result": result}


@app.post("/assistant/desktop/screenshot_window_title")
async def assistant_desktop_screenshot_window_title(request: Request) -> Dict[str, Any]:
    from tools.operator_tools import desktop_windows

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="missing_title")
    try:
        result = desktop_windows.screenshot_window_title(title=title)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "ok", "result": result}


def _strip_user_prefix(text: str) -> str:
    return USER_PREFIX.sub("", text).strip()


def _extract_request_tail(text: str) -> str:
    lowered = text.lower()
    for marker in REQUEST_MARKERS:
        idx = lowered.rfind(marker)
        if idx != -1:
            return text[idx + len(marker):].strip()
    return text


def _sanitize_gateway_text(text: str) -> str:
    if not text:
        return text
    lowered = text.lower()
    wrapped = CONTEXT_MARKER in lowered or any(marker in lowered for marker in REQUEST_MARKERS)
    text = _extract_request_tail(text)
    lowered = text.lower()
    if not any(marker.lower() in lowered for marker in GATEWAY_MARKERS):
        if wrapped:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if not lines:
                return text
            return _strip_user_prefix(lines[-1])
        return _strip_user_prefix(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return text
    # Prefer the last non-metadata line.
    for line in reversed(lines):
        if re.match(r"^(openclaw-control-ui|assistant|you|system:)", line, re.IGNORECASE):
            continue
        return _strip_user_prefix(line)
    return _strip_user_prefix(lines[-1])


def _normalize_gateway_path(path: str) -> str:
    if not path:
        return ""
    cleaned = path.strip()
    if not cleaned:
        return ""
    if "://" in cleaned:
        return ""
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    if not cleaned.startswith("/api/") and cleaned.count("/") == 1:
        cleaned = "/api" + cleaned
    return cleaned


def _last_gateway_error() -> Optional[Dict[str, Any]]:
    events = assistant_state.list_system_events(limit=200)
    for entry in reversed(events):
        if entry.get("source") == "gateway":
            return entry
    return None


def _model_catalog() -> list[str]:
    model_ids = bridge.list_models()
    for model_id in AWARNET_MODELS:
        if model_id not in model_ids:
            model_ids.append(model_id)
    return model_ids


def _extract_system_and_user(messages: Any) -> tuple[Optional[str], Optional[str]]:
    system_prompt = None
    user_text = None
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if role == "system" and system_prompt is None and isinstance(content, str):
                system_prompt = content
            if role == "user" and isinstance(content, str):
                user_text = content
    return system_prompt, user_text


@app.get("/awarenet/{full_path:path}")
async def awarenet_spa(full_path: str):
    if not UI_DIST.exists():
        raise HTTPException(status_code=404, detail="Awarenet UI not built")
    candidate = UI_DIST / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(UI_DIST / "index.html")


@app.get("/v1/models")
async def list_models() -> Dict[str, Any]:
    data = [{"id": model_id, "object": "model"} for model_id in _model_catalog()]
    return {"object": "list", "data": data}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    model_id = str(payload.get("model") or "assistant")
    messages = payload.get("messages") or []
    temperature = payload.get("temperature")
    runtime_overrides = payload.get("runtime_overrides")

    system_prompt, user_text = _extract_system_and_user(messages)
    if not user_text:
        user_text = str(payload.get("prompt") or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="No user message provided")

    if model_id in AWARNET_MODELS:
        user_text = _sanitize_gateway_text(user_text)
        result = bridge.execute_awarenet(
            user_text,
            runtime_overrides=runtime_overrides if isinstance(runtime_overrides, dict) else None,
        )
        content = result.get("response") or ""
        used_model = model_id
    else:
        result = bridge.run_model(model_id, user_text, system_prompt=system_prompt, temperature=temperature)
        content = result.get("response") or result.get("error") or ""
        used_model = model_id

    return {
        "id": f"chatcmpl-{uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": used_model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


@app.get("/runtime/settings")
async def get_runtime_settings() -> Dict[str, Any]:
    overrides = bridge.config_manager.config.get("awarenet_overrides", {})
    return {"awarenet_critique_enabled": bool(overrides.get("critique_enabled", True))}


@app.post("/runtime/settings")
async def update_runtime_settings(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if "awarenet_critique_enabled" in payload:
        value = bool(payload.get("awarenet_critique_enabled"))
        bridge.config_manager.update_awarenet_override("critique_enabled", value)
    bridge.reload_config()
    return await get_runtime_settings()


@app.get("/assistant/status")
async def assistant_status() -> Dict[str, Any]:
    return {
        "status": "ok",
        "policy": bridge.get_policy_state(),
        "proactive": proactive.status(),
        "memory": assistant_state.summary(),
    }


@app.post("/assistant/execute")
async def assistant_execute(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    result = bridge.execute_action_payload(payload)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Execution failed")
    return result


@app.get("/assistant/memory")
async def assistant_memory(full: bool = False) -> Dict[str, Any]:
    if full:
        return {"status": "ok", "state": assistant_state.get_state()}
    return {"status": "ok", "summary": assistant_state.summary()}


@app.post("/assistant/memory")
async def assistant_memory_update(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    updated = {}
    prefs = payload.get("preferences")
    if isinstance(prefs, dict):
        updated["preferences"] = assistant_state.update_preferences(prefs)
    note = payload.get("note")
    if isinstance(note, str) and note.strip():
        updated["note"] = assistant_state.add_note(note.strip(), source="api")
    return {"status": "ok", "updated": updated}


@app.get("/assistant/tasks")
async def assistant_tasks(include_history: bool = False) -> Dict[str, Any]:
    return {"status": "ok", "tasks": assistant_state.list_tasks(include_history=include_history)}


@app.post("/assistant/tasks")
async def assistant_tasks_create(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    description = str(payload.get("description") or "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="Task description required")
    priority = str(payload.get("priority") or "medium")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    task = assistant_state.add_task(description, priority=priority, metadata=metadata)
    return {"status": "ok", "task": task}


@app.get("/assistant/policy")
async def assistant_policy() -> Dict[str, Any]:
    return {"status": "ok", "policy": bridge.get_policy_state()}


@app.post("/assistant/policy")
async def assistant_policy_update(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    policy = bridge.update_policy(payload)
    return {"status": "ok", "policy": policy}


@app.get("/assistant/approvals")
async def assistant_approvals(include_history: bool = False) -> Dict[str, Any]:
    return {"status": "ok", "approvals": assistant_state.list_approvals(include_history=include_history)}


@app.post("/assistant/approvals/resolve")
async def assistant_approvals_resolve(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    approval_id = str(payload.get("id") or "").strip()
    approved = bool(payload.get("approved", False))
    note = str(payload.get("note") or "").strip()
    entry = assistant_state.resolve_approval(approval_id, approved=approved, note=note)
    if not entry:
        raise HTTPException(status_code=404, detail="approval_not_found")
    return {"status": "ok", "approval": entry}


@app.post("/assistant/approvals/continue")
async def assistant_approvals_continue(request: Request) -> Dict[str, Any]:
    """
    Resolve an approval as approved and immediately execute its stored operator plan step.

    Body: { "id": "...", "note": "..."? }
    """
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    approval_id = str(payload.get("id") or "").strip()
    note = str(payload.get("note") or "").strip()
    if not approval_id:
        raise HTTPException(status_code=400, detail="missing_id")

    approval = assistant_state.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="approval_not_found")

    resolved = assistant_state.resolve_approval(approval_id, approved=True, note=note)
    plan = {}
    if isinstance(approval.get("payload"), dict):
        plan = approval["payload"].get("plan") if isinstance(approval["payload"].get("plan"), dict) else {}
    if not plan:
        return {"status": "ok", "approval": resolved, "executed": False, "error": "missing_plan_payload"}

    task_id = ""
    active = assistant_state.get_operator_state(include_history=False).get("active")
    if isinstance(active, dict):
        task_id = str(active.get("task_id") or "")
    # Allow overriding task_id if present in payload
    if isinstance(plan.get("action"), dict) and isinstance(plan.get("action").get("task_id"), str):
        task_id = str(plan["action"]["task_id"])
    if not task_id:
        # Fallback: if approval payload had task id stored in detail
        task_id = str(approval.get("detail") or "").split()[-1]

    try:
        step = PlanStep(
            goal=str(plan.get("goal") or "approved_step"),
            step_id=str(plan.get("step_id") or "approved"),
            tool=str(plan.get("tool") or "shell"),  # type: ignore[arg-type]
            action=plan.get("action") if isinstance(plan.get("action"), dict) else {},
            risk=("risky" if str(plan.get("risk") or "normal") == "risky" else "normal"),  # type: ignore[arg-type]
            success_criteria=str(plan.get("success_criteria") or ""),
        )
        result = await operator.execute_plan_step_async(task_id, step)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"status": "ok", "approval": resolved, "executed": True, "result": result}


@app.post("/assistant/operator/start")
async def assistant_operator_start(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    goal = str(payload.get("goal") or "").strip()
    if not goal:
        raise HTTPException(status_code=400, detail="missing_goal")
    return {"status": "ok", **operator.start_task(goal, source="api")}


@app.get("/assistant/operator/state")
async def assistant_operator_state(include_history: bool = False) -> Dict[str, Any]:
    return {"status": "ok", "operator": assistant_state.get_operator_state(include_history=include_history)}


@app.get("/assistant/editor/health")
async def assistant_editor_health() -> Dict[str, Any]:
    from tools.operator_tools import editor_bridge

    return {"status": "ok", "health": editor_bridge.health(bridge.config_manager.config)}


@app.get("/assistant/lessons")
async def assistant_lessons(tail: int = 50) -> Dict[str, Any]:
    """
    Return the last N lessons learned (JSONL).
    """
    path = Path(__file__).resolve().parents[1] / "data" / "lessons_learned.jsonl"
    if not path.exists():
        return {"status": "ok", "lessons": []}
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if tail and tail > 0:
        lines = lines[-tail:]
    lessons = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            lessons.append(json.loads(line))
        except Exception:
            continue
    return {"status": "ok", "lessons": lessons}


@app.post("/assistant/operator/troubleshoot")
async def assistant_operator_troubleshoot(request: Request) -> Dict[str, Any]:
    """
    Build a local diagnosis bundle and optionally run research triangulation.

    Body:
      {
        "task_id": "...",
        "fetch_urls": false,
        "sources": [ {title,url,snippet,credibility} ],
        "error_signature": "..."
      }
    """
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="missing_task_id")

    op = assistant_state.get_operator_state(include_history=False).get("active")
    artifacts_dir = ""
    if isinstance(op, dict) and op.get("task_id") == task_id:
        artifacts_dir = str(op.get("artifacts_dir") or "")
    if not artifacts_dir:
        # best effort: infer artifacts dir
        artifacts_dir = str(Path(__file__).resolve().parents[1] / ".superpowers" / "operator" / task_id)

    root = Path(__file__).resolve().parents[1]
    bundle = operator_troubleshoot.build_local_diagnosis_bundle(
        root=root,
        task_id=task_id,
        artifacts_dir=artifacts_dir,
        include_history=False,
    )
    diag_path = operator_troubleshoot.write_diagnostic_bundle(Path(artifacts_dir), bundle)

    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    fetch_urls = bool(payload.get("fetch_urls", False))
    error_signature = str(payload.get("error_signature") or "").strip() or str(bundle.get("task_id"))
    research = None
    candidates = None
    if sources:
        research = research_runner.run_research(
            error_signature=error_signature,
            environment={"os": os.name, "task_id": task_id},
            sources=sources,
            fetch_urls=fetch_urls,
        )
        operator_troubleshoot.write_diagnostic_bundle(Path(artifacts_dir), {"research": research})

        # Candidate fix generation (LLM) from ranked sources.
        try:
            sys = (
                "You are Awarenet Fix Candidate Generator. Return STRICT JSON only.\n"
                "Output schema: {\"candidates\":[{\"kind\":\"config_change|shell_step|editor_step|manual\",\"description\":\"...\",\"risk\":\"normal|risky\",\"payload\":{...}}]}\n"
                "Rules:\n"
                "- Provide 1-5 candidates, least risky first.\n"
                "- For shell_step/editor_step, payload must be {\"step\":{...}} using the operator PlanStep shape.\n"
                "- For config_change, payload must be {\"updates\":{...}}.\n"
                "- Use environment and error_signature.\n"
                "- Do not include extra keys.\n"
            )
            prompt = (
                f"Error signature:\n{error_signature}\n\n"
                f"Environment:\n{json.dumps({'os': os.name, 'task_id': task_id})}\n\n"
                f"Triangulation:\n{json.dumps(research.get('triangulation') if isinstance(research, dict) else {})}\n\n"
                "Return JSON."
            )
            out = bridge.run_model("assistant", prompt, system_prompt=sys, temperature=0.1, keep_alive="0s")
            raw = str(out.get("response") or "").strip()
            candidates = json.loads(raw) if raw else None
        except Exception:
            candidates = None

    return {"status": "ok", "diagnostic_path": diag_path, "bundle": bundle, "research": research, "candidates": candidates}


@app.post("/assistant/operator/autofix")
async def assistant_operator_autofix(request: Request) -> Dict[str, Any]:
    """
    Execute a list of fix attempts (policy-gated) and persist results.

    Body:
      {
        "task_id": "...",
        "error_signature": "...",
        "sources": [ {title,url} ],
        "attempts": [ { kind, description, risk?, payload? } ]
      }
    """
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="missing_task_id")
    error_signature = str(payload.get("error_signature") or "").strip() or task_id
    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    attempts_raw = payload.get("attempts") if isinstance(payload.get("attempts"), list) else []
    attempts: list[FixAttempt] = []
    now = time.time()
    for item in attempts_raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip() or "manual"
        desc = str(item.get("description") or "").strip() or kind
        risk = str(item.get("risk") or "normal").strip()
        pl = item.get("payload") if isinstance(item.get("payload"), dict) else None
        attempts.append(FixAttempt(ts=now, kind=kind, description=desc, risk=risk, payload=pl, result=None))  # type: ignore[arg-type]

    root = Path(__file__).resolve().parents[1]
    result = await fix_executor.execute_fix_attempts(
        root=root,
        task_id=task_id,
        operator=operator,
        attempts=attempts,
        error_signature=error_signature,
        sources=sources if all(isinstance(s, dict) for s in sources) else [],
    )
    return {"status": "ok", "result": result}


@app.post("/assistant/voice/speak")
async def assistant_voice_speak(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="missing_text")
    cfg = bridge.config_manager.config.get("voice", {}) if isinstance(bridge.config_manager.config.get("voice"), dict) else {}
    artifacts_dir = Path(__file__).resolve().parents[1] / ".superpowers" / "voice"
    result = voice.speak(
        text=text,
        artifacts_dir=artifacts_dir,
        rate=cfg.get("tts_rate"),
        voice_name_contains=str(cfg.get("tts_voice_name_contains") or "").strip() or None,
    )
    return {"status": "ok", "result": result}


@app.post("/assistant/voice/listen_once")
async def assistant_voice_listen_once(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    cfg = bridge.config_manager.config.get("voice", {}) if isinstance(bridge.config_manager.config.get("voice"), dict) else {}
    artifacts_dir = Path(__file__).resolve().parents[1] / ".superpowers" / "voice"
    seconds = int(payload.get("seconds") or cfg.get("listen_seconds") or 5)
    result = voice.listen_once(
        artifacts_dir=artifacts_dir,
        vosk_model_path=str(cfg.get("vosk_model_path") or ""),
        seconds=seconds,
        sample_rate=int(cfg.get("sample_rate") or 16000),
    )
    return {"status": "ok", "result": result}


@app.post("/assistant/voice/command")
async def assistant_voice_command(request: Request) -> Dict[str, Any]:
    """
    Run a voice command (already transcribed text) through the operator loop.
    """
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="missing_text")
    max_steps = int(payload.get("max_steps") or 12)
    result = await bridge.execute_operator(text, max_steps=max_steps)
    return {"status": "ok", "result": result}


@app.post("/assistant/operator/browser/open_url")
async def assistant_operator_browser_open_url(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    task_id = str(payload.get("task_id") or "").strip()
    url = str(payload.get("url") or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="missing_task_id")
    if not url:
        raise HTTPException(status_code=400, detail="missing_url")
    step = PlanStep(
        goal="open_url",
        step_id="open_url_screenshot",
        tool="browser",
        action={"type": "open_url_screenshot", "url": url},
        risk="normal",
        success_criteria="Page opened and screenshot captured",
    )
    result = await operator.execute_plan_step_async(task_id, step)
    return {"status": "ok", **result}


@app.post("/assistant/operator/step")
async def assistant_operator_step(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="missing_task_id")
    tool = str(payload.get("tool") or "").strip()
    action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
    goal = str(payload.get("goal") or "").strip() or "operator_step"
    step_id = str(payload.get("step_id") or "").strip() or "step"
    risk = str(payload.get("risk") or "normal").strip().lower()
    risk = "risky" if risk == "risky" else "normal"
    success_criteria = str(payload.get("success_criteria") or "").strip()
    if tool not in {"browser", "shell", "editor", "desktop"}:
        raise HTTPException(status_code=400, detail="invalid_tool")
    step = PlanStep(
        goal=goal,
        step_id=step_id,
        tool=tool,  # type: ignore[arg-type]
        action=action,
        risk=risk,  # type: ignore[arg-type]
        success_criteria=success_criteria,
    )
    result = await operator.execute_plan_step_async(task_id, step)
    return {"status": "ok", **result}


@app.post("/assistant/operator/execute")
async def assistant_operator_execute(request: Request) -> Dict[str, Any]:
    """
    Run the planner→operator loop for a goal.
    """
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    goal = str(payload.get("goal") or "").strip()
    if not goal:
        raise HTTPException(status_code=400, detail="missing_goal")
    max_steps = int(payload.get("max_steps") or 12)
    result = await bridge.execute_operator(goal, max_steps=max_steps)
    return {"status": "ok", "result": result}


@app.post("/assistant/operator/gmail/draft_leave")
async def assistant_operator_gmail_draft_leave(request: Request) -> Dict[str, Any]:
    """
    Draft a leave email in Gmail compose WITHOUT sending.

    Uses system Chrome profile when configured in payload options so the "default Chrome account"
    can already be signed in.
    """
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    task_id = str(payload.get("task_id") or "").strip()
    to = str(payload.get("to") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="missing_task_id")
    if not to:
        raise HTTPException(status_code=400, detail="missing_to")
    if not subject:
        raise HTTPException(status_code=400, detail="missing_subject")
    if not body:
        raise HTTPException(status_code=400, detail="missing_body")

    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    # Default: try using system Chrome profile headful (so user can see it)
    merged_options = {
        "headless": bool(options.get("headless", False)),
        "use_system_chrome_profile": bool(options.get("use_system_chrome_profile", True)),
        "chrome_profile_directory": str(options.get("chrome_profile_directory") or "Default"),
    }

    actions = recipes.gmail_draft_actions(to=to, subject=subject, body=body)

    step = PlanStep(
        goal="gmail_draft_leave",
        step_id="gmail_compose_draft",
        tool="browser",
        action={"type": "browser_actions", "options": merged_options, "actions": actions},
        risk="normal",
        success_criteria="Gmail compose opened and fields filled (no send)",
    )
    result = await operator.execute_plan_step_async(task_id, step)
    return {"status": "ok", **result}


@app.get("/assistant/models/status")
async def assistant_models_status() -> Dict[str, Any]:
    return {"status": "ok", "models": bridge.get_model_status()}


@app.get("/assistant/models/history")
async def assistant_models_history(since: Optional[str] = None, limit: int = 2000) -> Dict[str, Any]:
    return {"status": "ok", "history": assistant_state.list_model_events(since=since, limit=limit)}


@app.get("/assistant/logs/action")
async def assistant_logs_action(since: Optional[str] = None, limit: int = 2000) -> Dict[str, Any]:
    return {"status": "ok", "logs": assistant_state.list_action_logs(since=since, limit=limit)}


@app.get("/assistant/logs/system")
async def assistant_logs_system(since: Optional[str] = None, limit: int = 2000) -> Dict[str, Any]:
    return {"status": "ok", "logs": assistant_state.list_system_events(since=since, limit=limit)}


@app.get("/assistant/logs/proactive")
async def assistant_logs_proactive(since: Optional[str] = None, limit: int = 2000) -> Dict[str, Any]:
    logs = [log for log in assistant_state.list_action_logs(since=since, limit=limit * 2) if log.get("source") == "proactive"]
    return {"status": "ok", "logs": logs[-limit:]}


@app.get("/assistant/logs/files")
async def assistant_logs_files(path: Optional[str] = None, tail: int = 200) -> Dict[str, Any]:
    if not path:
        files = []
        if LOGS_DIR.exists():
            for file in LOGS_DIR.glob("*"):
                if file.is_file():
                    files.append({"name": file.name, "size": file.stat().st_size})
        return {"status": "ok", "files": files}
    safe_path = _safe_log_path(path)
    if not safe_path:
        raise HTTPException(status_code=400, detail="Invalid log path")
    try:
        lines = safe_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if tail > 0:
        lines = lines[-tail:]
    return {"status": "ok", "path": safe_path.name, "lines": lines}


@app.get("/assistant/config")
async def assistant_config() -> Dict[str, Any]:
    return {"status": "ok", "config": bridge.get_safe_config(), "snapshots": config_store.list_snapshots()}


@app.post("/assistant/config")
async def assistant_config_update(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    updated = _apply_config_updates(payload)
    return {"status": "ok", "config": updated}


@app.post("/assistant/config/snapshot")
async def assistant_config_snapshot() -> Dict[str, Any]:
    snapshot = config_store.add_snapshot(bridge.get_safe_config())
    return {"status": "ok", "snapshot": snapshot}


@app.get("/assistant/config/snapshots")
async def assistant_config_snapshots() -> Dict[str, Any]:
    return {"status": "ok", "snapshots": config_store.list_snapshots()}


@app.post("/assistant/config/restore")
async def assistant_config_restore(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    snapshot_id = str(payload.get("id") or "")
    snapshot = config_store.get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    updated = _apply_config_updates(snapshot.get("config") or {})
    return {"status": "ok", "config": updated}


@app.get("/assistant/openclaw/health")
async def assistant_openclaw_health() -> Dict[str, Any]:
    url = bridge.gateway_base_url()
    last_error = _last_gateway_error()
    try:
        response = requests.get(url, timeout=5)
        return {
            "status": "ok",
            "code": response.status_code,
            "base_url": url,
            "hint": f"{url}/api/status",
            "last_error": last_error,
        }
    except requests.RequestException as exc:
        return {
            "status": "error",
            "message": str(exc),
            "base_url": url,
            "hint": f"{url}/api/status",
            "last_error": last_error,
        }


@app.post("/assistant/openclaw/proxy")
async def assistant_openclaw_proxy(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    method = str(payload.get("method") or "GET").upper()
    if method not in {"GET", "POST"}:
        raise HTTPException(status_code=400, detail="Only GET/POST supported")
    path = str(payload.get("path") or "")
    normalized_path = _normalize_gateway_path(path)
    if not normalized_path:
        raise HTTPException(status_code=400, detail="Invalid path")
    base = bridge.gateway_base_url()
    url = base + normalized_path
    query = payload.get("query") if isinstance(payload.get("query"), dict) else None
    headers = payload.get("headers") if isinstance(payload.get("headers"), dict) else None
    body = payload.get("body")
    try:
        response = requests.request(method, url, params=query, headers=headers, json=body, timeout=15)
    except requests.RequestException as exc:
        assistant_state.add_system_event("error", "Gateway proxy failed", source="gateway", detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    content_type = response.headers.get("content-type", "")
    data: Any
    if "application/json" in content_type:
        data = response.json()
    else:
        data = response.text
    if response.status_code >= 400:
        assistant_state.add_system_event(
            "error",
            f"Gateway proxy HTTP {response.status_code}",
            source="gateway",
            detail=str(data)[:500],
        )
    section = str(payload.get("section") or "")
    if section:
        assistant_state.set_gateway_cache(section, data)
    return {
        "status": "ok",
        "code": response.status_code,
        "requested_path": path,
        "normalized_path": normalized_path,
        "url": url,
        "data": data,
    }


@app.get("/assistant/skills/status")
async def assistant_skills_status() -> Dict[str, Any]:
    state = skills_state.get_state()
    return {"status": "ok", "settings": bridge.get_safe_config().get("skills", {}), "state": state}


@app.get("/assistant/skills/settings")
async def assistant_skills_settings() -> Dict[str, Any]:
    return {"status": "ok", "settings": bridge.get_safe_config().get("skills", {})}


@app.post("/assistant/skills/settings")
async def assistant_skills_settings_update(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    updated = _apply_config_updates({"skills": payload})
    return {"status": "ok", "settings": updated.get("skills", {})}


@app.get("/assistant/skills/installed")
async def assistant_skills_installed() -> Dict[str, Any]:
    return {"status": "ok", **skills_manager.list_installed()}


@app.get("/assistant/skills/search")
async def assistant_skills_search(query: str) -> Dict[str, Any]:
    return {"status": "ok", **skills_manager.search(query)}


@app.post("/assistant/skills/scan")
async def assistant_skills_scan(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    query = str(payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query required")
    source = str(payload.get("source") or "manual")
    return {"status": "ok", **skills_manager.scan(query, source=source)}


@app.post("/assistant/skills/install")
async def assistant_skills_install(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    skill_id = str(payload.get("skill") or "").strip()
    if not skill_id:
        raise HTTPException(status_code=400, detail="Skill id required")
    return {"status": "ok", **skills_manager.install(skill_id)}


@app.post("/assistant/skills/update")
async def assistant_skills_update(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    skill_id = str(payload.get("skill") or "").strip()
    return {"status": "ok", **skills_manager.update(skill_id or None)}


@app.get("/assistant/skills/history")
async def assistant_skills_history() -> Dict[str, Any]:
    state = skills_state.get_state()
    return {"status": "ok", "history": state.get("history", [])}


@app.get("/assistant/skills/approvals")
async def assistant_skills_approvals(status: Optional[str] = None) -> Dict[str, Any]:
    return {"status": "ok", "approvals": skills_state.list_approvals(status=status)}


@app.post("/assistant/skills/approvals")
async def assistant_skills_approvals_update(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    approval_id = str(payload.get("id") or "").strip()
    action = str(payload.get("action") or "").strip().lower()
    if not approval_id or action not in {"approved", "denied"}:
        raise HTTPException(status_code=400, detail="Approval id and action required")
    return {"status": "ok", **skills_manager.process_approval(approval_id, action)}


@app.get("/assistant/proactive/status")
async def assistant_proactive_status() -> Dict[str, Any]:
    return {"status": "ok", "proactive": proactive.status()}


@app.post("/assistant/proactive/start")
async def assistant_proactive_start() -> Dict[str, Any]:
    started = proactive.start()
    return {"status": "ok", "started": started, "proactive": proactive.status()}


@app.post("/assistant/proactive/stop")
async def assistant_proactive_stop() -> Dict[str, Any]:
    stopped = proactive.stop()
    return {"status": "ok", "stopped": stopped, "proactive": proactive.status()}


@app.get("/assistant/vscode/context")
async def assistant_vscode_context() -> Dict[str, Any]:
    state = assistant_state.get_state()
    vscode = state.get("vscode", {})
    return {"status": "ok", "vscode": vscode}


@app.post("/assistant/vscode/context")
async def assistant_vscode_context_update(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    entry = assistant_state.record_vscode_context(payload)
    return {"status": "ok", "entry": entry}


@app.on_event("shutdown")
async def shutdown_event() -> None:
    proactive.stop()
    bridge.shutdown()


@app.on_event("startup")
async def startup_event() -> None:
    config = bridge.config_manager.config
    proactive_cfg = config.get("assistant_proactive", {}) if isinstance(config.get("assistant_proactive"), dict) else {}
    skills_cfg = config.get("skills", {}) if isinstance(config.get("skills"), dict) else {}
    if proactive_cfg.get("enabled") or skills_cfg.get("schedule_enabled"):
        proactive.start()
