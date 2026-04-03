"""
NEXUS Layer 7: Internet Research Engine
Multi-source parallel search, content extraction, deduplication, ranking.

Queries Stack Overflow, GitHub, Reddit, official docs simultaneously.
Returns 3-5 genuinely different solutions, ranked by relevance.
"""

from __future__ import annotations

import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from nexus.config import RESEARCH_MAX_SOURCES, RESEARCH_TIMEOUT_SECONDS, RESEARCH_MAX_CONTENT_CHARS

logger = logging.getLogger("nexus.research")


# ──────────────────────────────────────────────
# Data Structures
# ──────────────────────────────────────────────

@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str     # stackoverflow | github | reddit | docs | blog
    authority: int   # 1-5 (5 = official docs)


@dataclass
class ExtractedSolution:
    description: str
    code_blocks: List[str]
    commands: List[str]
    source_url: str
    source_authority: int
    score: float = 0.0
    fingerprint: str = ""

    def __post_init__(self):
        if not self.fingerprint:
            raw = (self.description[:200] + "".join(self.code_blocks[:2])).lower()
            self.fingerprint = hashlib.md5(raw.encode()).hexdigest()[:12]


# ──────────────────────────────────────────────
# Search Engines
# ──────────────────────────────────────────────

def _search_duckduckgo(query: str, max_results: int = 10) -> List[SearchResult]:
    """Search via DuckDuckGo Lite (no API key needed)."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                    source=_classify_source(r.get("href", "")),
                    authority=_authority_score(r.get("href", "")),
                )
                for r in results
            ]
    except ImportError:
        logger.warning("duckduckgo-search not installed (pip install duckduckgo-search)")
        return []
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return []


def _classify_source(url: str) -> str:
    """Classify URL into source category."""
    lowered = url.lower()
    if "stackoverflow.com" in lowered:
        return "stackoverflow"
    elif "github.com" in lowered:
        return "github"
    elif "reddit.com" in lowered:
        return "reddit"
    elif any(d in lowered for d in [".readthedocs.", "docs.python", "docs.microsoft", "developer.mozilla"]):
        return "docs"
    elif "dev.to" in lowered or "medium.com" in lowered:
        return "blog"
    return "web"


def _authority_score(url: str) -> int:
    """Rate source authority (1-5)."""
    source = _classify_source(url)
    scores = {
        "docs": 5,
        "stackoverflow": 4,
        "github": 4,
        "reddit": 3,
        "blog": 2,
        "web": 1,
    }
    return scores.get(source, 1)


# ──────────────────────────────────────────────
# Content Extraction
# ──────────────────────────────────────────────

def _extract_page_content(url: str, timeout: int = 15) -> Dict[str, Any]:
    """Fetch and extract useful content from a URL."""
    try:
        headers = {"User-Agent": "NEXUS-Research/1.0 (AI Assistant)"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        html = resp.text[:RESEARCH_MAX_CONTENT_CHARS]
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}

    # Try BeautifulSoup for structured extraction
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()

        # Extract code blocks
        code_blocks = []
        for code in soup.find_all(["code", "pre"]):
            text = code.get_text().strip()
            if text and len(text) > 10:
                code_blocks.append(text[:2000])

        # Extract main text
        text = soup.get_text(separator="\n", strip=True)

        # Clean up
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = "\n".join(lines)[:RESEARCH_MAX_CONTENT_CHARS]

        return {
            "ok": True,
            "url": url,
            "text": text,
            "code_blocks": code_blocks[:10],
            "char_count": len(text),
        }
    except ImportError:
        # Fallback: basic text extraction
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return {
            "ok": True,
            "url": url,
            "text": text[:RESEARCH_MAX_CONTENT_CHARS],
            "code_blocks": [],
            "char_count": len(text),
        }


# ──────────────────────────────────────────────
# Solution Ranking (NEXUS Blueprint scoring)
# ──────────────────────────────────────────────

def _score_solution(
    solution: ExtractedSolution,
    error_signature: str,
    environment: Dict[str, Any],
) -> float:
    """
    Score a solution against the error context.
    Signals from NEXUS Blueprint:
    - Exact error message match: +30
    - Same library/version match: +25
    - Source authority: +20
    - Recency: +10
    """
    score = 0.0

    # Error message match
    desc_lower = solution.description.lower()
    error_lower = error_signature.lower()
    if error_lower in desc_lower:
        score += 30
    elif any(word in desc_lower for word in error_lower.split()[:5]):
        score += 15

    # Code block presence (solutions with code are better)
    if solution.code_blocks:
        score += 10
    if solution.commands:
        score += 5

    # Source authority (max +20)
    score += solution.source_authority * 4

    # Has actual fix content (not just discussion)
    fix_keywords = ["fix", "solution", "resolved", "solved", "answer", "workaround"]
    if any(kw in desc_lower for kw in fix_keywords):
        score += 10

    return score


# ──────────────────────────────────────────────
# Semantic Deduplication
# ──────────────────────────────────────────────

def _deduplicate(solutions: List[ExtractedSolution]) -> List[ExtractedSolution]:
    """Remove semantically identical solutions."""
    seen_fingerprints = set()
    unique = []
    for sol in solutions:
        if sol.fingerprint not in seen_fingerprints:
            seen_fingerprints.add(sol.fingerprint)
            unique.append(sol)
    return unique


# ──────────────────────────────────────────────
# Research Engine — Main Interface
# ──────────────────────────────────────────────

class ResearchEngine:
    """
    NEXUS Layer 7 — Internet Research.
    
    Pipeline:
    1. Multi-source parallel search
    2. Content extraction from top results
    3. Solution parsing (code blocks, commands)
    4. Semantic deduplication
    5. Authority-weighted ranking
    6. Return top 3-5 distinct solutions
    """

    def __init__(self, brain: Optional[Any] = None):
        self.brain = brain
        self.executor = ThreadPoolExecutor(max_workers=4)

    def research(
        self,
        error_signature: str,
        *,
        environment: Optional[Dict[str, Any]] = None,
        max_solutions: int = RESEARCH_MAX_SOURCES,
        fetch_content: bool = True,
    ) -> Dict[str, Any]:
        """
        Full research pipeline for an error.
        Returns 3-5 ranked, deduplicated solutions.
        """
        start = time.monotonic()
        environment = environment or {}

        # Step 1: Search multiple queries in parallel
        queries = self._generate_search_queries(error_signature, environment)
        all_results: List[SearchResult] = []

        futures = {
            self.executor.submit(_search_duckduckgo, q, 5): q
            for q in queries
        }
        for future in as_completed(futures, timeout=RESEARCH_TIMEOUT_SECONDS):
            try:
                results = future.result()
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Search query failed: {e}")

        if not all_results:
            return {
                "ok": False,
                "error": "no_search_results",
                "duration_ms": int((time.monotonic() - start) * 1000),
            }

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                unique_results.append(r)

        # Sort by authority
        unique_results.sort(key=lambda r: r.authority, reverse=True)

        # Step 2: Fetch content from top results
        solutions: List[ExtractedSolution] = []
        if fetch_content:
            top_urls = unique_results[:8]
            content_futures = {
                self.executor.submit(_extract_page_content, r.url): r
                for r in top_urls
            }
            for future in as_completed(content_futures, timeout=RESEARCH_TIMEOUT_SECONDS):
                try:
                    content = future.result()
                    result = content_futures[future]
                    if content.get("ok"):
                        solutions.append(ExtractedSolution(
                            description=content.get("text", "")[:1000],
                            code_blocks=content.get("code_blocks", []),
                            commands=[],
                            source_url=result.url,
                            source_authority=result.authority,
                        ))
                except Exception:
                    continue
        else:
            # Use snippets only
            for r in unique_results[:10]:
                solutions.append(ExtractedSolution(
                    description=r.snippet,
                    code_blocks=[],
                    commands=[],
                    source_url=r.url,
                    source_authority=r.authority,
                ))

        # Step 3: Deduplicate
        solutions = _deduplicate(solutions)

        # Step 4: Score and rank
        for sol in solutions:
            sol.score = _score_solution(sol, error_signature, environment)
        solutions.sort(key=lambda s: s.score, reverse=True)

        # Step 5: Return top N
        top_solutions = solutions[:max_solutions]

        duration_ms = int((time.monotonic() - start) * 1000)
        return {
            "ok": True,
            "error_signature": error_signature,
            "solutions_count": len(top_solutions),
            "total_results_found": len(all_results),
            "solutions": [
                {
                    "rank": i + 1,
                    "score": sol.score,
                    "description": sol.description[:500],
                    "code_blocks": sol.code_blocks[:3],
                    "source_url": sol.source_url,
                    "source_authority": sol.source_authority,
                }
                for i, sol in enumerate(top_solutions)
            ],
            "duration_ms": duration_ms,
        }

    def _generate_search_queries(
        self,
        error_signature: str,
        environment: Dict[str, Any],
    ) -> List[str]:
        """Generate multiple search queries for parallel fetch."""
        queries = [error_signature]

        # Add environment context
        lang = environment.get("language", "python")
        queries.append(f"{error_signature} {lang} fix")
        queries.append(f"{error_signature} solution stackoverflow")

        # Add library context if available
        lib = environment.get("library", "")
        if lib:
            queries.append(f"{error_signature} {lib}")

        return queries[:4]  # Max 4 parallel queries

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False)
