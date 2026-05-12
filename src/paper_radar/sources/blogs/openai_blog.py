"""OpenAI research feed adapter."""
from __future__ import annotations
import logging
from typing import Iterable

from bs4 import BeautifulSoup

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

INDEX_URL = "https://openai.com/research/index"
LAB_NAME = "OpenAI"


def fetch(limit: int = 30) -> Iterable[Paper]:
    html = _common.http_get(INDEX_URL)
    if not html:
        log.warning("openai: index fetch failed")
        return
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not (href.startswith("/research/") or href.startswith("/index/")):
            continue
        if href.rstrip("/") in ("/research", "/index"):
            continue
        full = href if href.startswith("http") else "https://openai.com" + href
        if full in seen: continue
        seen.add(full)
        links.append(full)
        if len(links) >= limit:
            break

    for url in links:
        post = _common.http_get(url)
        if not post:
            continue
        ps = BeautifulSoup(post, "lxml")
        title = ""
        if ps.find("meta", property="og:title"):
            title = ps.find("meta", property="og:title").get("content", "")
        elif ps.find("h1"):
            title = ps.find("h1").get_text(strip=True)
        if not title:
            continue
        desc = ps.find("meta", attrs={"name": "description"}) or ps.find("meta", property="og:description")
        abstract = desc.get("content", "") if desc else ""

        yield _common.make_paper(
            source="openai",
            url=url,
            title=title,
            abstract=abstract,
            authors=["OpenAI"],
            lab_name=LAB_NAME,
            extra_categories=["blog"],
        )
