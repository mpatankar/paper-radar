"""Stats builder.

Daily run writes feeds_out/stats.json, which is a structured summary of:
  - how many papers were seen
  - how many passed tier-1 / tier-2 / either
  - per-feed counts
  - resolver cache hit rate
  - histogram for tuning: counts under alternate thresholds

`paper-radar stats` prints a human-readable summary of the most recent
runs. The user reads this and adjusts config.yaml.
"""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paper_radar.types import Decision, Paper


def build_stats(
    *,
    seen: list[Paper],
    decisions: list[Decision],
    resolver_stats: dict | None = None,
    config_snapshot: dict | None = None,
) -> dict[str, Any]:
    accepted = [d for d in decisions if d.accepted]

    per_feed = Counter()
    for d in accepted:
        for fid in d.feeds:
            per_feed[fid] += 1

    tier1_count = sum(1 for d in decisions if d.tier1_matches)
    tier2_any_count = sum(1 for d in decisions if d.tier2_matches)
    tier2_senior_count = sum(1 for d in decisions if d.senior_authors)

    institution_freq = Counter()
    for d in accepted:
        for inst in d.tier1_matches:
            institution_freq[inst] += 1
        for inst in d.tier2_matches:
            institution_freq[inst] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_papers_seen": len(seen),
        "n_papers_accepted": len(accepted),
        "n_papers_rejected": len(seen) - len(accepted),
        "tuning_histogram": {
            "tier_1_any_author": tier1_count,
            "tier_2_any_author": tier2_any_count,
            "tier_2_senior_only": tier2_senior_count,
            "either_tier1_or_tier2_senior": len(accepted),
        },
        "per_feed_counts": dict(per_feed),
        "top_institutions": institution_freq.most_common(20),
        "resolver_stats": resolver_stats or {},
        "config_snapshot": config_snapshot or {},
    }


def write_stats(stats: dict, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "stats.json"
    path.write_text(json.dumps(stats, indent=2))
    return path
