from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional


FixKind = Literal["config_change", "retry_step", "shell_step", "editor_step", "code_patch", "manual"]


@dataclass(frozen=True)
class FixAttempt:
    ts: float
    kind: FixKind
    description: str
    risk: str = "normal"
    payload: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None


def propose_fix_attempts(triangulation: Dict[str, Any]) -> List[FixAttempt]:
    """
    v1 scaffold: returns empty list.

    Future: turn triangulation candidates into concrete attempts.
    """
    _ = triangulation
    return []

