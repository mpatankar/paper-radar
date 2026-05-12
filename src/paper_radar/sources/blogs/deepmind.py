"""Google DeepMind research adapter (RSS-backed)."""
from __future__ import annotations
import logging
from typing import Iterable
import xml.etree.ElementTree as ET

from paper_radar.types import Paper
from . import _common

log = logging.getLogger(__name__)

# DeepMind serves an RSS-ish feed on the research page; fall back to HTML if not.
RSS_URL = "https://deepmind.google/blog/rss.xml"
LAB_NAME = "Google DeepMind"


def fetch(limit: int = 30) -> Iterable[Paper]:
    body = _common.http_get(RSS_URL)
    if not body:
        log.warning("deepmind: RSS fetch failed")
        return
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        log.warning("deepmind: RSS parse error: %s", e)
        return

    # standard RSS 2.0 channel/item layout
    for i, item in enumerate(root.iter("item")):
        if i >= limit:
            break
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = _common.parse_iso(item.findtext("pubDate"))
        if not link or not title:
            continue
        yield _common.make_paper(
            source="deepmind",
            url=link,
            title=title,
            abstract=desc,
            authors=["Google DeepMind"],
            lab_name=LAB_NAME,
            published_at=pub,
            extra_categories=["blog"],
        )
