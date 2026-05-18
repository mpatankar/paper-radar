"""RSS generator + landing page.

We deliberately use stdlib + a tiny XML escape — no extra dep — because the
RSS schema is small and stable, and avoiding `feedgen`'s heavy lxml-based
churn means the only failure mode here is "writing files."

Each feed item shows:
  - title (paper title)
  - link (arXiv abs URL or blog URL)
  - publication date
  - description (HTML; abstract + tier match + senior authors)
  - guid (paper id)

Feeds ACCUMULATE across runs: each run reads the existing feed file (if any),
merges new items in (dedup by guid), sorts newest-first, and caps at
feed_max_items. This way subscribers see a rolling N-item history rather
than only the deltas from the most recent run.

The landing page is one self-contained HTML file listing each feed with its
RSS URL and last-update count.
"""
from __future__ import annotations
import html
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import formatdate, parsedate_to_datetime
from pathlib import Path
from typing import Iterable

from paper_radar.config import FeedSpec
from paper_radar.types import Decision, Paper

log = logging.getLogger(__name__)


def _rfc822(dt: datetime | None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    return formatdate(dt.timestamp(), usegmt=True)


def _description_html(paper: Paper, decision: Decision) -> str:
    """Body of the RSS item. Plain HTML, embedded as CDATA."""
    parts: list[str] = []

    # Why this paper made the feed.
    why_bits = []
    if decision.tier1_matches:
        why_bits.append(f"<b>Tier-1:</b> {html.escape(', '.join(sorted(set(decision.tier1_matches))))}")
    if decision.tier2_matches:
        senior = ", ".join(decision.senior_authors) or "(senior)"
        why_bits.append(
            f"<b>Tier-2 senior:</b> {html.escape(', '.join(sorted(set(decision.tier2_matches))))}"
            f" — {html.escape(senior)}"
        )
    if why_bits:
        parts.append("<p style='color:#555;font-size:0.9em'>" + " · ".join(why_bits) + "</p>")

    # Authors line.
    authors = ", ".join(html.escape(a.name) for a in paper.authors[:8])
    if len(paper.authors) > 8:
        authors += f", … <i>(+{len(paper.authors)-8} more)</i>"
    parts.append(f"<p><b>Authors:</b> {authors}</p>")

    # Abstract.
    if paper.abstract:
        parts.append(f"<p>{html.escape(paper.abstract)}</p>")

    # Links + categories + arxiv deposit date (preserved here since pubDate
    # now reflects when paper-radar surfaced the paper, not when arXiv got it).
    cats = ", ".join(html.escape(c) for c in paper.categories) if paper.categories else "—"
    extras = [f"<b>Categories:</b> {cats}"]
    if paper.published_at:
        extras.append(f"<b>arXiv submitted:</b> {paper.published_at.date().isoformat()}")
    extras.append(f"<a href='{html.escape(paper.url)}'>page</a>")
    if paper.pdf_url:
        extras.append(f"<a href='{html.escape(paper.pdf_url)}'>pdf</a>")
    parts.append("<p style='color:#888;font-size:0.85em'>" + " · ".join(extras) + "</p>")

    return "\n".join(parts)


def write_feed(feed: FeedSpec, items: list[tuple[Paper, Decision]],
               out_dir: Path, *, max_items: int = 200,
               site_base_url: str = "https://example.github.io/paper-radar/feeds_out",
               emit_time: datetime | None = None) -> Path:
    """Write feeds_out/<id>.xml, accumulating prior items.

    Strategy:
      1. Read the existing file (if present) and parse its <item>s.
      2. Build new items from this run. Each gets <pubDate> = `emit_time`
         (when paper-radar first surfaced it), NOT arXiv's deposit date —
         otherwise old papers that arXiv re-lists today sort under their
         original deposit date and look stale in the reader.
      3. Merge: new items take precedence on guid collision. Then sort by
         pubDate desc and cap at max_items.
      4. Write.

    Returns the path. `emit_time` is parameterized so tests can be
    deterministic; production always defaults to `now`.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{feed.id}.xml"

    emit_time = emit_time or datetime.now(timezone.utc)
    new_serialized = [_serialize_item(p, d, emit_time) for p, d in items]
    new_guids = {it["guid"] for it in new_serialized}

    # Load prior items, drop any guid that's also in this run (the new render wins).
    prior_items = _load_existing_items(path) if path.exists() else []
    prior_items = [it for it in prior_items if it.get("guid") not in new_guids]

    merged = new_serialized + prior_items
    # Sort newest first (fall back to "epoch" for any item missing a parseable pubDate).
    merged.sort(key=lambda it: it.get("_pub_ts") or 0.0, reverse=True)
    merged = merged[:max_items]

    now_rfc = _rfc822(None)
    xml_parts: list[str] = []
    xml_parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml_parts.append('<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">')
    xml_parts.append("  <channel>")
    xml_parts.append(f"    <title>{html.escape(feed.title)}</title>")
    self_link = f"{site_base_url.rstrip('/')}/{feed.id}.xml"
    xml_parts.append(f'    <atom:link href="{html.escape(self_link)}" rel="self" type="application/rss+xml" />')
    xml_parts.append(f"    <link>{html.escape(site_base_url)}</link>")
    xml_parts.append(f"    <description>{html.escape(feed.description)}</description>")
    xml_parts.append(f"    <lastBuildDate>{now_rfc}</lastBuildDate>")
    xml_parts.append("    <generator>paper-radar 0.1</generator>")

    for it in merged:
        xml_parts.append("    <item>")
        xml_parts.append(f"      <title>{html.escape(it['title'])}</title>")
        xml_parts.append(f"      <link>{html.escape(it['link'])}</link>")
        xml_parts.append(f'      <guid isPermaLink="false">{html.escape(it["guid"])}</guid>')
        xml_parts.append(f"      <pubDate>{it['pubDate']}</pubDate>")
        for c in it.get("categories", []):
            xml_parts.append(f"      <category>{html.escape(c)}</category>")
        xml_parts.append(f"      <description><![CDATA[{it['description']}]]></description>")
        xml_parts.append("    </item>")

    xml_parts.append("  </channel>")
    xml_parts.append("</rss>")

    path.write_text("\n".join(xml_parts), encoding="utf-8")
    log.info("wrote %d items to %s (%d new this run, %d carried over)",
             len(merged), path, len(new_serialized),
             max(0, len(merged) - len(new_serialized)))
    return path


def _serialize_item(paper: Paper, decision: Decision, emit_time: datetime) -> dict:
    """Turn a (Paper, Decision) into the dict we render and persist in XML.

    `pubDate` is the emit time — when paper-radar surfaced this item — so
    readers sort the freshly-added items at the top regardless of when
    arXiv originally received the paper. The original arXiv deposit date,
    if present, is preserved in the description body.
    """
    return {
        "title": paper.title,
        "link": paper.url,
        "guid": paper.id,
        "pubDate": _rfc822(emit_time),
        "_pub_ts": emit_time.timestamp(),
        "categories": list(paper.categories),
        "description": _description_html(paper, decision),
    }


def _load_existing_items(path: Path) -> list[dict]:
    """Parse an existing RSS 2.0 feed and return items in our internal dict shape."""
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        log.warning("can't parse existing %s (%s); starting fresh", path, e)
        return []
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        return []
    out: list[dict] = []
    for item in channel.findall("item"):
        guid_el = item.find("guid")
        pub_el = item.find("pubDate")
        # Parse pubDate to timestamp for sorting; tolerate missing/malformed.
        ts = 0.0
        if pub_el is not None and pub_el.text:
            try:
                ts = parsedate_to_datetime(pub_el.text).timestamp()
            except (TypeError, ValueError):
                ts = 0.0
        out.append({
            "title": (item.findtext("title") or ""),
            "link": (item.findtext("link") or ""),
            "guid": (guid_el.text if guid_el is not None else "") or "",
            "pubDate": (pub_el.text if pub_el is not None else _rfc822(None)),
            "_pub_ts": ts,
            "categories": [c.text or "" for c in item.findall("category")],
            "description": (item.findtext("description") or ""),
        })
    return out


def write_landing_page(feeds: list[FeedSpec], out_dir: Path,
                       feed_item_counts: dict[str, int]) -> Path:
    """Build a simple index.html listing all available feeds."""
    out_dir = Path(out_dir)
    rows = []
    for f in feeds:
        n = feed_item_counts.get(f.id, 0)
        rows.append(
            f"<tr><td><b>{html.escape(f.title)}</b><br>"
            f"<span style='color:#666'>{html.escape(f.description)}</span></td>"
            f"<td><code>{html.escape(f.id)}.xml</code></td>"
            f"<td><a href='{html.escape(f.id)}.xml'>subscribe</a></td>"
            f"<td>{n} items</td></tr>"
        )
    body = f"""<!doctype html>
<meta charset="utf-8">
<title>paper-radar — feeds</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 760px; margin: 60px auto; padding: 0 16px; color: #222; }}
  h1 {{ font-weight: 600; margin-bottom: 4px; }}
  p.lede {{ color: #555; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 32px; }}
  td, th {{ padding: 12px 8px; vertical-align: top; border-bottom: 1px solid #eee; text-align: left; font-size: 14px; }}
  code {{ background: #f4f4f7; padding: 2px 5px; border-radius: 3px; font-size: 13px; }}
  a {{ color: #2256aa; }}
</style>

<h1>paper-radar</h1>
<p class="lede">Curated daily RSS feeds of high-signal AI/Robotics papers.
Filters arXiv + frontier-lab blogs to authors at top labs (tier 1 = any author;
tier 2 = senior author).</p>

<table>
  <thead><tr><th>Feed</th><th>File</th><th></th><th>Items</th></tr></thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>

<p style="margin-top:48px;color:#888;font-size:13px">
  Updated daily.
  <a href="stats.json">stats.json</a> ·
  <a href="https://github.com/miheer/paper-radar">source</a>
</p>
"""
    path = out_dir / "index.html"
    path.write_text(body, encoding="utf-8")
    return path
