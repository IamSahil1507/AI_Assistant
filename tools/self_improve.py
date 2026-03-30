import json
from pathlib import Path
from typing import Any, Dict, List


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "self_improve.json"


def _load() -> Dict[str, Any]:
    if DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"notices": [], "history": []}


def _save(data: Dict[str, Any]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _append_notice(kind: str, detail: str, benefit: str = "") -> None:
    data = _load()
    notice = {"kind": kind, "detail": detail, "benefit": benefit}
    data.setdefault("notices", []).append(notice)
    data.setdefault("history", []).append(notice)
    if len(data["history"]) > 200:
        data["history"] = data["history"][-200:]
    _save(data)


def note_learning(detail: str, benefit: str = "") -> None:
    _append_notice("learned", detail, benefit)


def note_change(detail: str, benefit: str = "") -> None:
    _append_notice("changed", detail, benefit)


def note_suggestion(detail: str, benefit: str = "") -> None:
    _append_notice("suggestion", detail, benefit)


def pop_notices() -> List[Dict[str, str]]:
    data = _load()
    notices = data.get("notices") or []
    data["notices"] = []
    _save(data)
    return notices
