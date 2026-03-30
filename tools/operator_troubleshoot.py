from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from tools import assistant_state


@dataclass(frozen=True)
class Lesson:
    ts: float
    fingerprint: str
    tool: str
    error: str
    root_cause: str = ""
    fix: str = ""
    prevention: str = ""
    sources: Optional[list[dict[str, str]]] = None


def lessons_path(root: Path) -> Path:
    return root / "data" / "lessons_learned.jsonl"


def append_lesson(root: Path, lesson: Lesson) -> None:
    path = lessons_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(lesson), ensure_ascii=True) + "\n")


def write_diagnostic_bundle(artifacts_dir: Path, payload: Dict[str, Any]) -> str:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out = artifacts_dir / f"diagnostic_{int(time.time())}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(out)


def _read_jsonl_tail(path: Path, max_lines: int = 200) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    if max_lines > 0:
        lines = lines[-max_lines:]
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                out.append(obj)
        except Exception:
            continue
    return out


def build_local_diagnosis_bundle(
    *,
    root: Path,
    task_id: str,
    artifacts_dir: str | Path,
    include_history: bool = False,
    max_step_lines: int = 200,
) -> Dict[str, Any]:
    """
    Build a local-only diagnosis bundle.

    Includes:
    - active operator state
    - recent system/model/action logs (bounded)
    - tail of operator steps.jsonl
    - safe config snapshot (no secrets)
    """
    art = Path(artifacts_dir)
    steps = _read_jsonl_tail(art / "steps.jsonl", max_lines=max_step_lines)
    op_state = assistant_state.get_operator_state(include_history=include_history)
    system_events = assistant_state.list_system_events(limit=200)
    model_events = assistant_state.list_model_events(limit=200)
    action_logs = assistant_state.list_action_logs(limit=200)

    config_path = root / "config" / "openclaw.json"
    config_raw = {}
    if config_path.exists():
        try:
            config_raw = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            config_raw = {}

    return {
        "ts": time.time(),
        "task_id": task_id,
        "artifacts_dir": str(art),
        "operator_state": op_state,
        "steps_tail": steps,
        "system_events_tail": system_events,
        "model_events_tail": model_events,
        "action_logs_tail": action_logs,
        "config_snapshot": {
            "assistant_policy": (config_raw.get("assistant_policy") if isinstance(config_raw, dict) else {}),
            "research_enabled": (config_raw.get("research_enabled") if isinstance(config_raw, dict) else True),
            "research_mode": (config_raw.get("research_mode") if isinstance(config_raw, dict) else "local_first"),
            "editor_bridge": (config_raw.get("editor_bridge") if isinstance(config_raw, dict) else {}),
            "desktop": (config_raw.get("desktop") if isinstance(config_raw, dict) else {}),
        },
    }

