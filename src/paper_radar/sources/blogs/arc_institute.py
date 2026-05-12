"""Arc Institute news adapter (scrape arcinstitute.org/news)."""
from __future__ import annotations
import logging
from typing import Iterable

from bs4 import BeautifulSoup

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

INDEX_URL = "https://arcinstitute.org/news"
LAB_NAME = "Arc Institute"


def fetch(limit: int = 30) -> Iterable[Paper]:
    html = _common.http_get(INDEX_URL)
    if not html:
        return
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    n = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Arc article URLs look like /news/<slug> or /publications/<slug>
        if not (href.startswith("/news/") or href.startswith("/publications/")):
            continue
        if href.rstrip("/") in ("/news", "/publications"):
            continue
        url = "https://arcinstitute.org" + href
        if url in seen:
            continue
        seen.add(url)
        title = a.get_text(strip=True)
        if not title or len(title) < 10:
            continue
        yield _common.make_paper(
            source="arc_institute",
            url=url, title=title, abstract="",
            authors=["Arc Institute"],
            lab_name=LAB_NAME,
            extra_categories=["blog", "biology"],
        )
        n += 1
        if n >= limit:
            return
