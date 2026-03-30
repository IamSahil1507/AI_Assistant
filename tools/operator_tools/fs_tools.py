from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class FsBlockedError(RuntimeError):
    pass


SENSITIVE_NAME_HINTS = (
    ".env",
    "secrets",
    "credentials",
    ".pem",
    ".key",
    "id_rsa",
    "token",
)


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


def _check_scope(config: Dict[str, Any], path: Path) -> None:
    allow_scope = str(config.get("assistant_policy", {}).get("allow_scope") or "everything").strip().lower()
    if allow_scope in {"workspace_only", "workspace_writes", "workspace_only_writes"}:
        root = _workspace_root_from_config(config)
        if not root:
            raise FsBlockedError("workspace_root_not_configured")
        if not _is_under(path, root):
            raise FsBlockedError("path_outside_workspace")


def list_dir(
    *,
    path: str,
    config: Dict[str, Any],
    max_entries: int = 200,
) -> Dict[str, Any]:
    p = Path(path).expanduser()
    _check_scope(config, p)
    if not p.exists():
        return {"ok": False, "error": "not_found", "path": str(p)}
    if not p.is_dir():
        return {"ok": False, "error": "not_a_directory", "path": str(p)}
    entries: List[Dict[str, Any]] = []
    for idx, child in enumerate(sorted(p.iterdir(), key=lambda x: x.name.lower())):
        if idx >= max_entries:
            break
        try:
            st = child.stat()
            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "type": "dir" if child.is_dir() else "file",
                    "size": st.st_size if child.is_file() else None,
                }
            )
        except OSError:
            continue
    return {"ok": True, "path": str(p), "entries": entries, "truncated": len(entries) >= max_entries}


def read_text(
    *,
    path: str,
    config: Dict[str, Any],
    max_bytes: int = 200_000,
) -> Dict[str, Any]:
    p = Path(path).expanduser()
    _check_scope(config, p)
    if not p.exists() or not p.is_file():
        return {"ok": False, "error": "not_found", "path": str(p)}
    name_lower = p.name.lower()
    if any(hint in name_lower for hint in SENSITIVE_NAME_HINTS):
        # Don't read sensitive candidates by default; return metadata only.
        st = p.stat()
        return {"ok": False, "error": "sensitive_file_blocked", "path": str(p), "size": st.st_size}
    st = p.stat()
    if st.st_size > max_bytes:
        return {"ok": False, "error": "file_too_large", "path": str(p), "size": st.st_size, "max_bytes": max_bytes}
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return {"ok": False, "error": str(exc), "path": str(p)}
    return {"ok": True, "path": str(p), "chars": len(text), "text": text}


def write_text(
    *,
    path: str,
    text: str,
    config: Dict[str, Any],
    create_dirs: bool = True,
) -> Dict[str, Any]:
    p = Path(path).expanduser()
    _check_scope(config, p)
    allow_scope = str(config.get("assistant_policy", {}).get("allow_scope") or "everything").strip().lower()
    if allow_scope in {"open_readonly", "open-readonly", "open_read_only"}:
        raise FsBlockedError("allow_scope_readonly")
    if create_dirs:
        p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(text or "", encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": str(exc), "path": str(p)}
    return {"ok": True, "path": str(p), "bytes": len((text or "").encode('utf-8'))}

