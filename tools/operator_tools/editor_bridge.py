from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests


class EditorBridgeError(RuntimeError):
    pass


def _base_url(config: Dict[str, Any]) -> str:
    bridge_cfg = config.get("editor_bridge") if isinstance(config.get("editor_bridge"), dict) else {}
    host = str(bridge_cfg.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    port = int(bridge_cfg.get("port") or 18999)
    return f"http://{host}:{port}"


def health(config: Dict[str, Any], timeout: int = 5) -> Dict[str, Any]:
    url = _base_url(config).rstrip("/") + "/health"
    try:
        resp = requests.get(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    if resp.status_code >= 400:
        return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text.strip()[:200]}"}
    try:
        data = resp.json()
    except Exception:
        data = {}
    return {"ok": True, "data": data}


def _post_with_retry(
    config: Dict[str, Any],
    path: str,
    payload: Dict[str, Any],
    *,
    timeout: int = 20,
    retries: int = 2,
) -> Dict[str, Any]:
    last_err = None
    for attempt in range(retries + 1):
        try:
            return _post(config, path, payload, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            # small backoff
            time.sleep(0.25 * (attempt + 1))
    raise EditorBridgeError(last_err or "editor_bridge_failed")


def _post(config: Dict[str, Any], path: str, payload: Dict[str, Any], timeout: int = 20) -> Dict[str, Any]:
    url = _base_url(config).rstrip("/") + path
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise EditorBridgeError(str(exc)) from exc
    if resp.status_code >= 400:
        raise EditorBridgeError(f"HTTP {resp.status_code}: {resp.text.strip()[:500]}")
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise EditorBridgeError(f"invalid_json: {exc}") from exc
    if not isinstance(data, dict):
        raise EditorBridgeError("invalid_response_shape")
    return data


def open_file(*, path: str, config: Dict[str, Any]) -> Dict[str, Any]:
    return _post_with_retry(config, "/openFile", {"path": path})


def search(*, query: str, include: str, config: Dict[str, Any]) -> Dict[str, Any]:
    return _post_with_retry(config, "/search", {"query": query, "include": include})


def apply_edits(*, path: str, edits: list[dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    return _post_with_retry(config, "/applyEdits", {"path": path, "edits": edits}, timeout=60)


def run_task(*, name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    return _post_with_retry(config, "/runTask", {"name": name}, timeout=60)

