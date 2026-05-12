"""Core data model.

A `Paper` is the unified record produced by every source (arXiv + blogs).
A `Decision` records why a paper was included or excluded from each feed
— this is the introspection surface the README points users to.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class Affiliation:
    """One institutional affiliation for an author at submission time."""
    name: str            # canonical normalized name, e.g. "Google/DeepMind"
    raw: str = ""        # raw string as it appeared in the source
    country: str = ""    # ISO 3166-1 alpha-2 if known


@dataclass
class Author:
    """An author on a paper, possibly enriched via OpenAlex."""
    name: str
    openalex_id: Optional[str] = None
    affiliations: list[Affiliation] = field(default_factory=list)
    # h-index from OpenAlex (a.k.a. summary_stats.h_index). None means "not resolved".
    h_index: Optional[int] = None
    cited_by_count: Optional[int] = None
    is_senior: bool = False   # filled by filter stage

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class Paper:
    """Unified record of a paper (or blog research post)."""
    id: str                   # globally unique; e.g. "arxiv:2501.12345" or "anthropic:slug"
    source: str               # "arxiv" | "anthropic" | "openai" | ...
    title: str
    abstract: str
    authors: list[Author]
    categories: list[str]     # arXiv cats or source-specific tags
    url: str                  # canonical URL
    pdf_url: str = ""
    published_at: Optional[datetime] = None
    raw: dict[str, Any] = field(default_factory=dict)  # source-native extras

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.published_at:
            d["published_at"] = self.published_at.isoformat()
        return d


@dataclass
class Decision:
    """Why this paper did or didn't make it into each feed.

    A `Decision` is the introspection record. `paper-radar explain <id>`
    prints this, and the daily run emits all decisions to a JSONL log so
    you can grep / diff them across runs.
    """
    paper_id: str
    title: str
    accepted: bool
    feeds: list[str] = field(default_factory=list)
    tier1_matches: list[str] = field(default_factory=list)
    tier2_matches: list[str] = field(default_factory=list)
    senior_authors: list[str] = field(default_factory=list)
    matched_keywords: dict[str, list[str]] = field(default_factory=dict)  # feed -> keywords
    reasons: list[str] = field(default_factory=list)   # human-readable bullets
    rejected_by_feed: dict[str, str] = field(default_factory=dict)  # feed -> why excluded

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
