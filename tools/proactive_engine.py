from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Callable, List

from tools import assistant_state


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProactiveEngine:
    def __init__(self, config_provider: Callable[[], Dict[str, Any]], tick_callbacks: Optional[List[Callable[[], Any]]] = None) -> None:
        self._config_provider = config_provider
        self._tick_callbacks = tick_callbacks or []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_tick: Optional[str] = None

    def start(self) -> bool:
        if self._running:
            return False
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        assistant_state.set_status("proactive_status", "running")
        return True

    def stop(self) -> bool:
        if not self._running:
            return False
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        assistant_state.set_status("proactive_status", "stopped")
        return True

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "last_tick": self._last_tick,
        }

    def _loop(self) -> None:
        while self._running:
            self._tick()
            interval = self._interval_seconds()
            time.sleep(interval)

    def _interval_seconds(self) -> float:
        config = self._config_provider() or {}
        proactive = config.get("assistant_proactive", {}) if isinstance(config.get("assistant_proactive"), dict) else {}
        interval = proactive.get("interval_seconds", 30)
        try:
            return max(5.0, float(interval))
        except (TypeError, ValueError):
            return 30.0

    def _tick(self) -> None:
        now = _now_iso()
        self._last_tick = now
        assistant_state.set_status("last_heartbeat", now)
        for callback in list(self._tick_callbacks):
            try:
                callback()
            except Exception:
                continue
        tasks = assistant_state.list_tasks(include_history=False).get("queue", [])
        overdue = []
        for task in tasks:
            due_at = task.get("metadata", {}).get("due_at")
            if not due_at:
                continue
            try:
                due_ts = datetime.fromisoformat(due_at)
            except ValueError:
                continue
            if due_ts <= datetime.now(timezone.utc):
                overdue.append(task)
        for task in overdue:
            assistant_state.add_action_log(
                action=f"Reminder: {task.get('description')}",
                status="reminder",
                detail=f"task_id={task.get('id')}",
                source="proactive",
            )
