"""Command-line entrypoint.

Subcommands:
  run                  Pull, enrich, filter, write feeds.
  run --dry-run        Same but don't write output files.
  explain <paper-id>   Show full decision trace for one paper (uses decisions log).
  tune                 Run end-to-end without writing, then print volume histograms.
  stats                Show recent runs' stats.
  list-feeds           List configured feeds.
  list-labs            List allowlisted institutions.
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Iterable

from paper_radar.config import Config, load_config
from paper_radar.filter import Filter
from paper_radar.resolver import Resolver
from paper_radar.run import run_once
from paper_radar.sources import arxiv as arxiv_source
from paper_radar.state import State


def _configure_logging(level: str):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _load(args) -> Config:
    cfg = load_config(args.config_dir)
    _configure_logging(args.log_level or cfg.logging.level)
    return cfg


# -- subcommand handlers ------------------------------------------------------

def cmd_run(args):
    cfg = _load(args)
    stats = run_once(cfg, dry_run=args.dry_run)
    print(json.dumps({
        "seen": stats["n_papers_seen"],
        "accepted": stats["n_papers_accepted"],
        "feeds": stats["per_feed_counts"],
    }, indent=2))


def cmd_explain(args):
    """Replay the decision for one paper from the JSONL log, OR re-run filter live."""
    cfg = _load(args)
    log_path = Path(cfg.logging.decisions_jsonl)
    if log_path.exists():
        with log_path.open() as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("paper_id") == args.paper_id:
                    _print_decision_record(d)
                    return
    print(f"No decision record found for {args.paper_id} in {log_path}.")
    print("Run `paper-radar run` first, or call `paper-radar explain --live <id>` to re-fetch.")
    if args.live and args.paper_id.startswith("arxiv:"):
        _live_explain(cfg, args.paper_id)


def _print_decision_record(d: dict):
    print(f"Paper:    {d.get('title')}")
    print(f"ID:       {d.get('paper_id')}")
    print(f"Run:      {d.get('run_started_at')}")
    print(f"Decision: {'ACCEPTED' if d.get('accepted') else 'REJECTED'}")
    for r in d.get("reasons", []):
        print(f"  · {r}")
    if d.get("tier1_matches"):
        print(f"  Tier 1: {', '.join(sorted(set(d['tier1_matches'])))}")
    if d.get("tier2_matches"):
        print(f"  Tier 2: {', '.join(sorted(set(d['tier2_matches'])))}")
    if d.get("senior_authors"):
        print(f"  Senior authors: {', '.join(d['senior_authors'])}")
    if d.get("feeds"):
        print(f"  Feeds:  {', '.join(d['feeds'])}")
    for fid, kws in (d.get("matched_keywords") or {}).items():
        if kws: print(f"    {fid} keywords: {', '.join(kws)}")
    for fid, why in (d.get("rejected_by_feed") or {}).items():
        print(f"    {fid} skipped: {why}")


def _live_explain(cfg: Config, paper_id: str):
    # Pull this single paper from arXiv and run the full pipeline on it.
    arxiv_id = paper_id.split(":", 1)[1]
    # Use OAI's GetRecord verb for one paper.
    import requests
    import xml.etree.ElementTree as ET
    from paper_radar.sources.arxiv import _record_to_paper, NS
    url = (f"https://export.arxiv.org/oai2?verb=GetRecord&identifier=oai:arXiv.org:{arxiv_id}"
           f"&metadataPrefix=arXiv")
    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        print(f"arXiv returned {r.status_code}")
        return
    root = ET.fromstring(r.content)
    rec = root.find("oai:GetRecord/oai:record", NS)
    if rec is None:
        print("paper not found in arXiv")
        return
    paper = _record_to_paper(rec)
    if not paper:
        print("could not parse paper")
        return

    with Resolver(Path(cfg.output.state_dir), cfg.enrich) as resolver:
        resolver.enrich(paper)
    filt = Filter(cfg)
    print()
    print("=== live explain ===")
    print(filt.explain(paper))


def cmd_tune(args):
    """Dry-run that prints the tuning histogram so the user can pick thresholds."""
    cfg = _load(args)
    stats = run_once(cfg, dry_run=True)
    print(json.dumps({
        "n_papers_seen": stats["n_papers_seen"],
        "tuning_histogram": stats["tuning_histogram"],
        "top_institutions": stats["top_institutions"][:10],
    }, indent=2))
    print("\nUnder current config:")
    print(f"  → {stats['n_papers_accepted']} papers would be accepted")
    print(f"  → distributed across {len(stats['per_feed_counts'])} feeds")
    print("\nAdjust filter.tier_2_mode / thresholds in config.yaml and re-run `paper-radar tune`.")


def cmd_stats(args):
    cfg = _load(args)
    with State(Path(cfg.output.state_dir)) as state:
        runs = list(state.recent_runs(limit=args.limit))
    if not runs:
        print("No runs recorded yet.")
        return
    print(f"{'Started':<22} {'Seen':>6} {'Accept':>7} {'Feeds':<40}")
    for r in runs:
        from datetime import datetime, timezone
        ts = datetime.fromtimestamp(r["started_at"], tz=timezone.utc).isoformat(timespec="seconds")
        feeds = r["payload"].get("per_feed_counts", {})
        feeds_str = " ".join(f"{k}={v}" for k, v in feeds.items())
        print(f"{ts:<22} {r['n_seen']:>6} {r['n_accepted']:>7} {feeds_str}")


def cmd_list_feeds(args):
    cfg = _load(args)
    for f in cfg.feeds:
        print(f"{f.id:<22} {f.title}")
        print(f"  cats:     {' '.join(f.arxiv_categories) or '—'}")
        print(f"  keywords: {', '.join(f.keywords_any[:6])}{' …' if len(f.keywords_any) > 6 else ''}")
        print()


def cmd_list_labs(args):
    cfg = _load(args)
    print(f"=== Tier 1 ({len(cfg.tier_1)}) — any author triggers inclusion ===")
    for inst in cfg.tier_1:
        print(f"  {inst.name:<28} match: {', '.join(inst.match)}")
    print(f"\n=== Tier 2 ({len(cfg.tier_2)}) — senior author triggers inclusion ===")
    for inst in cfg.tier_2:
        print(f"  {inst.name:<28} match: {', '.join(inst.match)}")


# -- argparse plumbing --------------------------------------------------------

def build_parser():
    ap = argparse.ArgumentParser(prog="paper-radar")
    ap.add_argument("--config-dir", type=Path, default=None,
                    help="config directory (defaults to $PAPER_RADAR_CONFIG_DIR or ./config)")
    ap.add_argument("--log-level", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="Run one full daily pipeline.")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("explain", help="Show why one paper was accepted/rejected.")
    p.add_argument("paper_id", help="e.g. arxiv:2501.12345")
    p.add_argument("--live", action="store_true",
                   help="If not in log, fetch the paper live and run the filter.")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("tune", help="Dry-run; print volume histograms.")
    p.set_defaults(func=cmd_tune)

    p = sub.add_parser("stats", help="Show recent-run summaries.")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("list-feeds", help="List configured feeds.")
    p.set_defaults(func=cmd_list_feeds)

    p = sub.add_parser("list-labs", help="List allowlisted institutions.")
    p.set_defaults(func=cmd_list_labs)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
