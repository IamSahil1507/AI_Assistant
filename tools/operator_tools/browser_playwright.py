from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


class PlaywrightNotInstalledError(RuntimeError):
    pass


def _require_playwright():
    try:
        from playwright.async_api import async_playwright  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise PlaywrightNotInstalledError(
            "Playwright is not installed. Install with: pip install playwright && playwright install"
        ) from exc
    return async_playwright


def _profile_dir(artifacts_dir: str | Path) -> Path:
    out_dir = Path(artifacts_dir)
    return out_dir / "browser_profile"


def _system_chrome_user_data_dir() -> str:
    local = os.environ.get("LOCALAPPDATA") or ""
    if not local:
        return ""
    return str(Path(local) / "Google" / "Chrome" / "User Data")


async def _with_persistent_page(
    *,
    artifacts_dir: str | Path,
    viewport: Optional[Dict[str, int]] = None,
    headless: bool = True,
    use_system_chrome_profile: bool = False,
    chrome_profile_directory: str = "Default",
):
    """
    Context manager factory for a persistent Chromium context + a single page.

    Uses a per-task profile directory so cookies/sessions persist across steps.
    """
    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if use_system_chrome_profile:
        system_dir = _system_chrome_user_data_dir()
        profile = Path(system_dir) if system_dir else _profile_dir(out_dir)
    else:
        profile = _profile_dir(out_dir)
    profile.mkdir(parents=True, exist_ok=True)

    async_playwright = _require_playwright()
    p = await async_playwright().start()
    launch_args = [f"--profile-directory={chrome_profile_directory}"] if use_system_chrome_profile else []
    context = await p.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        headless=headless,
        viewport=viewport or {"width": 1280, "height": 720},
        channel="chrome" if use_system_chrome_profile else None,
        args=launch_args,
    )
    page = context.pages[0] if context.pages else await context.new_page()
    return p, context, page


async def open_url_screenshot_async(
    *,
    url: str,
    artifacts_dir: str | Path,
    timeout_ms: int = 30000,
    wait_until: str = "domcontentloaded",
    viewport: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Minimal browser action: open URL and capture screenshot.

    Returns a tool observation payload:
      { ok, url, screenshot_path, title, timing_ms }
    """
    if not url or not isinstance(url, str):
        return {"ok": False, "error": "missing_url"}

    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = out_dir / f"browser_{int(time.time())}.png"

    start = time.monotonic()
    p = context = page = None
    title = ""
    try:
        p, context, page = await _with_persistent_page(artifacts_dir=out_dir, viewport=viewport)
        await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        title = await page.title()
        await page.screenshot(path=str(screenshot_path), full_page=True)
    finally:
        try:
            if context is not None:
                await context.close()
        finally:
            if p is not None:
                await p.stop()
    timing_ms = int((time.monotonic() - start) * 1000)
    return {
        "ok": True,
        "url": url,
        "title": title,
        "screenshot_path": str(screenshot_path),
        "timing_ms": timing_ms,
    }


async def run_actions_async(
    *,
    artifacts_dir: str | Path,
    actions: Sequence[Dict[str, Any]],
    timeout_ms: int = 30000,
    viewport: Optional[Dict[str, int]] = None,
    headless: bool = True,
    use_system_chrome_profile: bool = False,
    chrome_profile_directory: str = "Default",
) -> Dict[str, Any]:
    """
    Run a sequence of browser actions with a persistent profile.

    Supported action types:
      - goto {url, wait_until?}
      - click {selector}
      - fill {selector, text}
      - press {selector?, key}
      - wait_for {selector, state?}
      - extract_text {selector}
      - screenshot {full_page?}

    Returns:
      { ok, url, title, screenshot_path?, extracted?, timing_ms, steps }
    """
    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted: Dict[str, str] = {}
    downloads: list[dict[str, Any]] = []
    steps: list[Dict[str, Any]] = []
    screenshot_path: Optional[Path] = None

    start = time.monotonic()
    p = context = page = None
    try:
        try:
            p, context, page = await _with_persistent_page(
                artifacts_dir=out_dir,
                viewport=viewport,
                headless=headless,
                use_system_chrome_profile=use_system_chrome_profile,
                chrome_profile_directory=chrome_profile_directory,
            )
        except Exception as exc:  # noqa: BLE001
            # Common: system Chrome profile is locked/in-use by an existing Chrome instance.
            # Fallback: use per-task profile so the operator can still proceed.
            if use_system_chrome_profile:
                steps.append(
                    {
                        "type": "profile_fallback",
                        "ok": False,
                        "error": str(exc),
                        "note": "System Chrome profile was unavailable; falling back to operator profile. "
                        "To use your default Chrome signed-in account, close all Chrome windows and retry.",
                    }
                )
                p, context, page = await _with_persistent_page(
                    artifacts_dir=out_dir,
                    viewport=viewport,
                    headless=headless,
                    use_system_chrome_profile=False,
                    chrome_profile_directory="Default",
                )
            else:
                raise
        for action in actions:
            if not isinstance(action, dict):
                continue
            typ = str(action.get("type") or "").strip().lower()
            try:
                if typ == "goto":
                    url = str(action.get("url") or "").strip()
                    wait_until = str(action.get("wait_until") or "domcontentloaded").strip()
                    await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                    steps.append({"type": "goto", "ok": True, "url": url})
                elif typ == "click":
                    selector = str(action.get("selector") or "").strip()
                    await page.click(selector, timeout=timeout_ms)
                    steps.append({"type": "click", "ok": True, "selector": selector})
                elif typ == "click_role":
                    role = str(action.get("role") or "").strip()
                    name = str(action.get("name") or "").strip()
                    locator = page.get_by_role(role, name=name) if name else page.get_by_role(role)
                    await locator.first.click(timeout=timeout_ms)
                    steps.append({"type": "click_role", "ok": True, "role": role, "name": name})
                elif typ == "click_text":
                    text = str(action.get("text") or "").strip()
                    locator = page.get_by_text(text, exact=bool(action.get("exact", False)))
                    await locator.first.click(timeout=timeout_ms)
                    steps.append({"type": "click_text", "ok": True, "text": text})
                elif typ == "fill":
                    selector = str(action.get("selector") or "").strip()
                    text = str(action.get("text") or "")
                    await page.fill(selector, text, timeout=timeout_ms)
                    steps.append({"type": "fill", "ok": True, "selector": selector})
                elif typ == "fill_role":
                    role = str(action.get("role") or "").strip()
                    name = str(action.get("name") or "").strip()
                    text = str(action.get("text") or "")
                    locator = page.get_by_role(role, name=name) if name else page.get_by_role(role)
                    await locator.first.fill(text, timeout=timeout_ms)
                    steps.append({"type": "fill_role", "ok": True, "role": role, "name": name})
                elif typ == "type":
                    selector = str(action.get("selector") or "").strip()
                    text = str(action.get("text") or "")
                    delay_ms = int(action.get("delay_ms") or 0)
                    if selector:
                        await page.click(selector, timeout=timeout_ms)
                    await page.keyboard.type(text, delay=delay_ms)
                    steps.append({"type": "type", "ok": True, "selector": selector, "chars": len(text)})
                elif typ == "press":
                    key = str(action.get("key") or "").strip()
                    selector = str(action.get("selector") or "").strip()
                    if selector:
                        await page.press(selector, key, timeout=timeout_ms)
                    else:
                        await page.keyboard.press(key)
                    steps.append({"type": "press", "ok": True, "key": key, "selector": selector})
                elif typ == "wait_for":
                    selector = str(action.get("selector") or "").strip()
                    state = str(action.get("state") or "visible").strip()
                    await page.wait_for_selector(selector, state=state, timeout=timeout_ms)
                    steps.append({"type": "wait_for", "ok": True, "selector": selector, "state": state})
                elif typ == "wait_for_url":
                    pattern = str(action.get("pattern") or "").strip()
                    await page.wait_for_url(pattern, timeout=timeout_ms)
                    steps.append({"type": "wait_for_url", "ok": True, "pattern": pattern})
                elif typ == "extract_text":
                    selector = str(action.get("selector") or "").strip()
                    el = await page.query_selector(selector)
                    txt = (await el.inner_text()) if el else ""
                    extracted[selector] = txt
                    steps.append({"type": "extract_text", "ok": True, "selector": selector, "chars": len(txt)})
                elif typ == "download_click":
                    selector = str(action.get("selector") or "").strip()
                    downloads_dir = out_dir / "downloads"
                    downloads_dir.mkdir(parents=True, exist_ok=True)
                    async with page.expect_download(timeout=timeout_ms) as dl_info:
                        await page.click(selector, timeout=timeout_ms)
                    dl = await dl_info.value
                    suggested = dl.suggested_filename
                    save_as = str(action.get("save_as") or suggested).strip() or suggested
                    dest = downloads_dir / save_as
                    await dl.save_as(str(dest))
                    downloads.append({"path": str(dest), "suggested_filename": suggested, "url": dl.url})
                    steps.append({"type": "download_click", "ok": True, "selector": selector, "path": str(dest)})
                elif typ == "screenshot":
                    full_page = bool(action.get("full_page", True))
                    screenshot_path = out_dir / f"browser_{int(time.time())}.png"
                    await page.screenshot(path=str(screenshot_path), full_page=full_page)
                    steps.append({"type": "screenshot", "ok": True, "path": str(screenshot_path)})
                else:
                    steps.append({"type": typ or "unknown", "ok": False, "error": "unsupported_action"})
            except Exception as exc:  # noqa: BLE001
                steps.append({"type": typ or "unknown", "ok": False, "error": str(exc)})
                # Capture best-effort screenshot for debugging.
                try:
                    screenshot_path = out_dir / f"browser_error_{int(time.time())}.png"
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    steps.append({"type": "error_screenshot", "ok": True, "path": str(screenshot_path)})
                except Exception as shot_exc:  # noqa: BLE001
                    steps.append({"type": "error_screenshot", "ok": False, "error": str(shot_exc)})
                url_now = getattr(page, "url", "")
                title_now = ""
                try:
                    title_now = await page.title()
                except Exception:
                    title_now = ""
                return {
                    "ok": False,
                    "error": str(exc),
                    "url": url_now,
                    "title": title_now,
                    "screenshot_path": str(screenshot_path) if screenshot_path else "",
                    "steps": steps,
                    "extracted": extracted,
                    "downloads": downloads,
                }

        if screenshot_path is None:
            screenshot_path = out_dir / f"browser_{int(time.time())}.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
        url_now = page.url
        title = await page.title()
    finally:
        try:
            if context is not None:
                await context.close()
        finally:
            if p is not None:
                await p.stop()

    timing_ms = int((time.monotonic() - start) * 1000)
    return {
        "ok": True,
        "url": url_now,
        "title": title,
        "screenshot_path": str(screenshot_path) if screenshot_path else "",
        "extracted": extracted,
        "downloads": downloads,
        "steps": steps,
        "timing_ms": timing_ms,
    }


def open_url_screenshot(**kwargs) -> Dict[str, Any]:
    """
    Sync wrapper (used by non-async callers).
    """
    return asyncio.run(open_url_screenshot_async(**kwargs))


def run_actions(**kwargs) -> Dict[str, Any]:
    return asyncio.run(run_actions_async(**kwargs))

