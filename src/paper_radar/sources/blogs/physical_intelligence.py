"""Physical Intelligence research adapter (scrape pi-blog HTML)."""
from __future__ import annotations
import logging
from typing import Iterable

from bs4 import BeautifulSoup

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

INDEX_URL = "https://www.physicalintelligence.company/blog"
LAB_NAME = "Physical Intelligence"


def fetch(limit: int = 20) -> Iterable[Paper]:
    html = _common.http_get(INDEX_URL)
    if not html:
        return
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    n = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/blog/" not in href or href.rstrip("/").endswith("/blog"):
            continue
        url = href if href.startswith("http") else "https://www.physicalintelligence.company" + href
        if url in seen:
            continue
        seen.add(url)
        title = a.get_text(strip=True)
        if not title or len(title) < 6:
            continue
        yield _common.make_paper(
            source="physical_intelligence",
            url=url, title=title, abstract="",
            authors=["Physical Intelligence"],
            lab_name=LAB_NAME,
            extra_categories=["blog", "robotics"],
        )
        n += 1
        if n >= limit:
            return
