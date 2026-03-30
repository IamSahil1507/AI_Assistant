from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from tools import assistant_state
from tools.operator_tools import browser_playwright
from tools.operator_tools import shell_tools
from tools.operator_tools import fs_tools
from tools.operator_tools import editor_bridge
from tools.operator_tools import desktop_windows
from tools import operator_troubleshoot


ToolName = Literal["browser", "shell", "editor", "desktop"]
RiskLevel = Literal["normal", "risky"]
Decision = Literal["allow", "block", "require_approval"]


@dataclass(frozen=True)
class PlanStep:
    goal: str
    step_id: str
    tool: ToolName
    action: Dict[str, Any]
    risk: RiskLevel = "normal"
    success_criteria: str = ""
    fallbacks: Optional[List[Dict[str, Any]]] = None


@dataclass(frozen=True)
class Observation:
    tool: ToolName
    ts: float
    ok: bool
    summary: str
    data: Dict[str, Any]
    artifact_paths: List[str]

    def fingerprint(self) -> str:
        payload = {
            "tool": self.tool,
            "ok": self.ok,
            "summary": self.summary[:500],
            "data_keys": sorted(list(self.data.keys()))[:50],
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


class OperatorController:
    """
    Runs a bounded plan→policy→tool→observe loop.

    v1 is a skeleton: it provides durable artifacts/logging and a single-step hook
    so we can incrementally add tools (browser/shell/editor/desktop) and planning.
    """

    def __init__(self, bridge: Any) -> None:
        self.bridge = bridge
        self._root = Path(__file__).resolve().parents[1]

    def _artifacts_dir(self, task_id: str) -> Path:
        return self._root / ".superpowers" / "operator" / task_id

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _append_jsonl(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def _note_failure_if_repeating(self, task_id: str, observation: Observation) -> None:
        """
        Lightweight v1 stuck detection:
        - If the same observation fingerprint repeats, write a diagnostic bundle and append a lesson stub.
        """
        state = assistant_state.get_state()
        operator_state = state.get("operator") if isinstance(state.get("operator"), dict) else {}
        last_fp = operator_state.get("last_observation_fp") if isinstance(operator_state, dict) else None
        fp = observation.fingerprint()
        if last_fp and last_fp == fp and not observation.ok:
            artifacts = self._artifacts_dir(task_id)
            diag_path = operator_troubleshoot.write_diagnostic_bundle(
                artifacts,
                {
                    "task_id": task_id,
                    "fingerprint": fp,
                    "tool": observation.tool,
                    "summary": observation.summary,
                    "data": observation.data,
                    "artifact_paths": observation.artifact_paths,
                },
            )
            operator_troubleshoot.append_lesson(
                self._root,
                operator_troubleshoot.Lesson(
                    ts=time.time(),
                    fingerprint=fp,
                    tool=observation.tool,
                    error=str(observation.data.get("error") or observation.summary),
                    root_cause="",
                    fix="",
                    prevention="",
                    sources=[],
                ),
            )
            assistant_state.add_system_event(
                "warn",
                "Operator stuck detected; diagnostic bundle written",
                source="operator",
                detail=diag_path,
            )
        # persist last fp
        assistant_state.set_status("operator.last_observation_fp", fp)

    def start_task(self, goal: str, *, source: str = "operator") -> Dict[str, Any]:
        task_id = f"op_{int(time.time())}_{uuid4().hex[:8]}"
        artifacts = self._artifacts_dir(task_id)
        artifacts.mkdir(parents=True, exist_ok=True)
        self._write_json(
            artifacts / "task.json",
            {"task_id": task_id, "goal": goal, "source": source, "created_at": time.time()},
        )
        assistant_state.set_operator_active(task_id, goal, str(artifacts))
        assistant_state.add_system_event("info", f"Operator task started: {goal}", source="operator", detail=task_id)
        return {"task_id": task_id, "artifacts_dir": str(artifacts)}

    def run_single_step(
        self,
        task_id: str,
        plan_step: PlanStep,
        *,
        observation: Optional[Observation] = None,
    ) -> Dict[str, Any]:
        """
        Execute exactly one plan step through the policy gate.

        Tool execution is not implemented here yet; this method is used to
        validate the control-plane: logging, policy decisions, approvals.
        """
        artifacts = self._artifacts_dir(task_id)
        artifacts.mkdir(parents=True, exist_ok=True)
        steps_path = artifacts / "steps.jsonl"

        entry: Dict[str, Any] = {
            "ts": time.time(),
            "task_id": task_id,
            "plan": {
                "goal": plan_step.goal,
                "step_id": plan_step.step_id,
                "tool": plan_step.tool,
                "risk": plan_step.risk,
                "success_criteria": plan_step.success_criteria,
                "action": plan_step.action,
            },
        }

        policy_eval = {}
        if hasattr(self.bridge, "policy") and hasattr(self.bridge.policy, "evaluate_operator_step"):
            try:
                policy_eval = self.bridge.policy.evaluate_operator_step(
                    tool=plan_step.tool,
                    action=plan_step.action,
                    risk=plan_step.risk,
                )
            except Exception as exc:  # noqa: BLE001
                policy_eval = {"decision": "block", "risk": "risky", "reason": f"policy_exception: {exc}"}
        entry["policy"] = policy_eval

        # In v1 skeleton, we do not execute tools yet.
        if observation:
            entry["observation"] = {
                "tool": observation.tool,
                "ts": observation.ts,
                "ok": observation.ok,
                "summary": observation.summary,
                "data": observation.data,
                "artifact_paths": observation.artifact_paths,
                "fingerprint": observation.fingerprint(),
            }

        self._append_jsonl(steps_path, entry)
        # Standard artifact: write the last step + observation as JSON for easier debugging.
        try:
            step_artifact = artifacts / f"step_{int(entry['ts'])}_{plan_step.step_id}.json"
            self._write_json(step_artifact, entry)
        except Exception:
            pass
        try:
            assistant_state.update_operator_active(step=entry.get("plan"), observation=entry.get("observation"))
        except Exception:
            pass
        return {"task_id": task_id, "policy": policy_eval, "logged": True, "artifacts_dir": str(artifacts)}

    def execute_plan_step(self, task_id: str, plan_step: PlanStep) -> Dict[str, Any]:
        """
        Execute a plan step end-to-end (policy + tool) and log it.

        v1 supports only a minimal browser action:
          tool=browser, action={ "type": "open_url_screenshot", "url": "https://..." }
        """
        policy_eval = self.bridge.policy.evaluate_operator_step(
            tool=plan_step.tool,
            action=plan_step.action,
            risk=plan_step.risk,
        )
        decision = str(policy_eval.get("decision") or "")
        if decision == "require_approval":
            approval = assistant_state.add_approval_request(
                title=f"Operator approval required ({plan_step.tool})",
                detail=f"{plan_step.step_id}: {plan_step.success_criteria or 'execute step'}",
                risk=str(policy_eval.get("risk") or plan_step.risk),
                tool=plan_step.tool,
                payload={"plan": plan_step.__dict__, "policy": policy_eval},
            )
            self.run_single_step(task_id, plan_step, observation=None)
            return {"task_id": task_id, "policy": policy_eval, "approval": approval, "executed": False}
        if decision != "allow":
            self.run_single_step(task_id, plan_step, observation=None)
            return {"task_id": task_id, "policy": policy_eval, "executed": False}

        artifacts = self._artifacts_dir(task_id)
        obs_payload: Dict[str, Any] = {"ok": False, "error": "tool_not_implemented"}
        artifact_paths: List[str] = []
        summary = ""
        if plan_step.tool == "browser":
            action_type = str(plan_step.action.get("type") or "").strip()
            if action_type == "open_url_screenshot":
                url = str(plan_step.action.get("url") or "").strip()
                try:
                    obs_payload = browser_playwright.open_url_screenshot(url=url, artifacts_dir=artifacts)
                except Exception as exc:  # noqa: BLE001
                    obs_payload = {"ok": False, "error": str(exc)}
                if obs_payload.get("screenshot_path"):
                    artifact_paths.append(str(obs_payload["screenshot_path"]))
                summary = f"Opened {url}" if obs_payload.get("ok") else f"Failed to open {url}"
            else:
                obs_payload = {"ok": False, "error": "unknown_browser_action", "action_type": action_type}
                summary = "Unknown browser action"
        else:
            summary = "Tool not implemented"

        observation = Observation(
            tool=plan_step.tool,
            ts=time.time(),
            ok=bool(obs_payload.get("ok", False)),
            summary=summary,
            data=obs_payload,
            artifact_paths=artifact_paths,
        )
        self.run_single_step(task_id, plan_step, observation=observation)
        return {"task_id": task_id, "policy": policy_eval, "observation": obs_payload, "executed": True}

    async def execute_plan_step_async(self, task_id: str, plan_step: PlanStep) -> Dict[str, Any]:
        """
        Async variant for tools that require async execution (e.g., Playwright).
        """
        policy_eval = self.bridge.policy.evaluate_operator_step(
            tool=plan_step.tool,
            action=plan_step.action,
            risk=plan_step.risk,
        )
        decision = str(policy_eval.get("decision") or "")
        if decision == "require_approval":
            approval = assistant_state.add_approval_request(
                title=f"Operator approval required ({plan_step.tool})",
                detail=f"{plan_step.step_id}: {plan_step.success_criteria or 'execute step'}",
                risk=str(policy_eval.get("risk") or plan_step.risk),
                tool=plan_step.tool,
                payload={"plan": plan_step.__dict__, "policy": policy_eval},
            )
            self.run_single_step(task_id, plan_step, observation=None)
            return {"task_id": task_id, "policy": policy_eval, "approval": approval, "executed": False}
        if decision != "allow":
            self.run_single_step(task_id, plan_step, observation=None)
            return {"task_id": task_id, "policy": policy_eval, "executed": False}

        artifacts = self._artifacts_dir(task_id)
        obs_payload: Dict[str, Any] = {"ok": False, "error": "tool_not_implemented"}
        artifact_paths: List[str] = []
        summary = ""
        if plan_step.tool == "browser":
            action_type = str(plan_step.action.get("type") or "").strip()
            if action_type == "open_url_screenshot":
                url = str(plan_step.action.get("url") or "").strip()
                try:
                    obs_payload = await browser_playwright.open_url_screenshot_async(url=url, artifacts_dir=artifacts)
                except Exception as exc:  # noqa: BLE001
                    obs_payload = {"ok": False, "error": str(exc)}
                if obs_payload.get("screenshot_path"):
                    artifact_paths.append(str(obs_payload["screenshot_path"]))
                summary = f"Opened {url}" if obs_payload.get("ok") else f"Failed to open {url}"
            elif action_type == "browser_actions":
                actions = plan_step.action.get("actions") if isinstance(plan_step.action.get("actions"), list) else []
                options = plan_step.action.get("options") if isinstance(plan_step.action.get("options"), dict) else {}
                try:
                    obs_payload = await browser_playwright.run_actions_async(
                        artifacts_dir=artifacts,
                        actions=actions,
                        headless=bool(options.get("headless", True)),
                        use_system_chrome_profile=bool(options.get("use_system_chrome_profile", False)),
                        chrome_profile_directory=str(options.get("chrome_profile_directory") or "Default"),
                    )
                except Exception as exc:  # noqa: BLE001
                    obs_payload = {"ok": False, "error": str(exc)}
                if obs_payload.get("screenshot_path"):
                    artifact_paths.append(str(obs_payload["screenshot_path"]))
                summary = "Browser actions complete" if obs_payload.get("ok") else "Browser actions failed"
            else:
                obs_payload = {"ok": False, "error": "unknown_browser_action", "action_type": action_type}
                summary = "Unknown browser action"
        else:
            if plan_step.tool == "shell":
                action_type = str(plan_step.action.get("type") or "").strip()
                if action_type == "run_command":
                    command = str(plan_step.action.get("command") or "").strip()
                    timeout_seconds = int(plan_step.action.get("timeout_seconds") or 60)
                    cwd = plan_step.action.get("cwd")
                    cwd = str(cwd) if isinstance(cwd, str) and cwd.strip() else None
                    try:
                        obs_payload = shell_tools.run_command(
                            command=command,
                            artifacts_dir=artifacts,
                            config=self.bridge.config_manager.config,
                            timeout_seconds=timeout_seconds,
                            cwd=cwd,
                        )
                    except Exception as exc:  # noqa: BLE001
                        obs_payload = {"ok": False, "error": str(exc)}
                    for key in ("stdout_path", "stderr_path"):
                        if obs_payload.get(key):
                            artifact_paths.append(str(obs_payload[key]))
                    summary = "Command executed" if obs_payload.get("ok") else "Command failed"
                elif action_type == "fs_list":
                    path = str(plan_step.action.get("path") or "").strip()
                    max_entries = int(plan_step.action.get("max_entries") or 200)
                    try:
                        obs_payload = fs_tools.list_dir(path=path, config=self.bridge.config_manager.config, max_entries=max_entries)
                    except Exception as exc:  # noqa: BLE001
                        obs_payload = {"ok": False, "error": str(exc)}
                    summary = "Listed directory" if obs_payload.get("ok") else "Directory list failed"
                elif action_type == "fs_read_text":
                    path = str(plan_step.action.get("path") or "").strip()
                    max_bytes = int(plan_step.action.get("max_bytes") or 200_000)
                    try:
                        obs_payload = fs_tools.read_text(path=path, config=self.bridge.config_manager.config, max_bytes=max_bytes)
                    except Exception as exc:  # noqa: BLE001
                        obs_payload = {"ok": False, "error": str(exc)}
                    summary = "Read file" if obs_payload.get("ok") else "File read failed"
                elif action_type == "fs_write_text":
                    path = str(plan_step.action.get("path") or "").strip()
                    text = str(plan_step.action.get("text") or "")
                    try:
                        obs_payload = fs_tools.write_text(path=path, text=text, config=self.bridge.config_manager.config)
                    except Exception as exc:  # noqa: BLE001
                        obs_payload = {"ok": False, "error": str(exc)}
                    summary = "Wrote file" if obs_payload.get("ok") else "File write failed"
                else:
                    obs_payload = {"ok": False, "error": "unknown_shell_action", "action_type": action_type}
                    summary = "Unknown shell action"
            else:
                if plan_step.tool == "editor":
                    action_type = str(plan_step.action.get("type") or "").strip()
                    cfg = self.bridge.config_manager.config
                    try:
                        if action_type == "open_file":
                            path = str(plan_step.action.get("path") or "").strip()
                            obs_payload = editor_bridge.open_file(path=path, config=cfg)
                            summary = "Opened file"
                        elif action_type == "search":
                            query = str(plan_step.action.get("query") or "").strip()
                            include = str(plan_step.action.get("include") or "**/*").strip() or "**/*"
                            obs_payload = editor_bridge.search(query=query, include=include, config=cfg)
                            summary = "Search complete"
                        elif action_type == "apply_edits":
                            path = str(plan_step.action.get("path") or "").strip()
                            edits = plan_step.action.get("edits") if isinstance(plan_step.action.get("edits"), list) else []
                            obs_payload = editor_bridge.apply_edits(path=path, edits=edits, config=cfg)
                            summary = "Edits applied"
                        elif action_type == "run_task":
                            name = str(plan_step.action.get("name") or "").strip()
                            obs_payload = editor_bridge.run_task(name=name, config=cfg)
                            summary = "Task started"
                        else:
                            obs_payload = {"ok": False, "error": "unknown_editor_action", "action_type": action_type}
                            summary = "Unknown editor action"
                    except Exception as exc:  # noqa: BLE001
                        obs_payload = {"ok": False, "error": str(exc)}
                        summary = "Editor action failed"
                    # Standard artifact: dump editor payload
                    try:
                        payload_path = artifacts / f"editor_{int(time.time())}_{plan_step.step_id}.json"
                        self._write_json(payload_path, {"action_type": action_type, "payload": obs_payload})
                        artifact_paths.append(str(payload_path))
                    except Exception:
                        pass
                else:
                    if plan_step.tool == "desktop":
                        action_type = str(plan_step.action.get("type") or "").strip()
                        try:
                            if action_type == "launch_notepad":
                                obs_payload = desktop_windows.launch_notepad(artifacts_dir=artifacts)
                                summary = "Notepad launched"
                            elif action_type == "type_notepad":
                                text = str(plan_step.action.get("text") or "")
                                obs_payload = desktop_windows.type_in_notepad(text=text, artifacts_dir=artifacts)
                                summary = "Typed into Notepad"
                            elif action_type == "list_windows":
                                max_items = int(plan_step.action.get("max_items") or 50)
                                obs_payload = desktop_windows.list_windows(max_items=max_items)
                                summary = "Listed windows"
                            elif action_type == "screenshot_full":
                                obs_payload = desktop_windows.screenshot_full(artifacts_dir=artifacts)
                                summary = "Captured full screenshot"
                            elif action_type == "screenshot_window_title":
                                title_contains = str(plan_step.action.get("title_contains") or "").strip()
                                obs_payload = desktop_windows.screenshot_window_title(
                                    title_contains=title_contains,
                                    artifacts_dir=artifacts,
                                )
                                summary = "Captured window screenshot"
                            elif action_type == "launch_app":
                                command = str(plan_step.action.get("command") or "").strip()
                                obs_payload = desktop_windows.launch_app(command=command, artifacts_dir=artifacts)
                                summary = "Launched app"
                            else:
                                obs_payload = {"ok": False, "error": "unknown_desktop_action", "action_type": action_type}
                                summary = "Unknown desktop action"
                        except Exception as exc:  # noqa: BLE001
                            obs_payload = {"ok": False, "error": str(exc)}
                            summary = "Desktop action failed"
                        if obs_payload.get("screenshot_path"):
                            artifact_paths.append(str(obs_payload.get("screenshot_path")))
                    else:
                        summary = "Tool not implemented"

        observation = Observation(
            tool=plan_step.tool,
            ts=time.time(),
            ok=bool(obs_payload.get("ok", False)),
            summary=summary,
            data=obs_payload,
            artifact_paths=artifact_paths,
        )
        if not observation.ok:
            self._note_failure_if_repeating(task_id, observation)
        self.run_single_step(task_id, plan_step, observation=observation)
        return {"task_id": task_id, "policy": policy_eval, "observation": obs_payload, "executed": True}

