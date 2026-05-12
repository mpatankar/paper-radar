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

The landing page is one self-contained HTML file listing each feed with its
RSS URL and last-update count.
"""
from __future__ import annotations
import html
import logging
from datetime import datetime, timezone
from email.utils import formatdate
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

    # Links + categories.
    cats = ", ".join(html.escape(c) for c in paper.categories) if paper.categories else "—"
    parts.append(f"<p style='color:#888;font-size:0.85em'>"
                 f"<b>Categories:</b> {cats}"
                 f" · <a href='{html.escape(paper.url)}'>page</a>"
                 + (f" · <a href='{html.escape(paper.pdf_url)}'>pdf</a>" if paper.pdf_url else "")
                 + "</p>")

    return "\n".join(parts)


def write_feed(feed: FeedSpec, items: list[tuple[Paper, Decision]],
               out_dir: Path, *, max_items: int = 200,
               site_base_url: str = "https://example.github.io/paper-radar/feeds_out") -> Path:
    """Write feeds_out/<id>.xml. Returns the path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Newest first.
    items = sorted(
        items,
        key=lambda pd: pd[0].published_at or datetime.now(timezone.utc),
        reverse=True,
    )[:max_items]

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

    for paper, decision in items:
        body = _description_html(paper, decision)
        pub = _rfc822(paper.published_at)
        xml_parts.append("    <item>")
        xml_parts.append(f"      <title>{html.escape(paper.title)}</title>")
        xml_parts.append(f"      <link>{html.escape(paper.url)}</link>")
        xml_parts.append(f'      <guid isPermaLink="false">{html.escape(paper.id)}</guid>')
        xml_parts.append(f"      <pubDate>{pub}</pubDate>")
        for c in paper.categories:
            xml_parts.append(f"      <category>{html.escape(c)}</category>")
        xml_parts.append(f"      <description><![CDATA[{body}]]></description>")
        xml_parts.append("    </item>")

    xml_parts.append("  </channel>")
    xml_parts.append("</rss>")

    path = out_dir / f"{feed.id}.xml"
    path.write_text("\n".join(xml_parts), encoding="utf-8")
    log.info("wrote %d items to %s", len(items), path)
    return path


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
