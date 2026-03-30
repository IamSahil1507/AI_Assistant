from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data" / "config_snapshots.json"
MAX_SNAPSHOTS = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> Dict[str, Any]:
    if SNAPSHOT_PATH.exists():
        try:
            data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {"snapshots": []}


def _save(data: Dict[str, Any]) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_snapshots() -> List[Dict[str, Any]]:
    data = _load()
    return list(data.get("snapshots") or [])


def add_snapshot(config: Dict[str, Any]) -> Dict[str, Any]:
    data = _load()
    entry = {
        "id": uuid4().hex,
        "config": config,
        "ts": _now_iso(),
    }
    snapshots = data.setdefault("snapshots", [])
    snapshots.append(entry)
    if len(snapshots) > MAX_SNAPSHOTS:
        data["snapshots"] = snapshots[-MAX_SNAPSHOTS:]
    _save(data)
    return entry


def get_snapshot(snapshot_id: str) -> Optional[Dict[str, Any]]:
    for entry in list_snapshots():
        if entry.get("id") == snapshot_id:
            return entry
    return None
