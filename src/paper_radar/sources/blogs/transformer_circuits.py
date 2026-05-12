"""Transformer Circuits Thread (Anthropic interpretability publication).

TC doesn't expose a working RSS feed, so we scrape the HTML index page. Each
entry on https://transformer-circuits.pub/ links to a research article.
"""
from __future__ import annotations
import logging
from typing import Iterable

from bs4 import BeautifulSoup

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

INDEX_URL = "https://transformer-circuits.pub/"
LAB_NAME = "Anthropic"


def fetch(limit: int = 30) -> Iterable[Paper]:
    html = _common.http_get(INDEX_URL)
    if not html:
        log.warning("transformer_circuits: index fetch failed")
        return
    soup = BeautifulSoup(html, "lxml")

    seen = set()
    count = 0
    import re
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # TC article URLs look like:
        #   2026/nla/index.html   (relative)
        #   /2024/scaling/index.html
        #   https://transformer-circuits.pub/2024/scaling/
        # All begin with a 4-digit year.
        if not re.match(r"^(/?20\d{2}/|https?://transformer-circuits\.pub/20\d{2}/)", href):
            continue
        # Normalize
        if href.startswith("http"):
            url = href
        elif href.startswith("/"):
            url = "https://transformer-circuits.pub" + href
        else:
            url = "https://transformer-circuits.pub/" + href
        if url in seen:
            continue
        seen.add(url)

        title = a.get_text(strip=True) or _common.title_from_slug(url)
        if not title or len(title) < 8:   # skip nav fragments / bare dates
            continue

        yield _common.make_paper(
            source="transformer_circuits",
            url=url,
            title=title,
            abstract="",            # TC entries are long; abstract requires PDF page parse
            authors=["Anthropic Interpretability"],
            lab_name=LAB_NAME,
            extra_categories=["blog", "interpretability"],
        )
        count += 1
        if count >= limit:
            return
