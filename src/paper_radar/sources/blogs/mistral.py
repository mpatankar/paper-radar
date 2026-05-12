"""Mistral AI news adapter (scrape mistral.ai/news)."""
from __future__ import annotations
import logging
from typing import Iterable

from bs4 import BeautifulSoup

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

INDEX_URL = "https://mistral.ai/news/"
LAB_NAME = "Mistral AI"


def fetch(limit: int = 30) -> Iterable[Paper]:
    html = _common.http_get(INDEX_URL)
    if not html:
        return
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    n = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("/news/") or href.rstrip("/").endswith("/news"):
            continue
        url = "https://mistral.ai" + href
        if url in seen:
            continue
        seen.add(url)
        title = a.get_text(strip=True)
        if not title or len(title) < 10:
            continue
        yield _common.make_paper(
            source="mistral",
            url=url, title=title, abstract="",
            authors=["Mistral AI"],
            lab_name=LAB_NAME,
            extra_categories=["blog"],
        )
        n += 1
        if n >= limit:
            return
