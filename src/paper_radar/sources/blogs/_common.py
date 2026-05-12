"""Shared helpers for blog adapters."""
from __future__ import annotations
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

import requests
from bs4 import BeautifulSoup

from paper_radar.types import Affiliation, Author, Paper

log = logging.getLogger(__name__)

# Many lab sites are behind Cloudflare / WAFs that block non-browser UAs.
# We send a polite browser-like UA for blogs (and include `mailto:` in a
# header for honesty). arXiv has its own UA in sources/arxiv.py.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
      "paper-radar/0.1")

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Operator-Contact": "mailto:miheer.patankar96@gmail.com",
}


def http_get(url: str, retries: int = 3, timeout: int = 30) -> str | None:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.text
            if r.status_code in (429, 503):
                time.sleep(min(30, 5 * (attempt + 1)))
                continue
            log.warning("blog GET %s -> %d", url, r.status_code)
            return None
        except requests.RequestException as e:
            log.warning("blog GET %s error: %s", url, e)
            time.sleep(min(30, 5 * (attempt + 1)))
    return None


def slug_for(url: str) -> str:
    """Stable, short slug derived from a URL — used as paper id."""
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return digest


def make_paper(*, source: str, url: str, title: str, abstract: str,
               authors: list[str], lab_name: str,
               published_at: Optional[datetime] = None,
               extra_categories: list[str] | None = None) -> Paper:
    """Build a Paper for a blog post.

    `lab_name` is set as the canonical Affiliation for every author — since
    blog posts come from a known lab, we don't need OpenAlex for them.
    """
    aff = Affiliation(name=lab_name, raw=lab_name)
    authored = [Author(name=n, affiliations=[aff]) for n in authors]
    return Paper(
        id=f"{source}:{slug_for(url)}",
        source=source,
        title=title.strip(),
        abstract=abstract.strip(),
        authors=authored,
        categories=(extra_categories or []),
        url=url,
        published_at=published_at,
        raw={"lab": lab_name},
    )


def title_from_slug(url: str) -> str:
    """Fallback when a card link has no readable text: derive title from the URL slug.

    /research/manifold-steering  -> "Manifold Steering"
    /2024/scaling-monosemanticity/index.html -> "Scaling Monosemanticity"
    """
    import re
    # Take last meaningful path component (skip "index.html", trailing slashes)
    parts = [p for p in url.rstrip("/").split("/") if p and p != "index.html"]
    if not parts:
        return ""
    slug = parts[-1]
    slug = re.sub(r"\.(html?|php)$", "", slug)
    words = re.split(r"[-_]+", slug)
    return " ".join(w[:1].upper() + w[1:] for w in words if w)


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # try RSS pubDate format: "Wed, 03 Jan 2024 18:00:00 GMT"
        from email.utils import parsedate_to_datetime
        try:
            return parsedate_to_datetime(s)
        except Exception:
            return None
