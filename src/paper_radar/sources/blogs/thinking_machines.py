"""Thinking Machines (Mira Murati) research adapter."""
from __future__ import annotations
import logging
from typing import Iterable

from bs4 import BeautifulSoup

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

INDEX_URL = "https://thinkingmachines.ai/"
LAB_NAME = "Thinking Machines"


def fetch(limit: int = 20) -> Iterable[Paper]:
    html = _common.http_get(INDEX_URL)
    if not html:
        return
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    n = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Heuristic: look for post-like URLs (with date/slug shape)
        if not (href.startswith("/research/") or href.startswith("/blog/")):
            continue
        url = "https://thinkingmachines.ai" + href if href.startswith("/") else href
        if url in seen: continue
        seen.add(url)
        title = a.get_text(strip=True)
        if not title or len(title) < 6: continue
        yield _common.make_paper(
            source="thinking_machines",
            url=url, title=title, abstract="",
            authors=["Thinking Machines"],
            lab_name=LAB_NAME,
            extra_categories=["blog"],
        )
        n += 1
        if n >= limit:
            return
