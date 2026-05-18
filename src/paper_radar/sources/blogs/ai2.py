"""Allen Institute for AI (AI2) blog adapter."""
from __future__ import annotations
import logging
from typing import Iterable

from bs4 import BeautifulSoup

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

INDEX_URL = "https://allenai.org/blog"
LAB_NAME = "Allen Institute for AI"


def fetch(limit: int = 25) -> Iterable[Paper]:
    html = _common.http_get(INDEX_URL)
    if not html:
        return
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    n = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("/blog/") or href.rstrip("/") == "/blog":
            continue
        url = "https://allenai.org" + href
        if url in seen:
            continue
        seen.add(url)
        title = a.get_text(strip=True) or _common.title_from_slug(url)
        if not title or len(title) < 5:
            continue
        yield _common.make_paper(
            source="ai2",
            url=url, title=title, abstract="",
            authors=["Allen Institute for AI"],
            lab_name=LAB_NAME,
            extra_categories=["blog"],
        )
        n += 1
        if n >= limit:
            return
