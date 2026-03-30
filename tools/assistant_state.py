from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "assistant_state.json"
MAX_ACTION_LOG = 500
MAX_TASK_HISTORY = 200
MAX_VSCODE_HISTORY = 50
MAX_NOTES = 200
MAX_MODEL_EVENTS = 500
MAX_SYSTEM_EVENTS = 500
MAX_GATEWAY_CACHE = 50
MAX_OPERATOR_HISTORY = 200
MAX_APPROVAL_HISTORY = 500


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> Dict[str, Any]:
    return {
        "preferences": {},
        "tasks": {"queue": [], "history": []},
        "action_log": [],
        "approvals": {"pending": [], "history": []},
        "operator": {"active": None, "history": []},
        "model_events": [],
        "system_events": [],
        "gateway_cache": {},
        "vscode": {"last": None, "history": []},
        "notes": [],
        "status": {},
        "updated_at": _now_iso(),
    }


def _ensure_shape(state: Dict[str, Any]) -> Dict[str, Any]:
    state.setdefault("preferences", {})
    state.setdefault("tasks", {"queue": [], "history": []})
    state.setdefault("action_log", [])
    state.setdefault("approvals", {"pending": [], "history": []})
    state.setdefault("operator", {"active": None, "history": []})
    state.setdefault("model_events", [])
    state.setdefault("system_events", [])
    state.setdefault("gateway_cache", {})
    state.setdefault("vscode", {"last": None, "history": []})
    state.setdefault("notes", [])
    state.setdefault("status", {})
    state.setdefault("updated_at", _now_iso())
    return state


def _load_state() -> Dict[str, Any]:
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return _ensure_shape(data)
        except json.JSONDecodeError:
            pass
    return _default_state()


def _save_state(state: Dict[str, Any]) -> None:
    state["updated_at"] = _now_iso()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_state() -> Dict[str, Any]:
    return _load_state()


def summary() -> Dict[str, Any]:
    state = _load_state()
    tasks = state.get("tasks", {})
    queue = tasks.get("queue") or []
    history = tasks.get("history") or []
    vscode = state.get("vscode")
    vscode_last = None
    if isinstance(vscode, dict):
        last = vscode.get("last")
        if isinstance(last, dict):
            vscode_last = last.get("ts")
    return {
        "updated_at": state.get("updated_at"),
        "tasks_pending": len(queue),
        "tasks_completed": len([t for t in history if t.get("status") == "completed"]),
        "action_log_count": len(state.get("action_log") or []),
        "model_event_count": len(state.get("model_events") or []),
        "system_event_count": len(state.get("system_events") or []),
        "notes_count": len(state.get("notes") or []),
        "vscode_last_ts": vscode_last,
    }


def _parse_since(since: Optional[str]) -> Optional[datetime]:
    if not since:
        return None
    try:
        return datetime.fromisoformat(since)
    except ValueError:
        return None


def _filter_entries(entries: List[Dict[str, Any]], since: Optional[str], limit: int) -> List[Dict[str, Any]]:
    cutoff = _parse_since(since)
    if cutoff:
        filtered = []
        for entry in entries:
            ts = entry.get("ts")
            if not ts:
                continue
            try:
                entry_dt = datetime.fromisoformat(ts)
            except ValueError:
                continue
            if entry_dt >= cutoff:
                filtered.append(entry)
    else:
        filtered = list(entries)
    if limit <= 0:
        return filtered
    return filtered[-limit:]


def update_preferences(prefs: Dict[str, Any]) -> Dict[str, Any]:
    state = _load_state()
    store = state.setdefault("preferences", {})
    store.update(prefs or {})
    _save_state(state)
    return store


def add_note(note: str, source: str = "user") -> Dict[str, Any]:
    if not note:
        return {}
    state = _load_state()
    entry = {"id": uuid4().hex, "note": note.strip(), "source": source, "ts": _now_iso()}
    notes = state.setdefault("notes", [])
    notes.append(entry)
    if len(notes) > MAX_NOTES:
        state["notes"] = notes[-MAX_NOTES:]
    _save_state(state)
    return entry


def add_task(description: str, priority: str = "medium", metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    desc = (description or "").strip()
    if not desc:
        return {}
    state = _load_state()
    task = {
        "id": f"task_{int(time.time())}_{uuid4().hex[:6]}",
        "description": desc,
        "priority": priority,
        "status": "pending",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "metadata": metadata or {},
    }
    queue = state.setdefault("tasks", {}).setdefault("queue", [])
    queue.append(task)
    _save_state(state)
    return task


def list_tasks(include_history: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    state = _load_state()
    tasks = state.get("tasks", {})
    queue = tasks.get("queue") or []
    history = tasks.get("history") or []
    return {"queue": list(queue), "history": list(history) if include_history else []}


def update_task(task_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not task_id:
        return None
    state = _load_state()
    tasks = state.setdefault("tasks", {})
    queue = tasks.setdefault("queue", [])
    history = tasks.setdefault("history", [])
    for idx, task in enumerate(queue):
        if task.get("id") == task_id:
            task.update(updates or {})
            task["updated_at"] = _now_iso()
            status = task.get("status")
            if status in {"completed", "cancelled"}:
                history.append(task)
                queue.pop(idx)
                if len(history) > MAX_TASK_HISTORY:
                    tasks["history"] = history[-MAX_TASK_HISTORY:]
            _save_state(state)
            return task
    for task in history:
        if task.get("id") == task_id:
            task.update(updates or {})
            task["updated_at"] = _now_iso()
            _save_state(state)
            return task
    return None


def add_action_log(action: str, status: str, detail: str = "", source: str = "auto_runner") -> Dict[str, Any]:
    state = _load_state()
    entry = {
        "id": uuid4().hex,
        "action": action,
        "status": status,
        "detail": detail,
        "source": source,
        "ts": _now_iso(),
    }
    logs = state.setdefault("action_log", [])
    logs.append(entry)
    if len(logs) > MAX_ACTION_LOG:
        state["action_log"] = logs[-MAX_ACTION_LOG:]
    _save_state(state)
    return entry


def add_approval_request(
    title: str,
    detail: str,
    *,
    risk: str = "risky",
    tool: str = "operator",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    state = _load_state()
    entry = {
        "id": uuid4().hex,
        "title": (title or "").strip(),
        "detail": (detail or "").strip(),
        "risk": risk,
        "tool": tool,
        "payload": payload or {},
        "status": "pending",
        "ts": _now_iso(),
    }
    approvals = state.setdefault("approvals", {})
    pending = approvals.setdefault("pending", [])
    pending.append(entry)
    # keep bounded
    if len(pending) > 200:
        approvals["pending"] = pending[-200:]
    _save_state(state)
    return entry


def resolve_approval(approval_id: str, *, approved: bool, note: str = "") -> Optional[Dict[str, Any]]:
    if not approval_id:
        return None
    state = _load_state()
    approvals = state.setdefault("approvals", {})
    pending = approvals.setdefault("pending", [])
    history = approvals.setdefault("history", [])
    for idx, entry in enumerate(pending):
        if entry.get("id") == approval_id:
            entry["status"] = "approved" if approved else "rejected"
            entry["resolved_at"] = _now_iso()
            if note:
                entry["note"] = note
            history.append(entry)
            pending.pop(idx)
            if len(history) > MAX_APPROVAL_HISTORY:
                approvals["history"] = history[-MAX_APPROVAL_HISTORY:]
            _save_state(state)
            return entry
    return None


def list_approvals(include_history: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    state = _load_state()
    approvals = state.get("approvals") or {}
    pending = approvals.get("pending") or []
    history = approvals.get("history") or []
    return {"pending": list(pending), "history": list(history) if include_history else []}


def get_approval(approval_id: str) -> Optional[Dict[str, Any]]:
    if not approval_id:
        return None
    state = _load_state()
    approvals = state.get("approvals") or {}
    pending = approvals.get("pending") or []
    history = approvals.get("history") or []
    for entry in pending:
        if isinstance(entry, dict) and entry.get("id") == approval_id:
            return entry
    for entry in reversed(history):
        if isinstance(entry, dict) and entry.get("id") == approval_id:
            return entry
    return None


def set_operator_active(task_id: str, goal: str, artifacts_dir: str) -> Dict[str, Any]:
    state = _load_state()
    operator = state.setdefault("operator", {"active": None, "history": []})
    entry = {
        "task_id": task_id,
        "goal": goal,
        "artifacts_dir": artifacts_dir,
        "status": "active",
        "started_at": _now_iso(),
        "last_step": None,
        "last_observation": None,
    }
    operator["active"] = entry
    _save_state(state)
    return entry


def update_operator_active(step: Optional[Dict[str, Any]] = None, observation: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    state = _load_state()
    operator = state.get("operator")
    if not isinstance(operator, dict):
        return None
    active = operator.get("active")
    if not isinstance(active, dict):
        return None
    if step is not None:
        active["last_step"] = step
    if observation is not None:
        active["last_observation"] = observation
    operator["active"] = active
    _save_state(state)
    return active


def complete_operator_active(status: str = "completed", detail: str = "") -> Optional[Dict[str, Any]]:
    state = _load_state()
    operator = state.get("operator")
    if not isinstance(operator, dict):
        return None
    active = operator.get("active")
    if not isinstance(active, dict):
        return None
    active["status"] = status
    active["completed_at"] = _now_iso()
    if detail:
        active["detail"] = detail
    history = operator.setdefault("history", [])
    history.append(active)
    if len(history) > MAX_OPERATOR_HISTORY:
        operator["history"] = history[-MAX_OPERATOR_HISTORY:]
    operator["active"] = None
    _save_state(state)
    return active


def get_operator_state(include_history: bool = False) -> Dict[str, Any]:
    state = _load_state()
    operator = state.get("operator") if isinstance(state.get("operator"), dict) else {"active": None, "history": []}
    result = {"active": operator.get("active")}
    if include_history:
        result["history"] = operator.get("history") or []
    return result


def add_model_event(event: str, model: str, source: str = "model", detail: str = "") -> Dict[str, Any]:
    state = _load_state()
    entry = {
        "id": uuid4().hex,
        "event": event,
        "model": model,
        "source": source,
        "detail": detail,
        "ts": _now_iso(),
    }
    events = state.setdefault("model_events", [])
    events.append(entry)
    if len(events) > MAX_MODEL_EVENTS:
        state["model_events"] = events[-MAX_MODEL_EVENTS:]
    _save_state(state)
    return entry


def add_system_event(level: str, message: str, source: str = "system", detail: str = "") -> Dict[str, Any]:
    state = _load_state()
    entry = {
        "id": uuid4().hex,
        "level": level,
        "message": message,
        "source": source,
        "detail": detail,
        "ts": _now_iso(),
    }
    events = state.setdefault("system_events", [])
    events.append(entry)
    if len(events) > MAX_SYSTEM_EVENTS:
        state["system_events"] = events[-MAX_SYSTEM_EVENTS:]
    _save_state(state)
    return entry


def list_action_logs(since: Optional[str] = None, limit: int = 2000) -> List[Dict[str, Any]]:
    state = _load_state()
    return _filter_entries(state.get("action_log") or [], since, limit)


def list_model_events(since: Optional[str] = None, limit: int = 2000) -> List[Dict[str, Any]]:
    state = _load_state()
    return _filter_entries(state.get("model_events") or [], since, limit)


def list_system_events(since: Optional[str] = None, limit: int = 2000) -> List[Dict[str, Any]]:
    state = _load_state()
    return _filter_entries(state.get("system_events") or [], since, limit)


def set_gateway_cache(section: str, payload: Any) -> None:
    if not section:
        return
    state = _load_state()
    cache = state.setdefault("gateway_cache", {})
    cache[section] = {"payload": payload, "ts": _now_iso()}
    if len(cache) > MAX_GATEWAY_CACHE:
        items = list(cache.items())[-MAX_GATEWAY_CACHE:]
        state["gateway_cache"] = dict(items)
    _save_state(state)


def get_gateway_cache(section: str) -> Optional[Dict[str, Any]]:
    state = _load_state()
    cache = state.get("gateway_cache") or {}
    if not isinstance(cache, dict):
        return None
    entry = cache.get(section)
    return entry if isinstance(entry, dict) else None


def record_vscode_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not payload:
        return {}
    state = _load_state()
    entry = {"ts": _now_iso(), "payload": payload}
    vscode = state.setdefault("vscode", {"last": None, "history": []})
    vscode["last"] = entry
    history = vscode.setdefault("history", [])
    history.append(entry)
    if len(history) > MAX_VSCODE_HISTORY:
        vscode["history"] = history[-MAX_VSCODE_HISTORY:]
    _save_state(state)
    return entry


def set_status(key: str, value: Any) -> None:
    state = _load_state()
    status = state.setdefault("status", {})
    status[key] = value
    _save_state(state)
