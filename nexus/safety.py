"""
NEXUS Layer 9: Safety & Control — DO NOT SKIP
Fusion: Claude Code permission hooks + NEXUS protected zones + kill switch

Every action NEXUS takes passes through this layer FIRST.
"""

from __future__ import annotations

import json
import logging
import os
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Callable

from nexus.config import (
    PROTECTED_ZONES, PROTECTED_COMMANDS, KILL_SWITCH_HOTKEY,
    PermissionTier, PATHS,
)

logger = logging.getLogger("nexus.safety")


# ──────────────────────────────────────────────
# Audit Logger
# ──────────────────────────────────────────────

class AuditLogger:
    """
    Every action written to audit.log BEFORE execution.
    Timestamp, action, rationale, expected result, tier.
    """

    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path or PATHS.audit
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(
        self,
        action: str,
        tier: str,
        rationale: str = "",
        expected_result: str = "",
        *,
        approved: bool = True,
        detail: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Log an action BEFORE it executes."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "tier": tier,
            "rationale": rationale,
            "expected_result": expected_result,
            "approved": approved,
            "detail": detail or {},
        }
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def log_outcome(self, action: str, success: bool, outcome: str = "") -> None:
        """Log the outcome AFTER execution."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "outcome": "success" if success else "failure",
            "detail": outcome,
        }
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def rotate(self, max_size_mb: float = 50.0) -> None:
        """Rotate log if it gets too big."""
        if self.log_path.exists():
            size_mb = self.log_path.stat().st_size / (1024 * 1024)
            if size_mb > max_size_mb:
                rotated = self.log_path.with_suffix(f".{int(time.time())}.log")
                self.log_path.rename(rotated)
                logger.info(f"Rotated audit log to {rotated}")


# ──────────────────────────────────────────────
# Permission System (Three-Tier)
# ──────────────────────────────────────────────

class PermissionGate:
    """
    Three-tier permission system:
    - READ: always allowed, never asks
    - WRITE: confirm once per session
    - DESTRUCTIVE: confirm EVERY time, no exceptions
    """

    def __init__(self, confirm_callback: Optional[Callable[[str, str], bool]] = None):
        self._write_confirmed: bool = False
        self._confirm_callback = confirm_callback or self._default_confirm
        self._session_approvals: Dict[str, bool] = {}

    def check(
        self,
        action: str,
        tier: str,
        *,
        detail: str = "",
    ) -> Dict[str, Any]:
        """
        Check if an action is allowed.
        Returns: {"allowed": bool, "tier": str, "reason": str}
        """
        # READ — always allowed
        if tier == PermissionTier.READ:
            return {"allowed": True, "tier": tier, "reason": "read_always_allowed"}

        # WRITE — confirm once per session
        if tier == PermissionTier.WRITE:
            if self._write_confirmed:
                return {"allowed": True, "tier": tier, "reason": "session_approved"}
            approved = self._confirm_callback(
                f"WRITE permission requested: {action}",
                f"{detail}\n\nAllow WRITE operations for this session? (Y/N)"
            )
            if approved:
                self._write_confirmed = True
                return {"allowed": True, "tier": tier, "reason": "user_approved_session"}
            return {"allowed": False, "tier": tier, "reason": "user_denied"}

        # DESTRUCTIVE — confirm EVERY TIME
        if tier == PermissionTier.DESTRUCTIVE:
            approved = self._confirm_callback(
                f"⚠️ DESTRUCTIVE action: {action}",
                f"{detail}\n\nThis cannot be undone. Proceed? (Y/N)"
            )
            if approved:
                return {"allowed": True, "tier": tier, "reason": "user_approved_once"}
            return {"allowed": False, "tier": tier, "reason": "user_denied"}

        return {"allowed": False, "tier": tier, "reason": "unknown_tier"}

    @staticmethod
    def _default_confirm(title: str, detail: str) -> bool:
        """Default confirmation via console input."""
        print(f"\n{'='*60}")
        print(f"🛡️  {title}")
        print(f"{'='*60}")
        print(detail)
        try:
            response = input("\n> ").strip().lower()
            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    @staticmethod
    def classify_action(action: str, tool: str = "") -> str:
        """Classify an action into READ/WRITE/DESTRUCTIVE tier."""
        lowered = action.lower()
        tool_lower = tool.lower()

        # DESTRUCTIVE actions
        destructive_indicators = [
            "delete", "remove", "rm ", "rm -rf", "format", "drop ",
            "truncate", "destroy", "purge", "wipe", "uninstall",
            "pip install", "npm install", "choco install",
            "reg delete", "netsh", "diskpart",
            "env ", "setx ", "set ",  # environment variables
        ]
        if any(d in lowered for d in destructive_indicators):
            return PermissionTier.DESTRUCTIVE

        # WRITE actions
        write_indicators = [
            "write", "create", "edit", "modify", "save", "update",
            "mkdir", "touch", "echo ", ">>", ">", "mv ", "move ",
            "copy ", "cp ", "rename", "git commit", "git push",
        ]
        if any(w in lowered for w in write_indicators):
            return PermissionTier.WRITE
        if tool_lower in ["filewrite", "fileedit", "bash", "shell"]:
            return PermissionTier.WRITE

        # READ (default)
        return PermissionTier.READ


# ──────────────────────────────────────────────
# Protected Zone Enforcer
# ──────────────────────────────────────────────

class ProtectedZoneEnforcer:
    """
    Hardcoded zones NEXUS can NEVER touch.
    These are constants — not config options.
    """

    def __init__(self, extra_zones: Optional[List[str]] = None):
        self.zones = list(PROTECTED_ZONES)
        if extra_zones:
            self.zones.extend(extra_zones)

    def is_protected(self, path: str) -> bool:
        """Check if a path falls within a protected zone."""
        normalized = os.path.normpath(path).lower()
        for zone in self.zones:
            zone_norm = os.path.normpath(zone).lower()
            if normalized.startswith(zone_norm) or normalized == zone_norm:
                return True
        return False

    def is_command_blocked(self, command: str) -> bool:
        """Check if a command is in the blocked list."""
        lowered = command.lower().strip()
        for blocked in PROTECTED_COMMANDS:
            if blocked.lower() in lowered:
                return True
        return False

    def check(self, action: str, paths: Optional[List[str]] = None) -> Dict[str, Any]:
        """Check if an action violates any protected zone."""
        violations: List[str] = []

        # Check command
        if self.is_command_blocked(action):
            violations.append(f"Blocked command: {action}")

        # Check paths
        if paths:
            for p in paths:
                if self.is_protected(p):
                    violations.append(f"Protected path: {p}")

        if violations:
            return {"allowed": False, "violations": violations}
        return {"allowed": True, "violations": []}


# ──────────────────────────────────────────────
# Kill Switch
# ──────────────────────────────────────────────

class KillSwitch:
    """
    Global kill switch: Ctrl+Shift+F12
    Terminates all NEXUS processes instantly.
    """

    def __init__(self, on_kill: Optional[Callable[[], None]] = None):
        self._active = False
        self._thread: Optional[threading.Thread] = None
        self._on_kill = on_kill or self._default_kill
        self._kill_triggered = False

    def activate(self) -> bool:
        """Start listening for kill switch hotkey."""
        if self._active:
            return False
        try:
            import keyboard  # type: ignore
            keyboard.add_hotkey(KILL_SWITCH_HOTKEY, self._trigger_kill)
            self._active = True
            logger.info(f"Kill switch active: {KILL_SWITCH_HOTKEY}")
            return True
        except ImportError:
            logger.warning("'keyboard' library not installed — kill switch disabled")
            logger.warning("Install with: pip install keyboard")
            return False
        except Exception as e:
            logger.warning(f"Kill switch failed to activate: {e}")
            return False

    def deactivate(self) -> None:
        """Stop listening for kill switch."""
        if self._active:
            try:
                import keyboard
                keyboard.remove_hotkey(KILL_SWITCH_HOTKEY)
            except Exception:
                pass
            self._active = False

    def _trigger_kill(self) -> None:
        """Called when kill switch hotkey is pressed."""
        if self._kill_triggered:
            return  # prevent double-trigger
        self._kill_triggered = True
        logger.critical("🛑 KILL SWITCH ACTIVATED — terminating all NEXUS processes")
        self._on_kill()

    @staticmethod
    def _default_kill() -> None:
        """Default kill handler — terminate everything."""
        import signal
        import subprocess

        logger.critical("Executing emergency shutdown...")

        # Kill Playwright browsers
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", "chromium.exe"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass

        # Kill any spawned subprocesses
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", "python.exe", "/fi", "WINDOWTITLE eq NEXUS*"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass

        # Exit this process
        os._exit(1)


# ──────────────────────────────────────────────
# Safety Layer — Unified Gateway
# ──────────────────────────────────────────────

class SafetyLayer:
    """
    NEXUS Layer 9 — The unified safety gateway.
    Every action passes through here BEFORE execution.
    
    Flow:
    1. Check protected zones
    2. Classify permission tier (READ/WRITE/DESTRUCTIVE)
    3. Log to audit trail
    4. Check permission gate
    5. Return allow/deny
    """

    def __init__(
        self,
        confirm_callback: Optional[Callable[[str, str], bool]] = None,
        on_kill: Optional[Callable[[], None]] = None,
    ):
        self.audit = AuditLogger()
        self.permissions = PermissionGate(confirm_callback)
        self.zones = ProtectedZoneEnforcer()
        self.kill_switch = KillSwitch(on_kill)

    def initialize(self) -> Dict[str, bool]:
        """Initialize all safety systems. Call on startup."""
        return {
            "audit_log": True,
            "permissions": True,
            "protected_zones": True,
            "kill_switch": self.kill_switch.activate(),
        }

    def evaluate(
        self,
        action: str,
        *,
        tool: str = "",
        paths: Optional[List[str]] = None,
        rationale: str = "",
        force_tier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate whether an action should proceed.
        
        Returns: {
            "allowed": bool,
            "tier": str,
            "reason": str,
            "violations": list,
        }
        """
        # Step 1: Check protected zones (HARDCODED — cannot be overridden)
        zone_check = self.zones.check(action, paths)
        if not zone_check["allowed"]:
            self.audit.log(action, "BLOCKED", "Protected zone violation",
                          approved=False, detail={"violations": zone_check["violations"]})
            return {
                "allowed": False,
                "tier": "blocked",
                "reason": "protected_zone_violation",
                "violations": zone_check["violations"],
            }

        # Step 2: Classify permission tier
        tier = force_tier or PermissionGate.classify_action(action, tool)

        # Step 3: Log to audit trail BEFORE execution
        self.audit.log(action, tier, rationale)

        # Step 4: Check permission gate
        perm_check = self.permissions.check(action, tier, detail=rationale)

        # Step 5: Log approval decision
        if not perm_check["allowed"]:
            self.audit.log(action, tier, "User denied", approved=False)

        return {
            "allowed": perm_check["allowed"],
            "tier": tier,
            "reason": perm_check["reason"],
            "violations": [],
        }

    def preview(self, action: str, detail: str = "") -> str:
        """
        Generate a plain-English preview of what NEXUS is about to do.
        Mandatory for WRITE and DESTRUCTIVE actions.
        """
        tier = PermissionGate.classify_action(action)
        emoji = {"read": "👁️", "write": "✏️", "destructive": "⚠️"}.get(tier, "❓")
        return f"{emoji} [{tier.upper()}] I'm about to: {action}" + (f"\n   Detail: {detail}" if detail else "")

    def shutdown(self) -> None:
        """Clean shutdown of safety systems."""
        self.kill_switch.deactivate()
        self.audit.rotate()
        logger.info("Safety layer shut down cleanly")
