"""Meta AI research adapter (scrape ai.meta.com/research)."""
from __future__ import annotations
import logging
import re
from typing import Iterable

from bs4 import BeautifulSoup

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

INDEX_URL = "https://ai.meta.com/research/"
LAB_NAME = "Meta FAIR"


def fetch(limit: int = 30) -> Iterable[Paper]:
    html = _common.http_get(INDEX_URL)
    if not html:
        log.warning("meta_ai: index fetch failed")
        return
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    n = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Meta AI publication URLs typically look like /research/publications/... or /blog/...
        if not re.search(r"/research/publications/|/blog/|/research/", href):
            continue
        if href.rstrip("/").endswith("/research") or "/category/" in href:
            continue
        url = href if href.startswith("http") else "https://ai.meta.com" + href
        if url in seen:
            continue
        seen.add(url)
        title = a.get_text(strip=True)
        if not title or len(title) < 10:
            continue
        yield _common.make_paper(
            source="meta_ai",
            url=url, title=title, abstract="",
            authors=["Meta AI Research"],
            lab_name=LAB_NAME,
            extra_categories=["blog"],
        )
        n += 1
        if n >= limit:
            return
