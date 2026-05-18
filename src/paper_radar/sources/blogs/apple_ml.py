"""Apple ML Research (RSS-backed)."""
from __future__ import annotations
import logging
import xml.etree.ElementTree as ET
from typing import Iterable

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

FEED_URL = "https://machinelearning.apple.com/rss.xml"
LAB_NAME = "Apple ML Research"


def fetch(limit: int = 25) -> Iterable[Paper]:
    body = _common.http_get(FEED_URL)
    if not body:
        return
    # Apple's RSS sometimes has bare `&` in titles (e.g., "Workshop on PPML & AI 2026"),
    # which is invalid XML. Repair by escaping bare `&` not already part of an entity.
    import re
    body = re.sub(r"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", body)
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        log.warning("apple_ml: parse error %s", e)
        return
    for i, item in enumerate(root.iter("item")):
        if i >= limit:
            break
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = _common.parse_iso(item.findtext("pubDate"))
        if not (title and link):
            continue
        yield _common.make_paper(
            source="apple_ml",
            url=link, title=title, abstract=desc,
            authors=["Apple ML Research"],
            lab_name=LAB_NAME,
            published_at=pub,
            extra_categories=["blog"],
        )
