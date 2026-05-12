"""Anthropic research feed adapter.

Anthropic publishes research at anthropic.com/research and exposes a JSON
listing. We pull the listing, then fetch each post page for the abstract.
"""
from __future__ import annotations
import logging
from typing import Iterable

from bs4 import BeautifulSoup

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

INDEX_URL = "https://www.anthropic.com/research"
LAB_NAME = "Anthropic"


def fetch(limit: int = 30) -> Iterable[Paper]:
    html = _common.http_get(INDEX_URL)
    if not html:
        log.warning("anthropic: index fetch failed")
        return
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("/research/"):
            continue
        if href in ("/research", "/research/"):
            continue
        full = "https://www.anthropic.com" + href
        if full in seen:
            continue
        seen.add(full)
        links.append(full)
        if len(links) >= limit:
            break

    for url in links:
        post = _common.http_get(url)
        if not post:
            continue
        post_soup = BeautifulSoup(post, "lxml")
        title_el = post_soup.find("h1") or post_soup.find("meta", property="og:title")
        if title_el is None:
            continue
        title = (title_el.get_text(strip=True)
                 if hasattr(title_el, "get_text") else title_el.get("content", ""))
        desc_el = post_soup.find("meta", attrs={"name": "description"}) or post_soup.find("meta", property="og:description")
        abstract = desc_el.get("content", "") if desc_el else ""
        time_el = post_soup.find("time")
        pub_at = _common.parse_iso(time_el.get("datetime")) if time_el and time_el.has_attr("datetime") else None

        yield _common.make_paper(
            source="anthropic",
            url=url,
            title=title,
            abstract=abstract,
            authors=["Anthropic"],            # author bylines often not exposed
            lab_name=LAB_NAME,
            published_at=pub_at,
            extra_categories=["blog"],
        )
