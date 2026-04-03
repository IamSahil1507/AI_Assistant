"""
NEXUS Layer 5: Situational Intelligence
The layer that makes NEXUS *aware* — of you and your machine.

Reads two live streams:
- Stream A: User signals (mood, urgency, expertise, retry count, time of day)
- Stream B: System signals (RAM free, CPU load, VRAM, active app, network)

Builds a context_profile dict injected into every LLM prompt.
"""

from __future__ import annotations

import time
import logging
import platform
from datetime import datetime
from typing import Any, Dict, List, Optional

from nexus.config import (
    SI_POLL_INTERVAL_SECONDS,
    SI_RAM_CRITICAL_GB, SI_RAM_WARNING_GB,
    SI_CPU_HIGH_THRESHOLD, SI_VRAM_CRITICAL_GB,
    SI_LATE_NIGHT_START, SI_LATE_NIGHT_END,
    SI_MAX_RETRIES_BEFORE_CAUTION,
    FAST_BRAIN, THINK_BRAIN,
)

logger = logging.getLogger("nexus.si")


# ──────────────────────────────────────────────
# System Monitors
# ──────────────────────────────────────────────

def _get_ram_info() -> Dict[str, float]:
    """Get RAM info via psutil."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {
            "total_gb": round(vm.total / (1024**3), 1),
            "available_gb": round(vm.available / (1024**3), 1),
            "used_pct": vm.percent,
        }
    except ImportError:
        logger.warning("psutil not installed — RAM monitoring disabled")
        return {"total_gb": 16.0, "available_gb": 8.0, "used_pct": 50.0}


def _get_cpu_info() -> Dict[str, float]:
    """Get CPU load via psutil."""
    try:
        import psutil
        return {
            "percent": psutil.cpu_percent(interval=0.5),
            "freq_mhz": (psutil.cpu_freq().current if psutil.cpu_freq() else 0),
        }
    except ImportError:
        return {"percent": 0.0, "freq_mhz": 0}


def _get_vram_info() -> Dict[str, float]:
    """Get GTX 1650 VRAM info via pynvml."""
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        total_gb = round(info.total / (1024**3), 2)
        free_gb = round(info.free / (1024**3), 2)
        used_gb = round(info.used / (1024**3), 2)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8")
        pynvml.nvmlShutdown()
        return {
            "name": name,
            "total_gb": total_gb,
            "free_gb": free_gb,
            "used_gb": used_gb,
            "used_pct": round((used_gb / total_gb) * 100, 1) if total_gb > 0 else 0,
        }
    except (ImportError, Exception) as e:
        logger.warning(f"pynvml not available ({e}) — VRAM monitoring disabled")
        return {"name": "GTX 1650", "total_gb": 4.0, "free_gb": 2.0, "used_gb": 2.0, "used_pct": 50.0}


def _get_active_window() -> str:
    """Get foreground window title on Windows via pywin32."""
    try:
        if platform.system() != "Windows":
            return "unknown"
        import win32gui  # type: ignore
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        return title if title else "unknown"
    except (ImportError, Exception):
        return "unknown"


def _check_network() -> str:
    """Simple network check via ping."""
    try:
        import requests
        r = requests.get("https://www.google.com", timeout=3)
        return "ok" if r.status_code == 200 else "degraded"
    except Exception:
        return "offline"


# ──────────────────────────────────────────────
# User Signal Parser
# ──────────────────────────────────────────────

class UserSignalParser:
    """Parses user signals from message text and task metadata."""

    # Frustration indicators
    FRUSTRATION_WORDS = {
        "wtf", "broken", "doesn't work", "not working", "again", "still",
        "frustrated", "annoyed", "ugh", "damn", "stupid", "hate",
        "why won't", "can't believe", "wasted", "hours", "help me",
    }

    URGENCY_WORDS = {
        "urgent", "asap", "now", "immediately", "hurry", "deadline",
        "quick", "fast", "rush", "critical", "emergency",
    }

    BEGINNER_WORDS = {
        "what is", "how do i", "explain", "tutorial", "beginner",
        "new to", "first time", "don't understand", "confused",
        "what does", "step by step", "simple",
    }

    def parse(self, text: str, retry_count: int = 0) -> Dict[str, Any]:
        """Parse user signals from message text."""
        lowered = text.lower()

        # Detect mood
        frustration_score = sum(1 for w in self.FRUSTRATION_WORDS if w in lowered)
        mood = "frustrated" if frustration_score >= 2 else (
            "stressed" if frustration_score == 1 else "calm"
        )

        # Detect urgency
        urgency_score = sum(1 for w in self.URGENCY_WORDS if w in lowered)
        urgency = "high" if urgency_score >= 1 or retry_count >= 3 else "normal"

        # Detect expertise
        beginner_score = sum(1 for w in self.BEGINNER_WORDS if w in lowered)
        expertise = "beginner" if beginner_score >= 2 else (
            "intermediate" if beginner_score == 1 else "expert"
        )

        # Time of day
        hour = datetime.now().hour
        is_late = SI_LATE_NIGHT_START <= hour or hour < SI_LATE_NIGHT_END

        return {
            "mood": mood,
            "urgency": urgency,
            "expertise": expertise,
            "retry_count": retry_count,
            "hour": hour,
            "is_late_night": is_late,
            "text_length": len(text),
            "frustration_score": frustration_score,
        }


# ──────────────────────────────────────────────
# Rule Engine
# ──────────────────────────────────────────────

class AdaptiveRuleEngine:
    """
    Derives behavior rules from user + system signals.
    These rules are injected into every LLM prompt.
    """

    def derive_rules(
        self,
        user: Dict[str, Any],
        system: Dict[str, Any],
    ) -> List[str]:
        """Generate adaptive behavior rules based on current context."""
        rules: List[str] = []

        # ── RAM Rules ──
        ram_free = system.get("ram_free_gb", 8.0)
        if ram_free < SI_RAM_CRITICAL_GB:
            rules.append(f"⚠️ Use {FAST_BRAIN} only — RAM critical ({ram_free:.1f}GB free)")
        elif ram_free < SI_RAM_WARNING_GB:
            rules.append(f"RAM low ({ram_free:.1f}GB) — prefer lightweight operations")

        # ── VRAM Rules ──
        vram_free = system.get("vram_free_gb", 2.0)
        if vram_free < SI_VRAM_CRITICAL_GB:
            rules.append(f"⚠️ VRAM critical ({vram_free:.2f}GB) — use CPU-only mode")

        # ── CPU Rules ──
        cpu_pct = system.get("cpu_pct", 0)
        if cpu_pct > SI_CPU_HIGH_THRESHOLD:
            rules.append(f"CPU under heavy load ({cpu_pct}%) — defer resource-intensive tasks")

        # ── Retry / Frustration Rules ──
        retry_count = user.get("retry_count", 0)
        mood = user.get("mood", "calm")
        if retry_count >= SI_MAX_RETRIES_BEFORE_CAUTION and mood == "frustrated":
            rules.append("Confirm every step — multiple retries + frustration detected")
            rules.append("Use gentle, empathetic language — acknowledge the difficulty")
        elif retry_count >= SI_MAX_RETRIES_BEFORE_CAUTION:
            rules.append(f"Step {retry_count} retries — try a different approach this time")

        # ── Late Night Rules ──
        if user.get("is_late_night", False):
            rules.append("🌙 Silent mode — no popups, subtle status, minimize interruptions")

        # ── Active App Rules ──
        active_app = system.get("active_app", "")
        if any(kw in active_app.lower() for kw in ["vs code", "visual studio", "code"]):
            rules.append("🎯 Focus mode — VS Code detected, non-blocking alerts only")
        elif any(kw in active_app.lower() for kw in ["terminal", "powershell", "cmd"]):
            rules.append("🎯 Focus mode — Terminal detected, non-blocking alerts only")

        # ── Expertise Rules ──
        expertise = user.get("expertise", "intermediate")
        if expertise == "beginner":
            rules.append("Use step-by-step explanations with 'why' for each step")
        elif expertise == "expert" and mood == "calm":
            rules.append("Dense, technical responses — skip hand-holding")

        # ── Network Rules ──
        network = system.get("network", "ok")
        if network == "offline":
            rules.append("🔌 Network offline — local models only, disable web search")
        elif network == "degraded":
            rules.append("Network unstable — prefer local operations")

        return rules


# ──────────────────────────────────────────────
# Situational Intelligence Layer
# ──────────────────────────────────────────────

class SituationalIntelligence:
    """
    NEXUS Layer 5 — The awareness engine.
    
    Call build_context() before every LLM call to get the full
    context_profile with user signals, system state, and adaptive rules.
    """

    def __init__(self):
        self.user_parser = UserSignalParser()
        self.rule_engine = AdaptiveRuleEngine()
        self._last_system_poll: float = 0.0
        self._cached_system: Dict[str, Any] = {}
        self._retry_counter: Dict[str, int] = {}  # task_id -> retry count

    def build_context(
        self,
        user_message: str = "",
        *,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build the full context_profile for injection into LLM prompts.
        This is called before EVERY LLM call.
        
        Returns the exact dict shape from the NEXUS Blueprint:
        {
            "user": { mood, urgency, expertise, retry_count, hour, ... },
            "system": { ram_free_gb, cpu_pct, vram_free_gb, network, active_app, ... },
            "rules": [ "rule1", "rule2", ... ]
        }
        """
        # Get retry count for this task
        retry_count = 0
        if task_id:
            retry_count = self._retry_counter.get(task_id, 0)

        # Parse user signals
        user_signals = self.user_parser.parse(user_message, retry_count=retry_count)

        # Poll system state (with caching to avoid overhead)
        system_state = self._poll_system()

        # Derive adaptive rules
        rules = self.rule_engine.derive_rules(user_signals, system_state)

        return {
            "user": user_signals,
            "system": system_state,
            "rules": rules,
        }

    def increment_retry(self, task_id: str) -> int:
        """Track retry count for a task."""
        self._retry_counter[task_id] = self._retry_counter.get(task_id, 0) + 1
        return self._retry_counter[task_id]

    def reset_retry(self, task_id: str) -> None:
        """Reset retry count on success."""
        self._retry_counter.pop(task_id, None)

    def _poll_system(self) -> Dict[str, Any]:
        """Poll system state with caching (every SI_POLL_INTERVAL_SECONDS)."""
        now = time.time()
        if now - self._last_system_poll < SI_POLL_INTERVAL_SECONDS and self._cached_system:
            return self._cached_system

        ram = _get_ram_info()
        cpu = _get_cpu_info()
        vram = _get_vram_info()
        active_app = _get_active_window()
        network = _check_network()

        self._cached_system = {
            "ram_free_gb": ram["available_gb"],
            "ram_used_pct": ram["used_pct"],
            "cpu_pct": cpu["percent"],
            "vram_free_gb": vram["free_gb"],
            "vram_used_pct": vram["used_pct"],
            "gpu_name": vram["name"],
            "network": network,
            "active_app": active_app,
            "polled_at": now,
        }
        self._last_system_poll = now
        return self._cached_system

    def get_model_recommendation(self) -> str:
        """Recommend which brain to use based on current system state."""
        system = self._poll_system()
        vram_free = system.get("vram_free_gb", 2.0)
        ram_free = system.get("ram_free_gb", 8.0)

        if vram_free < 1.0 or ram_free < SI_RAM_CRITICAL_GB:
            return FAST_BRAIN  # phi3 — safest
        elif vram_free >= 2.5 and ram_free >= 6.0:
            return THINK_BRAIN  # qwen3.5 — full power
        else:
            return FAST_BRAIN  # phi3 — play it safe
