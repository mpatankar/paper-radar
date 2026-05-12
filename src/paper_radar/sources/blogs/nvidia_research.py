"""NVIDIA Research adapter (scrape research.nvidia.com/publications)."""
from __future__ import annotations
import logging
import re
from typing import Iterable

from bs4 import BeautifulSoup

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

INDEX_URL = "https://research.nvidia.com/publications"
LAB_NAME = "NVIDIA Research"


def fetch(limit: int = 30) -> Iterable[Paper]:
    html = _common.http_get(INDEX_URL)
    if not html:
        log.warning("nvidia_research: index fetch failed")
        return
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    n = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not re.search(r"/publication/", href):
            continue
        url = href if href.startswith("http") else "https://research.nvidia.com" + href
        if url in seen:
            continue
        seen.add(url)
        title = a.get_text(strip=True)
        if not title or len(title) < 10:
            continue
        yield _common.make_paper(
            source="nvidia_research",
            url=url, title=title, abstract="",
            authors=["NVIDIA Research"],
            lab_name=LAB_NAME,
            extra_categories=["blog"],
        )
        n += 1
        if n >= limit:
            return
