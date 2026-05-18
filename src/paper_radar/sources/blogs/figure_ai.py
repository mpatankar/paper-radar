"""Figure AI humanoid robotics blog."""
from __future__ import annotations
import logging
from typing import Iterable

from bs4 import BeautifulSoup

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

INDEX_URL = "https://www.figure.ai/news"
LAB_NAME = "Figure AI"


def fetch(limit: int = 20) -> Iterable[Paper]:
    html = _common.http_get(INDEX_URL)
    if not html:
        return
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    n = 0
    import re
    DATE_PREFIX = re.compile(
        r"^(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
        re.IGNORECASE,
    )
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("/news/") or href.rstrip("/") == "/news":
            continue
        url = "https://www.figure.ai" + href
        if url in seen:
            continue
        seen.add(url)
        title = a.get_text(strip=True) or _common.title_from_slug(url)
        # Figure prefixes card titles with a date string like "January 27, 2026"
        # glued to the headline. Strip it.
        title = DATE_PREFIX.sub("", title).strip()
        if not title or len(title) < 5:
            continue
        yield _common.make_paper(
            source="figure_ai",
            url=url, title=title, abstract="",
            authors=["Figure AI"],
            lab_name=LAB_NAME,
            extra_categories=["blog", "robotics"],
        )
        n += 1
        if n >= limit:
            return
