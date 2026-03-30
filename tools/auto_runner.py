import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pyautogui
import pyperclip

from tools import self_improve
from tools import assistant_state

pyautogui.FAILSAFE = True

INSTRUCTION_HEADER = "OPENCLAW_INSTRUCTIONS"

APP_ALIASES = {
    "vmware": "vmware",
    "vmware workstation": "vmware",
    "vmware player": "vmware",
    "firefox": "firefox",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "notepad": "notepad",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "vscode": "code",
    "visual studio code": "code",
}


@dataclass
class ActionResult:
    action: str
    status: str
    detail: str = ""


def _find_chrome_path() -> str:
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return "chrome"

def _find_chrome_profile(prefer_default: bool = False) -> str:
    local_state = Path(os.path.expandvars(r"%LocalAppData%\Google\Chrome\User Data\Local State"))
    if local_state.exists():
        try:
            data = json.loads(local_state.read_text(encoding="utf-8"))
            profile = data.get("profile", {})
            if not prefer_default:
                last_used = profile.get("last_used")
                if isinstance(last_used, str) and last_used.strip():
                    return last_used
            # fall back to default profile
            return "Default"
        except Exception:  # noqa: BLE001
            return "Default"
    return "Default"

def _find_vmware_path() -> str:
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\VMware\VMware Workstation\vmware.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\VMware\VMware Workstation\vmware.exe"),
        os.path.expandvars(r"%ProgramFiles%\VMware\VMware Player\vmplayer.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\VMware\VMware Player\vmplayer.exe"),
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return "vmware"

def _find_vscode_path() -> str:
    candidates = [
        os.path.expandvars(r"%LocalAppData%\Programs\Microsoft VS Code\Code.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft VS Code\Code.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe"),
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return "code"


def _start_process(cmd: List[str]) -> None:
    subprocess.Popen(cmd, shell=False)


def _open_url(url: str, profile: str = "") -> None:
    chrome = _find_chrome_path()
    if profile:
        _start_process([chrome, f'--profile-directory={profile}', url])
    else:
        _start_process([chrome, url])


def _extract_profile(action: str) -> str:
    lowered = action.lower()
    if "default profile" in lowered or "default account" in lowered:
        return "Default"
    match = re.search(r"profile\s*[:=]?\s*([\w\s-]+)", action, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _open_path(path: str) -> None:
    if os.path.isdir(path) or os.path.isfile(path):
        _start_process(["explorer.exe", path])
        return
    _start_process([path])


def _type_text(text: str) -> None:
    pyperclip.copy(text)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")


def _extract_instruction_lines(text: str) -> List[str]:
    if INSTRUCTION_HEADER not in text:
        return []
    _, tail = text.split(INSTRUCTION_HEADER, 1)
    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    cleaned = []
    for line in lines:
        line = re.sub(r"^\d+\.\s*", "", line)
        if line:
            cleaned.append(line)
    return cleaned


def _resolve_app_name(action: str) -> str:
    lowered = action.lower().strip()
    if "vmware" in lowered:
        return _find_vmware_path()
    if "vscode" in lowered or "visual studio code" in lowered:
        return _find_vscode_path()
    for key, value in APP_ALIASES.items():
        if key in lowered:
            return value
    return action.strip()


def _policy_allows(policy: Optional[Callable[[str], Dict[str, Any]]], action: str) -> Optional[Dict[str, Any]]:
    if not policy:
        return None
    try:
        return policy(action)
    except Exception:
        return {"allowed": True, "risk": "unknown", "reason": "policy_error"}


def _record_result(result: ActionResult, source: str) -> None:
    assistant_state.add_action_log(
        action=result.action,
        status=result.status,
        detail=result.detail or "",
        source=source,
    )


def execute_instructions(
    text: str,
    *,
    policy: Optional[Callable[[str], Dict[str, Any]]] = None,
    source: str = "instructions",
) -> List[ActionResult]:
    actions = _extract_instruction_lines(text)
    results: List[ActionResult] = []
    for action in actions:
        decision = _policy_allows(policy, action)
        if decision and not decision.get("allowed", True):
            result = ActionResult(action, "blocked", decision.get("reason", "blocked"))
            results.append(result)
            _record_result(result, source)
            continue
        lowered = action.lower()
        try:
            if lowered.startswith("open vscode"):
                match = re.search(r"([a-zA-Z]:[\\/][^\s]+)", action)
                vscode = _find_vscode_path()
                if match:
                    _start_process([vscode, match.group(1)])
                else:
                    _start_process([vscode])
                result = ActionResult(action, "ok")
                results.append(result)
                _record_result(result, source)
                continue
            if lowered.startswith("open chrome"):
                profile = _extract_profile(action)
                if not profile:
                    prefer_default = "default profile" in lowered or "default account" in lowered
                    profile = _find_chrome_profile(prefer_default=prefer_default)
                _open_url("chrome://newtab", profile=profile)
                result = ActionResult(action, "ok")
                results.append(result)
                _record_result(result, source)
                continue
            if lowered.startswith("go to") or "mail.google.com" in lowered or "gmail.com" in lowered:
                match = re.search(r"(https?://\S+|\b\w+\.\w+\S*)", action)
                url = match.group(1) if match else "mail.google.com"
                if not url.startswith("http"):
                    url = "https://" + url
                profile = _extract_profile(action)
                if not profile:
                    prefer_default = "default profile" in lowered or "default account" in lowered
                    profile = _find_chrome_profile(prefer_default=prefer_default)
                _open_url(url, profile=profile)
                result = ActionResult(action, "ok")
                results.append(result)
                _record_result(result, source)
                continue
            if lowered.startswith("open ") and ":\\" in lowered:
                path = action[5:].strip().strip('"')
                _open_path(path)
                result = ActionResult(action, "ok")
                results.append(result)
                _record_result(result, source)
                continue
            if lowered.startswith("open "):
                app = _resolve_app_name(action[5:].strip())
                _open_path(app)
                result = ActionResult(action, "ok")
                results.append(result)
                _record_result(result, source)
                continue
            if lowered.startswith("run "):
                cmd = action[4:].strip()
                subprocess.Popen(cmd, shell=True)
                result = ActionResult(action, "ok")
                results.append(result)
                _record_result(result, source)
                continue
            if lowered.startswith("type "):
                text_to_type = action[5:].strip()
                _type_text(text_to_type)
                result = ActionResult(action, "ok")
                results.append(result)
                _record_result(result, source)
                continue
            if lowered.startswith("click "):
                result = ActionResult(action, "skipped", "click requires coordinates")
                results.append(result)
                _record_result(result, source)
                continue
            result = ActionResult(action, "skipped", "unknown action")
            results.append(result)
            _record_result(result, source)
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
            result = ActionResult(action, "error", detail)
            results.append(result)
            _record_result(result, source)
            if "WinError 2" in detail or "cannot find the file" in detail.lower():
                self_improve.note_suggestion(
                    f"Action failed: {action} ({detail})",
                    "Add or auto-detect the correct app path to make this action reliable.",
                )
    return results


def _action_to_string(action: Any) -> str:
    if isinstance(action, str):
        return action.strip()
    if not isinstance(action, dict):
        return ""
    command = str(action.get("command") or "").strip()
    if command:
        return command
    action_type = str(action.get("type") or "").strip().lower()
    target = str(action.get("target") or "").strip()
    text = str(action.get("text") or "").strip()
    if action_type in {"open", "run", "type", "click", "go", "navigate"}:
        if action_type == "type" and text:
            return f"type {text}"
        if action_type in {"go", "navigate"} and target:
            return f"go to {target}"
        if target:
            return f"{action_type} {target}"
    if text:
        return text
    return ""


def execute_action_payload(
    payload: Dict[str, Any],
    *,
    policy: Optional[Callable[[str], Dict[str, Any]]] = None,
    source: str = "api",
) -> List[ActionResult]:
    if not isinstance(payload, dict):
        return []
    if "instructions" in payload and isinstance(payload.get("instructions"), str):
        return execute_instructions(payload["instructions"], policy=policy, source=source)
    actions_raw = payload.get("actions")
    if not isinstance(actions_raw, list):
        return []
    actions = [a for a in (_action_to_string(item) for item in actions_raw) if a]
    results: List[ActionResult] = []
    for action in actions:
        results.extend(execute_instructions(f"{INSTRUCTION_HEADER}\n1. {action}", policy=policy, source=source))
    return results

