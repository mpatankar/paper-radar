# Podcast Setup

Outcome of the podcast review. Reference doc for constructing the setup in Pocket Casts.

## Player decision

**Pocket Casts** (switching from Apple Podcasts).

Reason: its Filters can combine **podcast selection + episode duration**, which is the
only way to isolate Tangle's "Suspension of the Rules" from the daily episodes.
Overcast can't filter by duration; Apple Podcasts can't do rule-based playlists at all.

AI-summary apps (Snipd etc.) were considered and **skipped** — for this library the
benefit is marginal: the shows you'd want to triage (Robopapers, Ologies) already have
self-documenting episode titles, and narrative shows shouldn't be summarized at all.

## The 8 filters

Every filter: **Episode Status → Unplayed + In Progress**. Other settings below.

| # | Filter | Podcasts | Duration rule | Sort |
|---|--------|----------|---------------|------|
| 1 | **Talk Shows** | Tangle, Sharp Tech | longer than 40 min | default |
| 2 | **Deep Dives** | Feeling of Computing, Robopapers, Dwarkesh | none | default |
| 3 | **Daily** | Marketplace, Dithering | none | newest first |
| 4 | **Business & Builders** | My First Million, Founders, Acquired | none | default |
| 5 | **Sales** | 30 Minutes to President's Club | longer than 20 min | default |
| 6 | **Browse: Stories** | Ologies, Radiolab, Hidden Brain, This American Life, Articles of Interest, Advent of Computing | none | default |
| 7 | **Browse: Ideas** | Odd Lots, Conversations with Tyler | none | default |
| 8 | **Series** | *(rotating — whatever finite series you're working through)* | none | **oldest first** |

Notes:
- **Talk Shows / >40 min** — Tangle dailies top out ~32 min and previews ~17 min, so
  >40 keeps only Suspension of the Rules (~67 min). Catches full Sharp Tech episodes.
  Caveat: a rare sub-40-min Sharp Tech episode could be missed.
- **Sales / >20 min** — drops 30MPC's short "lessons" and 90-sec trailers.
- **Daily** — optional: set Release date to "last 3 days".
- **Series** — the only filter sorted oldest-first. It's a rotating "currently bingeing"
  slot for finite limited series: add a series when you start it, remove it when done.
  Currently holds: Sold a Story.

Filters 1–7 are mood/topic filters (ongoing shows, newest episodes).
Filter 8 is a lifecycle filter (finite series, consumed in order, temporary).

## Subscriptions

**Search-and-add (public feeds):**
Marketplace (pick the *daily* show, not "After the Bell" / "Morning Report"),
Tangle, Robopapers, Ologies, My First Million, 30 Minutes to President's Club,
Hidden Brain, Acquired, Advent of Computing, This American Life, Founders,
Radiolab, Articles of Interest, Feeling of Computing, Dwarkesh, Odd Lots,
Conversations with Tyler.

**Members-only — add via personal feed URL from each membership account:**
- Dithering
- Sharp Tech
- Tangle — public feed carries some SotR, but use the members feed for reliability

**New podcast feed URLs:**
```
Dwarkesh:               https://apple.dwarkesh-podcast.workers.dev/feed.rss
Odd Lots:               https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1/8a94442e-5a74-4fa2-8b8d-ae27003a8d6b/982f5071-765c-403d-969d-ae27003a8d83/podcast.rss
Conversations w/ Tyler: https://rss.libsyn.com/shows/137081/destinations/850607.xml
```

## Decisions / changes from the original list

- **Added:** Dwarkesh (deep AI/ideas interviews — fills the big-picture-AI gap),
  Odd Lots (economics / "how the world works"), Conversations with Tyler (eclectic
  interviews).
- **Dropped: Latent Space** — your RSS feeds cover AI deeply enough; the podcast was
  builder-tilted and redundant.
- **Dropped: Dialectic** — couldn't be identified; not worth keeping.
- **Sold a Story** — finite limited series; goes in the Series filter while you finish
  it, then unsubscribe.

## Optional podcasts considered but not added

- **No Priors** — AI + startups/VC. Lighter than your other AI sources.
- **Risky Business** — security; only if the beat genuinely interests you (you added
  Krebs to RSS).

## Observations from reading the actual feeds

- **Acquired** has drifted from tech-company history to iconic institutions broadly
  (Ferrari, NFL, F1, Rolex, Costco). Still excellent — just not a tech podcast.
- **Founders** has drifted from "entrepreneurs" to "biographies of elite performers"
  (Federer, Agassi, Schwarzenegger alongside Phil Knight). Theme = how exceptional
  people operate.
- MFM / Founders / Acquired are *not* redundant — opportunistic ideas vs performer
  psychology vs institutional history. Keep all three.
