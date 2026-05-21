"""Hugging Face Daily Papers — community-curated frontier-paper aggregator.

Returns Papers keyed by the underlying arXiv ID so they dedupe correctly
with our arxiv pull. The HF "endorsement" is encoded by adding a synthetic
author affiliated with "Hugging Face Daily Papers" — that triggers a tier-1
match in the filter, so an HF-surfaced paper gets in regardless of author
affiliation.

IMPORTANT: HF's /api/daily_papers returns ~50 papers per day — that's
"papers people submitted," not "the best papers." Auto-including all 50
floods the feed. So we gate by community upvotes: only the top
MAX_PAPERS by upvote count, and only those clearing MIN_UPVOTES, are
emitted. Tune the two constants below.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Iterable

import requests

from paper_radar.types import Affiliation, Author, Paper
from . import _common

log = logging.getLogger(__name__)

API_URL = "https://huggingface.co/api/daily_papers"
LAB_NAME = "Hugging Face Daily Papers"

# Upvote gating — the fix for HF flooding the feed.
MIN_UPVOTES = 10    # a paper needs real community engagement to qualify
MAX_PAPERS = 10     # hard cap per run, even if more clear MIN_UPVOTES


def fetch(limit: int = MAX_PAPERS) -> Iterable[Paper]:
    try:
        r = requests.get(API_URL, headers=_common.HEADERS, timeout=30)
        if r.status_code != 200:
            log.warning("huggingface_papers: HTTP %d", r.status_code)
            return
        data = r.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        log.warning("huggingface_papers: %s", e)
        return

    # Sort by upvotes descending, keep only those above the floor.
    def upvotes(entry):
        return (entry.get("paper") or {}).get("upvotes") or 0

    ranked = sorted(data, key=upvotes, reverse=True)
    qualified = [e for e in ranked if upvotes(e) >= MIN_UPVOTES][:limit]
    log.info("huggingface_papers: %d/%d papers clear %d+ upvotes",
             len(qualified), len(data), MIN_UPVOTES)

    seen = 0
    for entry in qualified:
        paper = entry.get("paper") or {}
        arxiv_id = paper.get("id")
        title = paper.get("title")
        if not (arxiv_id and title):
            continue

        # arXiv IDs sometimes have version suffix like "2506.01015v2" — strip it
        # so the GUID matches what the arxiv adapter would produce.
        clean_id = arxiv_id.split("v")[0]

        pub_at = _common.parse_iso(paper.get("publishedAt") or entry.get("publishedAt"))

        # Real arxiv authors, plus a synthetic "HF Daily Papers" author whose
        # affiliation triggers the tier-1 match in the filter.
        authors: list[Author] = []
        for a in paper.get("authors", []) or []:
            name = a.get("name") or ""
            if name:
                authors.append(Author(name=name))
        authors.append(Author(
            name="Hugging Face Daily Papers (curated)",
            affiliations=[Affiliation(name=LAB_NAME, raw=LAB_NAME)],
        ))

        yield Paper(
            id=f"arxiv:{clean_id}",
            source="arxiv",                    # IMPORTANT: keep source=arxiv so dedupe works
            title=title.strip(),
            abstract=(paper.get("summary") or "").strip(),
            authors=authors,
            categories=["cs.AI"],              # HF papers are ML-flavored by definition
            url=f"https://huggingface.co/papers/{clean_id}",
            pdf_url=f"https://arxiv.org/pdf/{clean_id}",
            published_at=pub_at,
            raw={
                "arxiv_id": clean_id,
                "hf_upvotes": paper.get("upvotes"),
                "hf_curated": True,
            },
        )
        seen += 1
