from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class ShellBlockedError(RuntimeError):
    pass


def _workspace_root_from_config(config: Dict[str, Any]) -> Optional[Path]:
    agents = config.get("agents", {}) if isinstance(config.get("agents"), dict) else {}
    defaults = agents.get("defaults", {}) if isinstance(agents.get("defaults"), dict) else {}
    workspace = defaults.get("workspace")
    root = str(workspace or "").strip()
    return Path(root) if root else None


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def run_command(
    *,
    command: str,
    artifacts_dir: str | Path,
    config: Dict[str, Any],
    timeout_seconds: int = 60,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a command with bounded output capture.

    Safety:
    - If allow_scope is workspace_only/workspace_writes, force cwd to workspace root
      and block attempts to set cwd outside it.
    """
    cmd = (command or "").strip()
    if not cmd:
        return {"ok": False, "error": "missing_command"}

    allow_scope = str(config.get("assistant_policy", {}).get("allow_scope") or "everything").strip().lower()
    root = _workspace_root_from_config(config)
    resolved_cwd: Optional[Path] = Path(cwd).resolve() if cwd else None

    if allow_scope in {"workspace_only", "workspace_writes", "workspace_only_writes"}:
        if not root:
            raise ShellBlockedError("workspace_root_not_configured")
        if resolved_cwd and not _is_under(resolved_cwd, root):
            raise ShellBlockedError("cwd_outside_workspace")
        resolved_cwd = root.resolve()

    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    stdout_path = out_dir / f"shell_stdout_{ts}.txt"
    stderr_path = out_dir / f"shell_stderr_{ts}.txt"

    start = time.monotonic()
    completed = subprocess.run(
        cmd,
        shell=True,
        cwd=str(resolved_cwd) if resolved_cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    duration_ms = int((time.monotonic() - start) * 1000)

    stdout_text = completed.stdout or ""
    stderr_text = completed.stderr or ""
    stdout_path.write_text(stdout_text, encoding="utf-8", errors="ignore")
    stderr_path.write_text(stderr_text, encoding="utf-8", errors="ignore")

    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "duration_ms": duration_ms,
        "cwd": str(resolved_cwd) if resolved_cwd else "",
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_tail": stdout_text[-2000:],
        "stderr_tail": stderr_text[-2000:],
    }

