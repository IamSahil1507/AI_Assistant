from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import requests

from tools.research_triangulation import ResearchSource, triangulate


def _fetch_url(url: str, timeout: int = 15) -> str:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "AwarenetResearch/1.0"})
    resp.raise_for_status()
    text = resp.text or ""
    # keep bounded
    return text[:50_000]


def run_research(
    *,
    error_signature: str,
    environment: Dict[str, Any],
    sources: List[Dict[str, Any]],
    fetch_urls: bool = False,
) -> Dict[str, Any]:
    """
    Research runner that accepts 3–5 sources (local summaries and/or web URLs).

    - If fetch_urls=True, will fetch URL contents (bounded) and attach as `fetched`.
    - Always runs triangulation ranking and returns a structured record.
    """
    parsed: List[ResearchSource] = []
    fetched: List[Dict[str, Any]] = []
    for src in sources:
        if not isinstance(src, dict):
            continue
        title = str(src.get("title") or "").strip() or "source"
        url = str(src.get("url") or "").strip()
        snippet = str(src.get("snippet") or "").strip()
        credibility = str(src.get("credibility") or "unknown").strip()
        parsed.append(ResearchSource(title=title, url=url, snippet=snippet, credibility=credibility))
        if fetch_urls and url:
            try:
                content = _fetch_url(url)
                fetched.append({"url": url, "ok": True, "chars": len(content), "content": content})
            except Exception as exc:  # noqa: BLE001
                fetched.append({"url": url, "ok": False, "error": str(exc)})

    tri = triangulate(error_signature=error_signature, environment=environment, sources=parsed)
    return {
        "ts": time.time(),
        "error_signature": error_signature,
        "triangulation": tri,
        "sources_count": len(parsed),
        "fetched": fetched,
    }

