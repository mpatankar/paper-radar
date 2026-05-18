"""Boston Dynamics blog (engineering / product updates with research substance)."""
from __future__ import annotations
import logging
from typing import Iterable

from bs4 import BeautifulSoup

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

INDEX_URL = "https://bostondynamics.com/blog/"
LAB_NAME = "Boston Dynamics"


def fetch(limit: int = 20) -> Iterable[Paper]:
    html = _common.http_get(INDEX_URL)
    if not html:
        return
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    n = 0
    NAV_BLOCKLIST = {"read blog", "blog", "see all", "read more", "view all"}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/blog/" not in href:
            continue
        # Skip the index/category pages
        if href.rstrip("/").endswith("/blog"):
            continue
        url = href if href.startswith("http") else "https://bostondynamics.com" + href
        if url in seen:
            continue
        seen.add(url)
        title = a.get_text(strip=True)
        if not title or title.lower() in NAV_BLOCKLIST:
            title = _common.title_from_slug(url)
        if not title or len(title) < 8:
            continue
        yield _common.make_paper(
            source="boston_dynamics",
            url=url, title=title, abstract="",
            authors=["Boston Dynamics"],
            lab_name=LAB_NAME,
            extra_categories=["blog", "robotics"],
        )
        n += 1
        if n >= limit:
            return
