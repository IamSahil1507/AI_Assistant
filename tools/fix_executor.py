from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.fix_attempts import FixAttempt
from tools.operator_controller import OperatorController, PlanStep
from tools import operator_troubleshoot


def _artifacts_dir(root: Path, task_id: str) -> Path:
    return root / ".superpowers" / "operator" / task_id


async def execute_fix_attempts(
    *,
    root: Path,
    task_id: str,
    operator: OperatorController,
    attempts: List[FixAttempt],
    error_signature: str,
    sources: Optional[list[dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Execute fix attempts in order (least risky first expected).

    Supported attempt kinds/payload shapes:
    - config_change: payload { updates: { ... } }
    - retry_step: payload { step: { goal, step_id, tool, action, risk?, success_criteria? } }
    - manual/code_patch: recorded only (no execution in v1 scaffold)

    Returns results with per-attempt status. On first success, persists a lesson entry.
    """
    art = _artifacts_dir(root, task_id)
    art.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for attempt in attempts:
        payload = attempt.payload or {}
        entry: Dict[str, Any] = {
            "ts": time.time(),
            "kind": attempt.kind,
            "description": attempt.description,
            "risk": attempt.risk,
            "payload": payload,
            "ok": False,
        }

        if attempt.kind == "config_change":
            updates = payload.get("updates") if isinstance(payload.get("updates"), dict) else {}
            try:
                operator.bridge.config_manager._config = operator.bridge.config_manager._merge(
                    operator.bridge.config_manager.config, updates
                )
                operator.bridge.config_manager.save_app_config()
                operator.bridge.config_manager.update_user_config(updates)
                entry["ok"] = True
                entry["result"] = {"updated_keys": sorted(list(updates.keys()))[:50]}
            except Exception as exc:  # noqa: BLE001
                entry["result"] = {"error": str(exc)}

        elif attempt.kind in {"retry_step", "shell_step", "editor_step"}:
            step_payload = payload.get("step") if isinstance(payload.get("step"), dict) else {}
            try:
                step = PlanStep(
                    goal=str(step_payload.get("goal") or "retry"),
                    step_id=str(step_payload.get("step_id") or "retry_step"),
                    tool=str(step_payload.get("tool") or "shell"),  # type: ignore[arg-type]
                    action=step_payload.get("action") if isinstance(step_payload.get("action"), dict) else {},
                    risk=("risky" if str(step_payload.get("risk") or "normal") == "risky" else "normal"),  # type: ignore[arg-type]
                    success_criteria=str(step_payload.get("success_criteria") or ""),
                )
                out = await operator.execute_plan_step_async(task_id, step)
                entry["result"] = out
                obs = out.get("observation") if isinstance(out, dict) else None
                entry["ok"] = bool(obs.get("ok")) if isinstance(obs, dict) else False
            except Exception as exc:  # noqa: BLE001
                entry["result"] = {"error": str(exc)}

        else:
            entry["result"] = {"note": "not_executed_in_v1"}

        results.append(entry)
        if entry.get("ok") is True:
            operator_troubleshoot.append_lesson(
                root,
                operator_troubleshoot.Lesson(
                    ts=time.time(),
                    fingerprint=f"{task_id}:{attempt.kind}:{error_signature}",
                    tool="autofix",
                    error=error_signature,
                    root_cause="",
                    fix=attempt.description,
                    prevention="",
                    sources=sources or [],
                ),
            )
            break

    operator_troubleshoot.write_diagnostic_bundle(art, {"fix_attempts": results})
    return {"ok": any(r.get("ok") for r in results), "results": results}

