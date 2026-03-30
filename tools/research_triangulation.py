from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ResearchSource:
    title: str
    url: str
    snippet: str
    credibility: str = "unknown"  # official|issue_tracker|community|unknown


@dataclass(frozen=True)
class ResearchCandidateFix:
    description: str
    confidence: float
    reasons: List[str]
    source_urls: List[str]


def rank_sources(sources: List[ResearchSource]) -> List[ResearchSource]:
    weight = {"official": 4, "issue_tracker": 3, "community": 2, "unknown": 1}
    return sorted(sources, key=lambda s: weight.get(s.credibility, 1), reverse=True)


def triangulate(
    *,
    error_signature: str,
    environment: Dict[str, Any],
    sources: List[ResearchSource],
) -> Dict[str, Any]:
    """
    Scaffolding for multi-source research triangulation.

    v1 behavior:
    - rank sources by credibility
    - return a structured record that later steps can use to propose fixes

    Future: extract concrete fix candidates from sources using LLM, compare contradictions,
    and select best-fit based on environment + exact error.
    """
    ranked = rank_sources(sources)
    env_keys = sorted(list(environment.keys()))[:50]
    return {
        "error_signature": error_signature,
        "environment_keys": env_keys,
        "sources_ranked": [
            {"title": s.title, "url": s.url, "credibility": s.credibility, "snippet": s.snippet[:500]}
            for s in ranked
        ],
        "candidates": [],
        "note": "triangulation_scaffold_only",
    }

