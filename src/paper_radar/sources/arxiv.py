"""arXiv source via OAI-PMH.

We use arXiv's OAI-PMH endpoint (https://export.arxiv.org/oai2) which is the
documented bulk-metadata interface. We do *not* use the deprecated arxiv API
or scrape the listing pages.

The endpoint returns XML with one record per paper containing:
  - arXiv id
  - title
  - abstract
  - authors (names only — no affiliations)
  - categories
  - submission date

Affiliations and h-indexes are added later by the resolver module.
"""
from __future__ import annotations
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Iterator
from urllib.parse import urlencode

import requests

from paper_radar.config import ArxivConfig
from paper_radar.types import Author, Paper

log = logging.getLogger(__name__)

ENDPOINT = "https://oaipmh.arxiv.org/oai"

# OAI-PMH XML namespaces — verbose but stable.
NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "arxiv": "http://arxiv.org/OAI/arXiv/",
}


class ArxivError(RuntimeError):
    pass


def fetch_recent(cfg: ArxivConfig, today: datetime | None = None) -> Iterator[Paper]:
    """Yield Paper records from arXiv for the configured day window.

    The OAI-PMH `from` / `until` filters use the *deposit* date. We fetch all
    sets in `cfg.sets` and dedupe across them (some papers cross-list to
    multiple categories and would show up twice).
    """
    if not cfg.enabled:
        log.info("arxiv source disabled in config; skipping")
        return
    today = today or datetime.now(timezone.utc)
    until_date = today.date()
    from_date = (today - timedelta(days=cfg.days_back)).date()
    log.info("fetching arXiv records from %s to %s across %d sets",
             from_date, until_date, len(cfg.sets))

    seen_ids: set[str] = set()
    total = 0
    for set_spec in cfg.sets:
        for paper in _fetch_set(set_spec, from_date, until_date):
            if paper.id in seen_ids:
                continue
            seen_ids.add(paper.id)
            yield paper
            total += 1
            if total >= cfg.max_records:
                log.warning("hit max_records cap (%d); truncating", cfg.max_records)
                return


def _fetch_set(set_spec: str, from_date, until_date) -> Iterator[Paper]:
    """Page through OAI-PMH for one set, yielding Papers."""
    resumption_token: str | None = None
    page = 0
    while True:
        page += 1
        if resumption_token:
            url = f"{ENDPOINT}?{urlencode({'verb': 'ListRecords', 'resumptionToken': resumption_token})}"
        else:
            url = f"{ENDPOINT}?{urlencode({'verb': 'ListRecords', 'set': set_spec, 'metadataPrefix': 'arXiv', 'from': from_date.isoformat(), 'until': until_date.isoformat()})}"
        log.debug("arxiv %s page %d", set_spec, page)
        xml = _http_get_with_retries(url)
        if xml is None:
            log.warning("arxiv fetch failed for set=%s page=%d", set_spec, page)
            return
        root = ET.fromstring(xml)

        # Surface OAI errors clearly.
        err = root.find("oai:error", NS)
        if err is not None:
            log.error("arxiv OAI error: %s — %s", err.get("code"), err.text)
            return

        list_records = root.find("oai:ListRecords", NS)
        if list_records is None:
            return
        for rec in list_records.findall("oai:record", NS):
            paper = _record_to_paper(rec)
            if paper:
                yield paper

        tok_el = list_records.find("oai:resumptionToken", NS)
        if tok_el is None or not (tok_el.text or "").strip():
            return
        resumption_token = tok_el.text.strip()
        # arXiv asks us to wait between requests on resumption.
        time.sleep(3.0)


def _record_to_paper(rec: ET.Element) -> Paper | None:
    """Convert one OAI-PMH <record> into a Paper. Returns None for deleted records."""
    header = rec.find("oai:header", NS)
    if header is not None and header.get("status") == "deleted":
        return None

    meta = rec.find("oai:metadata/arxiv:arXiv", NS)
    if meta is None:
        return None

    arxiv_id = (meta.findtext("arxiv:id", default="", namespaces=NS) or "").strip()
    if not arxiv_id:
        return None
    title = " ".join((meta.findtext("arxiv:title", default="", namespaces=NS) or "").split())
    abstract = " ".join((meta.findtext("arxiv:abstract", default="", namespaces=NS) or "").split())
    created = meta.findtext("arxiv:created", default="", namespaces=NS) or ""
    cats_raw = (meta.findtext("arxiv:categories", default="", namespaces=NS) or "").strip()
    categories = cats_raw.split()

    authors_el = meta.find("arxiv:authors", NS)
    authors: list[Author] = []
    if authors_el is not None:
        for a in authors_el.findall("arxiv:author", NS):
            forenames = (a.findtext("arxiv:forenames", default="", namespaces=NS) or "").strip()
            keyname = (a.findtext("arxiv:keyname", default="", namespaces=NS) or "").strip()
            suffix = (a.findtext("arxiv:suffix", default="", namespaces=NS) or "").strip()
            name = " ".join(p for p in [forenames, keyname, suffix] if p)
            if not name:
                continue
            authors.append(Author(name=name))

    pub_at: datetime | None = None
    if created:
        try:
            pub_at = datetime.fromisoformat(created).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return Paper(
        id=f"arxiv:{arxiv_id}",
        source="arxiv",
        title=title,
        abstract=abstract,
        authors=authors,
        categories=categories,
        url=f"https://arxiv.org/abs/{arxiv_id}",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        published_at=pub_at,
        raw={"arxiv_id": arxiv_id},
    )


def _http_get_with_retries(url: str, retries: int = 5) -> bytes | None:
    """Resilient GET with exponential backoff. Returns None after final failure."""
    for attempt in range(retries):
        try:
            r = requests.get(
                url,
                headers={"User-Agent": "paper-radar/0.1 (https://github.com/yourname/paper-radar)"},
                timeout=60,
            )
            if r.status_code == 200:
                return r.content
            if r.status_code in (429, 503):
                wait = min(60, 5 * (2 ** attempt))
                log.warning("arxiv %d; backing off %ds", r.status_code, wait)
                time.sleep(wait)
                continue
            log.error("arxiv HTTP %d: %s", r.status_code, r.text[:200])
            return None
        except requests.RequestException as e:
            wait = min(60, 5 * (2 ** attempt))
            log.warning("arxiv request error: %s; retry in %ds", e, wait)
            time.sleep(wait)
    return None
