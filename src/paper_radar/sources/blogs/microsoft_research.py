"""Microsoft Research blog adapter (RSS-backed)."""
from __future__ import annotations
import logging
from typing import Iterable
import xml.etree.ElementTree as ET

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

FEED_URL = "https://www.microsoft.com/en-us/research/feed/"
LAB_NAME = "Microsoft Research"


def fetch(limit: int = 30) -> Iterable[Paper]:
    body = _common.http_get(FEED_URL)
    if not body:
        log.warning("microsoft_research: feed fetch failed")
        return
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        log.warning("microsoft_research: parse error %s", e)
        return

    # RSS 2.0 with dc:creator for authors
    ns = {"dc": "http://purl.org/dc/elements/1.1/"}
    for i, item in enumerate(root.iter("item")):
        if i >= limit:
            break
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = _common.parse_iso(item.findtext("pubDate"))
        creator = item.findtext("dc:creator", default="", namespaces=ns) or ""
        authors = [a.strip() for a in creator.split(",") if a.strip()] or ["Microsoft Research"]
        if not (link and title):
            continue
        yield _common.make_paper(
            source="microsoft_research",
            url=link, title=title, abstract=desc,
            authors=authors,
            lab_name=LAB_NAME,
            published_at=pub,
            extra_categories=["blog"],
        )
