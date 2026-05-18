"""Hugging Face Daily Papers — community-curated frontier-paper aggregator.

Returns Papers keyed by the underlying arXiv ID so they dedupe correctly
with our arxiv pull. The HF "endorsement" itself is encoded by adding a
synthetic author affiliated with "Hugging Face Daily Papers" — that triggers
a tier-1 match in the filter, so even papers from authors who don't
otherwise qualify get included if HF curates them.

Uses the documented-but-unofficial JSON API at /api/daily_papers.
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


def fetch(limit: int = 60) -> Iterable[Paper]:
    try:
        r = requests.get(API_URL, headers=_common.HEADERS, timeout=30)
        if r.status_code != 200:
            log.warning("huggingface_papers: HTTP %d", r.status_code)
            return
        data = r.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        log.warning("huggingface_papers: %s", e)
        return

    seen = 0
    for entry in data:
        if seen >= limit:
            return
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
