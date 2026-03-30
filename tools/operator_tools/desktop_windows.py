from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional


class DesktopToolNotInstalledError(RuntimeError):
    pass


def _require_pywinauto():
    try:
        from pywinauto import Application  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise DesktopToolNotInstalledError("pywinauto is not installed. Install with: pip install pywinauto") from exc
    return Application


def _require_desktop():
    try:
        from pywinauto import Desktop  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise DesktopToolNotInstalledError("pywinauto is not installed. Install with: pip install pywinauto") from exc
    return Desktop


def _require_imagegrab():
    try:
        from PIL import ImageGrab  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise DesktopToolNotInstalledError("Pillow is required for screenshots (pip install pillow)") from exc
    return ImageGrab


def list_windows(*, max_items: int = 50) -> Dict[str, Any]:
    Desktop = _require_desktop()
    items = []
    try:
        wins = Desktop(backend="uia").windows()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "windows": []}
    for w in wins[: max(1, int(max_items))]:
        try:
            items.append(
                {
                    "title": w.window_text(),
                    "class_name": w.friendly_class_name(),
                    "handle": int(getattr(w, "handle", 0) or 0),
                }
            )
        except Exception:
            continue
    return {"ok": True, "windows": items, "count": len(items)}


def screenshot_full(*, artifacts_dir: str | Path) -> Dict[str, Any]:
    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ImageGrab = _require_imagegrab()
    path = out_dir / f"desktop_full_{int(time.time())}.png"
    img = ImageGrab.grab(all_screens=True)
    img.save(path)
    return {"ok": True, "screenshot_path": str(path)}


def screenshot_window_title(*, title_contains: str, artifacts_dir: str | Path) -> Dict[str, Any]:
    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ImageGrab = _require_imagegrab()
    Desktop = _require_desktop()
    needle = (title_contains or "").strip()
    if not needle:
        return {"ok": False, "error": "missing_title_contains"}
    try:
        wins = Desktop(backend="uia").windows()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    match = None
    for w in wins:
        try:
            if needle.lower() in (w.window_text() or "").lower():
                match = w
                break
        except Exception:
            continue
    if match is None:
        return {"ok": False, "error": "window_not_found"}
    try:
        rect = match.rectangle()
        bbox = (rect.left, rect.top, rect.right, rect.bottom)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    path = out_dir / f"desktop_window_{int(time.time())}.png"
    img = ImageGrab.grab(bbox=bbox)
    img.save(path)
    return {"ok": True, "screenshot_path": str(path), "title": match.window_text()}


def launch_app(*, command: str, artifacts_dir: str | Path) -> Dict[str, Any]:
    cmd = (command or "").strip()
    if not cmd:
        return {"ok": False, "error": "missing_command"}
    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    Application = _require_pywinauto()
    start = time.monotonic()
    try:
        app = Application(backend="uia").start(cmd)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    duration_ms = int((time.monotonic() - start) * 1000)
    return {"ok": True, "command": cmd, "duration_ms": duration_ms, "note": "app_started"}


def launch_notepad(*, artifacts_dir: str | Path) -> Dict[str, Any]:
    """
    Launch Notepad and return a basic handle descriptor.
    """
    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    Application = _require_pywinauto()
    start = time.monotonic()
    app = Application(backend="uia").start("notepad.exe")
    win = app.window(best_match="Notepad")
    win.wait("ready", timeout=10)
    duration_ms = int((time.monotonic() - start) * 1000)
    return {
        "ok": True,
        "app": "notepad",
        "duration_ms": duration_ms,
        "note": "Window launched. Screenshot support is a later step.",
    }


def type_in_notepad(*, text: str, artifacts_dir: str | Path) -> Dict[str, Any]:
    """
    Best-effort: connect to an existing Notepad window and type.
    """
    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    Application = _require_pywinauto()
    start = time.monotonic()
    app = Application(backend="uia").connect(title_re=".*Notepad.*")
    win = app.window(title_re=".*Notepad.*")
    win.set_focus()
    edit = win.child_window(control_type="Edit")
    edit.type_keys(text, with_spaces=True, set_foreground=True)
    duration_ms = int((time.monotonic() - start) * 1000)
    return {"ok": True, "app": "notepad", "duration_ms": duration_ms, "chars": len(text)}

