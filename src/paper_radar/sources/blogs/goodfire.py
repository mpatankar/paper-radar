"""Goodfire research adapter."""
from __future__ import annotations
import logging
from typing import Iterable

from bs4 import BeautifulSoup

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

INDEX_URL = "https://www.goodfire.ai/research"
LAB_NAME = "Goodfire"


def fetch(limit: int = 20) -> Iterable[Paper]:
    html = _common.http_get(INDEX_URL)
    if not html:
        return
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    n = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not (href.startswith("/research/") or href.startswith("/blog/")):
            continue
        if href.rstrip("/") in ("/research", "/blog"):
            continue
        url = "https://www.goodfire.ai" + href if href.startswith("/") else href
        if url in seen: continue
        seen.add(url)
        title = a.get_text(strip=True) or _common.title_from_slug(url)
        if not title or len(title) < 6:
            continue
        yield _common.make_paper(
            source="goodfire",
            url=url, title=title, abstract="",
            authors=["Goodfire"],
            lab_name=LAB_NAME,
            extra_categories=["blog", "interpretability"],
        )
        n += 1
        if n >= limit:
            return
