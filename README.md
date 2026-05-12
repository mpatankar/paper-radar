# paper-radar

Curated daily RSS feeds of high-signal AI/Robotics papers. Filters arXiv +
frontier-lab blogs to authors at top-cited institutions, splits by topic, and
publishes RSS via GitHub Pages.

```
arXiv (cs.AI, cs.LG, cs.CV, cs.RO, cs.CL, stat.ML)
     +
frontier-lab blogs (Anthropic, OpenAI, DeepMind, …)
                              │
                              ▼
              affiliation resolver  (OpenAlex, cached)
                              │
                              ▼
                       tier filter
              (tier-1 any-author, tier-2 senior-author)
                              │
                              ▼
                     topic routing
            (frontier-llm, alignment-safety, vision-multimodal,
             robotics-embodied, ai-science, everything)
                              │
                              ▼
                    RSS XML on GitHub Pages
```

## How the filter actually works

Two tiers in `config/allowlist.yaml`.

- **Tier 1** — frontier labs (OpenAI, Anthropic, Google DeepMind, Meta FAIR, Microsoft Research, NVIDIA Research, xAI, Mistral, DeepSeek, Alibaba Qwen, Cohere, Thinking Machines, Physical Intelligence, Goodfire, SSI, Reka, Arc Institute, AI2, Tencent AI Lab, ByteDance Seed, Moonshot AI, Shanghai AI Lab, Toyota Research). Paper is accepted if **any** author is affiliated with one.
- **Tier 2** — elite academic labs (Stanford, MIT, Berkeley, CMU, Toronto, Oxford, Cambridge, ETH, Tsinghua, …). Paper is accepted only if a **senior author** is from one (first or last position, h-index ≥ 30 or cited-by ≥ 5,000).

The thresholds are knobs in `config/config.yaml`.

## Feeds

| ID | What |
|---|---|
| `frontier-llm` | New foundation models, scaling, training recipes, reasoning |
| `alignment-safety` | RLHF, interpretability, evals, red-teaming |
| `vision-multimodal` | VLMs, diffusion, video gen, 3D |
| `robotics-embodied` | Manipulation, VLA models, world models |
| `ai-science` | AlphaFold-style, weather, materials, biology |
| `everything` | Firehose: every accepted paper |

## Install + run locally

```bash
git clone <repo>
cd paper-radar
pip install -e .
paper-radar run          # one full pipeline
paper-radar tune         # dry-run; print volume histogram
paper-radar list-labs    # show tier 1 and tier 2 allowlist
paper-radar list-feeds   # show feed definitions
```

## Tuning the volume

The whole point of v0 is to tune the volume to "manageable." Run

```bash
paper-radar tune
```

which prints something like:

```json
{
  "n_papers_seen": 1247,
  "tuning_histogram": {
    "tier_1_any_author": 38,
    "tier_2_any_author": 412,
    "tier_2_senior_only": 71,
    "either_tier1_or_tier2_senior": 94
  },
  "top_institutions": [["Google DeepMind", 18], ["Stanford", 12], …]
}
```

You read those numbers, decide what feels right, and edit `config/config.yaml`:

- Want fewer papers? Raise `senior_h_index_threshold` (e.g. 40), or switch
  `tier_2_mode` to `disabled`.
- Want more? Drop `senior_h_index_threshold` (e.g. 20), or switch to
  `tier_2_mode: first_or_last_senior` (still seniority-gated) or
  `any_author` (no seniority gate at all).

## Introspection

```bash
# Why did this specific paper land where it did?
paper-radar explain arxiv:2501.12345

# Same, but for a paper that hasn't been through the pipeline yet (live fetch):
paper-radar explain --live arxiv:2501.12345

# Run history
paper-radar stats

# Decision log for every paper ever processed (grep-friendly)
cat data/decisions.jsonl | jq 'select(.accepted == false and .tier1_matches | length > 0)'
```

Every paper that flows through the pipeline gets a `Decision` record written
to `data/decisions.jsonl`. That's the audit trail; anything `paper-radar
explain` shows is read from this file.

## Architecture (file map)

```
src/paper_radar/
  __init__.py
  types.py              # Paper, Author, Affiliation, Decision dataclasses
  config.py             # YAML loader → typed Config object
  resolver.py           # OpenAlex affiliation + h-index resolver, SQLite-cached
  filter.py             # Tier matching, senior detection, feed routing
  feed.py               # RSS XML + landing page
  state.py              # seen.sqlite, run history
  stats.py              # tuning histograms, per-feed counts
  run.py                # orchestrator (pull → enrich → filter → write)
  cli.py                # argparse subcommands
  sources/
    arxiv.py            # OAI-PMH client
    blogs/
      _common.py        # shared HTTP / Paper builder
      anthropic.py
      openai_blog.py
      deepmind.py
      transformer_circuits.py
      # add more here, then register in blogs/__init__.py
config/
  config.yaml           # runtime knobs
  allowlist.yaml        # tier 1 + tier 2 institutions
  feeds.yaml            # feed definitions (categories, keywords)
feeds_out/              # generated RSS XML + index.html + stats.json
data/                   # SQLite caches + decisions.jsonl (gitignored)
.github/workflows/
  daily.yml             # nightly cron → gh-pages
  tests.yml             # pytest on push/PR
```

## Configuration files at a glance

- **`config/config.yaml`** — knobs you'll actually edit. Filter thresholds,
  enabled adapters, output directory, logging level.
- **`config/allowlist.yaml`** — tier 1 / tier 2 institutions. Adding a new
  lab is one block here.
- **`config/feeds.yaml`** — feed taxonomy. Add a new feed or rewire categories
  here. The `everything` feed special-cases through (no filters).

## Deploying

GitHub Pages does all the hosting. Push to GitHub, enable Pages on the
`gh-pages` branch, and the `daily.yml` workflow takes care of the rest. RSS
URLs end up at:

```
https://<you>.github.io/paper-radar/frontier-llm.xml
https://<you>.github.io/paper-radar/alignment-safety.xml
…
https://<you>.github.io/paper-radar/everything.xml
```

Plus a human-readable landing page at `index.html`.

## Adding a new lab

1. Add an entry to `config/allowlist.yaml` under the right tier:
   ```yaml
   - {name: "New Lab", match: ["new lab", "newlab inc"], country: "US"}
   ```
2. (Optional) If the lab publishes on its own site rather than arXiv, write a
   tiny adapter:
   ```python
   # src/paper_radar/sources/blogs/new_lab.py
   def fetch(): ...
   ```
   Register it in `sources/blogs/__init__.py` and `config.yaml`.

## Adding a new feed

Add a block to `config/feeds.yaml`:

```yaml
- id: my-new-feed
  title: "Paper Radar — Custom topic"
  description: "..."
  arxiv_categories: [cs.SE]
  keywords_any: ["formal verification", "type system"]
  exclude_if_keyword: ["survey"]
```

Done. The next `paper-radar run` writes `feeds_out/my-new-feed.xml`.

## Tests

```bash
pip install -e .[dev]
pytest
```

21 unit tests cover config loading, the filter (tier matching, senior detection,
feed routing, manual override), the arXiv XML parser (via fixture), the RSS
generator (validity + truncation), and the dedupe state store.

## Why these specific labs?

The tier list isn't pulled from a vibe — it's derived from a citation-graph
analysis done before this project. See [`../analysis_results.json`](../analysis_results.json)
in the parent directory: the top 30 institutions by citation-slot reach across
50 deliberately diverse seminal AI/Robotics papers, plus frontier startups
(Mistral, Physical Intelligence, Thinking Machines, etc.) that punch above
their citation weight despite low publication volume.

## License

MIT.
