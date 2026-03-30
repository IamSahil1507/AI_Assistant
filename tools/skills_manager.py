from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

from tools import skills_state
from tools import assistant_state


_SKILL_ID_PATTERN = re.compile(r"[\w.-]+/[\w.-]+")


class SkillsManager:
    def __init__(self, config_provider) -> None:
        self._config_provider = config_provider
        self._last_schedule_ts: float = 0.0

    def _config(self) -> Dict[str, Any]:
        return self._config_provider() or {}

    def settings(self) -> Dict[str, Any]:
        skills_cfg = self._config().get("skills")
        return skills_cfg if isinstance(skills_cfg, dict) else {}

    def _cli_base(self) -> List[str]:
        if shutil.which("skills"):
            return ["skills"]
        return ["npx", "skills"]

    def _run_cli(self, args: List[str]) -> Dict[str, Any]:
        env = os.environ.copy()
        settings = self.settings()
        if settings.get("telemetry_disabled", True):
            env["DISABLE_TELEMETRY"] = "1"
        cmd = self._cli_base() + args
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
                env=env,
            )
            ok = result.returncode == 0
            payload = {
                "ok": ok,
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "cmd": " ".join(cmd),
            }
            if not ok:
                assistant_state.add_system_event("error", "Skills CLI failed", source="skills", detail=payload.get("stderr", ""))
            return payload
        except Exception as exc:
            assistant_state.add_system_event("error", "Skills CLI exception", source="skills", detail=str(exc))
            return {"ok": False, "returncode": 1, "stdout": "", "stderr": str(exc), "cmd": " ".join(cmd)}

    def _parse_skill_ids(self, text: str) -> List[str]:
        if not text:
            return []
        return sorted(set(_SKILL_ID_PATTERN.findall(text)))

    def list_installed(self) -> Dict[str, Any]:
        result = self._run_cli(["list"])
        skills = self._parse_skill_ids(result.get("stdout", "") + "\n" + result.get("stderr", ""))
        skills_state.set_installed(skills)
        skills_state.record_history("list", "Listed installed skills", {"skills": skills, "raw": result})
        return {"ok": result["ok"], "skills": skills, "raw": result}

    def search(self, query: str) -> Dict[str, Any]:
        result = self._run_cli(["find", query])
        skills = self._parse_skill_ids(result.get("stdout", "") + "\n" + result.get("stderr", ""))
        payload = {"query": query, "skills": skills, "raw": result}
        skills_state.record_history("search", f"Search for '{query}'", payload)
        return {"ok": result["ok"], "skills": skills, "raw": result}

    def _allowed(self, skill_id: str) -> bool:
        settings = self.settings()
        if settings.get("denylist_enabled", True):
            denylist = set(settings.get("denylist") or [])
            if skill_id in denylist:
                return False
        if settings.get("allowlist_enabled", False):
            allowlist = set(settings.get("allowlist") or [])
            return skill_id in allowlist
        return True

    def install(self, skill_id: str) -> Dict[str, Any]:
        if not self._allowed(skill_id):
            msg = f"Skill '{skill_id}' blocked by allow/deny list"
            skills_state.record_history("install_blocked", msg, {"skill": skill_id})
            return {"ok": False, "error": msg}
        result = self._run_cli(["add", skill_id])
        skills_state.record_history("install", f"Install {skill_id}", {"skill": skill_id, "raw": result})
        assistant_state.add_system_event("info", f"Skill install {skill_id}", source="skills")
        return {"ok": result["ok"], "raw": result}

    def update(self, skill_id: Optional[str] = None) -> Dict[str, Any]:
        args = ["update"]
        if skill_id:
            args.append(skill_id)
        result = self._run_cli(args)
        skills_state.record_history("update", "Update skills", {"skill": skill_id, "raw": result})
        assistant_state.add_system_event("info", "Skills update", source="skills")
        return {"ok": result["ok"], "raw": result}

    def check_updates(self) -> Dict[str, Any]:
        result = self._run_cli(["check"])
        skills_state.record_history("check", "Check skill updates", {"raw": result})
        return {"ok": result["ok"], "raw": result}

    def scan(self, query: str, source: str = "manual") -> Dict[str, Any]:
        settings = self.settings()
        if not settings.get("enabled", True):
            return {"ok": False, "error": "skills_disabled"}
        search = self.search(query)
        skills = search.get("skills") or []
        approvals: List[Dict[str, Any]] = []
        installed: List[Dict[str, Any]] = []
        if skills:
            for skill_id in skills:
                if not self._allowed(skill_id):
                    continue
                if settings.get("auto_install", False) and not settings.get("discovery_only", True):
                    install_result = self.install(skill_id)
                    installed.append({"skill": skill_id, "result": install_result})
                else:
                    approvals.append(skills_state.add_approval(skill_id, f"Discovered via {source}", {"query": query}))
                if len(approvals) + len(installed) >= 3:
                    break
        payload = {"query": query, "source": source, "skills": skills, "installed": installed, "approvals": approvals}
        skills_state.record_scan(payload)
        return {"ok": True, **payload}

    def process_approval(self, approval_id: str, action: str) -> Dict[str, Any]:
        approval = skills_state.update_approval(approval_id, action)
        if not approval:
            return {"ok": False, "error": "approval_not_found"}
        if action == "approved":
            return {"ok": True, "approval": approval, "install": self.install(approval.get("skill", ""))}
        return {"ok": True, "approval": approval}

    def scheduled_tick(self) -> Optional[Dict[str, Any]]:
        settings = self.settings()
        if not settings.get("enabled", True) or not settings.get("schedule_enabled", True):
            return None
        interval = str(settings.get("schedule_interval") or "weekly").lower()
        seconds = 7 * 24 * 3600
        if interval == "daily":
            seconds = 24 * 3600
        elif interval == "monthly":
            seconds = 30 * 24 * 3600
        now = time.time()
        if now - self._last_schedule_ts < seconds:
            return None
        self._last_schedule_ts = now
        check = self.check_updates()
        if settings.get("auto_update", False):
            update = self.update()
        else:
            update = {"ok": True, "skipped": True}
        result = {"check": check, "update": update, "ts": time.time(), "interval": interval}
        skills_state.record_history("scheduled", f"Scheduled scan ({interval})", result)
        return result
