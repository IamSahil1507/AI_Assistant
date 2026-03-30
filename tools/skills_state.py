from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "skills_state.json"
MAX_HISTORY = 500
MAX_APPROVALS = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> Dict[str, Any]:
    return {
        "installed": [],
        "history": [],
        "approvals": [],
        "last_scan": None,
        "updated_at": _now_iso(),
    }


def _load_state() -> Dict[str, Any]:
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return _default_state()


def _save_state(state: Dict[str, Any]) -> None:
    state["updated_at"] = _now_iso()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_state() -> Dict[str, Any]:
    return _load_state()


def set_installed(skills: List[str]) -> None:
    state = _load_state()
    state["installed"] = list(skills)
    _save_state(state)


def record_history(kind: str, detail: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = _load_state()
    entry = {
        "id": uuid4().hex,
        "kind": kind,
        "detail": detail,
        "payload": payload or {},
        "ts": _now_iso(),
    }
    history = state.setdefault("history", [])
    history.append(entry)
    if len(history) > MAX_HISTORY:
        state["history"] = history[-MAX_HISTORY:]
    _save_state(state)
    return entry


def record_scan(result: Dict[str, Any]) -> None:
    state = _load_state()
    state["last_scan"] = result
    _save_state(state)


def add_approval(skill_id: str, reason: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = _load_state()
    entry = {
        "id": uuid4().hex,
        "skill": skill_id,
        "reason": reason,
        "payload": payload or {},
        "status": "pending",
        "ts": _now_iso(),
    }
    approvals = state.setdefault("approvals", [])
    approvals.append(entry)
    if len(approvals) > MAX_APPROVALS:
        state["approvals"] = approvals[-MAX_APPROVALS:]
    _save_state(state)
    return entry


def list_approvals(status: Optional[str] = None) -> List[Dict[str, Any]]:
    state = _load_state()
    approvals = state.get("approvals") or []
    if not status:
        return list(approvals)
    return [item for item in approvals if item.get("status") == status]


def update_approval(approval_id: str, status: str, note: str = "") -> Optional[Dict[str, Any]]:
    if not approval_id:
        return None
    state = _load_state()
    approvals = state.get("approvals") or []
    for item in approvals:
        if item.get("id") == approval_id:
            item["status"] = status
            if note:
                item["note"] = note
            item["updated_at"] = _now_iso()
            _save_state(state)
            return item
    return None
