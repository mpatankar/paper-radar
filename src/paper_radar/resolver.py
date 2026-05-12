"""OpenAlex affiliation resolver.

For each Paper from arXiv, we want each author's:
  - current institutional affiliation (for tier matching)
  - h-index and total citation count (for senior-author detection)

Strategy:
  1. First, try to find the paper itself on OpenAlex (by DOI/arXiv ID). If
     found, OpenAlex gives us authorships with per-author institutions for
     this specific paper — strongest signal.
  2. For each unresolved author, look them up by name. Disambiguate by
     coauthor overlap. Take their most recent / most cited affiliation.
  3. Look up author summary stats (h_index, cited_by_count).

Everything is cached in SQLite to keep daily runs cheap. The cache key for
authors is `(name, top-3 coauthor surname tuple)` which is good enough to
disambiguate "Wei Yang" cases in practice.

Network calls degrade gracefully: if OpenAlex is down or a name doesn't
resolve, we return the Paper with un-enriched authors — the filter will then
fall back to `manual_must_include`.
"""
from __future__ import annotations
import json
import logging
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests

from paper_radar.config import EnrichConfig
from paper_radar.types import Affiliation, Author, Paper

log = logging.getLogger(__name__)

OPENALEX_BASE = "https://api.openalex.org"
USER_EMAIL = "miheer.patankar96@gmail.com"   # placed in mailto= for polite-pool

# Schema versioning so we can blow away the cache by bumping this.
CACHE_SCHEMA_VERSION = 1


class Resolver:
    """Resolves arXiv Papers to enriched Papers with author affiliations + h-index.

    Use as a context manager so we close the SQLite connection cleanly:

        with Resolver(state_dir, cfg) as resolver:
            paper = resolver.enrich(paper)
    """

    def __init__(self, state_dir: Path, cfg: EnrichConfig, *, session: requests.Session | None = None):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.cfg = cfg
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": f"paper-radar/0.1 (mailto:{USER_EMAIL})"})
        # SQLite shared across threads — check_same_thread=False + lock.
        self.db = sqlite3.connect(self.state_dir / "author_cache.sqlite", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._db_lock = threading.Lock()
        self._init_schema()
        # Live counters for stats / introspection (atomic enough for our purposes)
        self.stats = {"cache_hits": 0, "openalex_hits": 0, "unresolved": 0, "paper_lookups": 0}
        # When OpenAlex tells us the daily quota is exhausted (429 with long
        # Retry-After), we set this flag and stop hitting them for the rest of
        # the run. Tomorrow's run, with a warm cache, will finish what's left.
        self._quota_exhausted = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def close(self):
        self.db.close()

    def _init_schema(self):
        with self._db_lock, closing(self.db.cursor()) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)""")
            c.execute("INSERT OR IGNORE INTO meta (k, v) VALUES (?, ?)",
                      ("schema_version", str(CACHE_SCHEMA_VERSION)))
            c.execute("""
                CREATE TABLE IF NOT EXISTS authors (
                    key TEXT PRIMARY KEY,
                    openalex_id TEXT,
                    display_name TEXT,
                    affiliations_json TEXT,
                    h_index INTEGER,
                    cited_by_count INTEGER,
                    fetched_at INTEGER
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS papers (
                    arxiv_id TEXT PRIMARY KEY,
                    openalex_id TEXT,
                    fetched_at INTEGER,
                    authorships_json TEXT
                )
            """)
            self.db.commit()

    # --- public API ----------------------------------------------------------

    def enrich(self, paper: Paper) -> Paper:
        """Enrich one Paper in place (also returns it for convenience)."""
        if not self.cfg.resolve_affiliations:
            return paper

        # Try to find the paper on OpenAlex first — gives us per-paper affiliations.
        paper_authorships = self._lookup_paper_by_arxiv(paper)
        if paper_authorships:
            # Match arXiv authors to OpenAlex authorships by name similarity.
            for author in paper.authors:
                match = _best_authorship_match(author.name, paper_authorships)
                if match:
                    author.affiliations = match["affiliations"]
                    author.openalex_id = match.get("openalex_id")

        # For any author still lacking affiliation or h-index, do a name lookup.
        coauthor_names = [a.name for a in paper.authors]
        for author in paper.authors:
            need_aff = not author.affiliations
            need_hidx = self.cfg.resolve_h_index and author.h_index is None
            if not (need_aff or need_hidx):
                continue
            row = self._lookup_author_by_name(author.name, coauthor_names)
            if row:
                if need_aff and row.get("affiliations"):
                    author.affiliations = row["affiliations"]
                if not author.openalex_id:
                    author.openalex_id = row.get("openalex_id")
                if author.h_index is None:
                    author.h_index = row.get("h_index")
                if author.cited_by_count is None:
                    author.cited_by_count = row.get("cited_by_count")
            else:
                self.stats["unresolved"] += 1

        return paper

    # --- paper lookup --------------------------------------------------------

    def _lookup_paper_by_arxiv(self, paper: Paper) -> list[dict] | None:
        """Returns authorships list for the paper, or None if not found / not arxiv."""
        if paper.source != "arxiv":
            return None
        arxiv_id = paper.raw.get("arxiv_id") or paper.id.split(":", 1)[-1]
        if not arxiv_id:
            return None

        # Check cache.
        with self._db_lock, closing(self.db.cursor()) as c:
            r = c.execute("SELECT authorships_json FROM papers WHERE arxiv_id=?", (arxiv_id,)).fetchone()
        if r and r["authorships_json"]:
            self.stats["cache_hits"] += 1
            cached = json.loads(r["authorships_json"])
            # Re-hydrate dict affiliations into Affiliation objects.
            for a in cached:
                a["affiliations"] = [Affiliation(**af) if isinstance(af, dict) else af
                                     for af in a.get("affiliations", [])]
            return cached or None

        self.stats["paper_lookups"] += 1
        # Try OpenAlex by DOI of arxiv DOI form
        doi = f"10.48550/arxiv.{arxiv_id.lower()}"
        url = f"{OPENALEX_BASE}/works/doi:{quote(doi)}?select=id,authorships&mailto={USER_EMAIL}"
        data = self._get_json(url)
        authorships: list[dict] = []
        if data and "authorships" in data:
            authorships = _format_authorships(data["authorships"])

        # Cache result (even if empty — avoids hammering for unindexed papers).
        jsonable = [{**a, "affiliations": [_aff_to_jsonable(af) for af in a["affiliations"]]}
                    for a in authorships]
        with self._db_lock, closing(self.db.cursor()) as c:
            c.execute("""INSERT OR REPLACE INTO papers (arxiv_id, openalex_id, fetched_at, authorships_json)
                         VALUES (?, ?, ?, ?)""",
                      (arxiv_id, (data or {}).get("id"), int(time.time()), json.dumps(jsonable)))
            self.db.commit()
        return authorships or None

    # --- author lookup -------------------------------------------------------

    def _lookup_author_by_name(self, name: str, coauthors: list[str]) -> dict | None:
        key = _author_cache_key(name, coauthors)
        with self._db_lock, closing(self.db.cursor()) as c:
            r = c.execute("""SELECT openalex_id, display_name, affiliations_json, h_index, cited_by_count
                             FROM authors WHERE key=?""", (key,)).fetchone()
        if r:
            self.stats["cache_hits"] += 1
            return {
                "openalex_id": r["openalex_id"],
                "display_name": r["display_name"],
                "affiliations": [Affiliation(**a) for a in json.loads(r["affiliations_json"] or "[]")],
                "h_index": r["h_index"],
                "cited_by_count": r["cited_by_count"],
            }

        self.stats["openalex_hits"] += 1
        # Search OpenAlex.
        url = f"{OPENALEX_BASE}/authors?search={quote(name)}&per-page=5&mailto={USER_EMAIL}"
        data = self._get_json(url)
        if not data or not data.get("results"):
            self._cache_author(key, None)
            return None

        # Disambiguate via coauthor surname overlap.
        candidates = data["results"]
        best = _disambiguate_author(name, candidates, coauthors, self)
        if not best:
            self._cache_author(key, None)
            return None

        affiliations = []
        for la in best.get("last_known_institutions") or []:
            affiliations.append(Affiliation(
                name=la.get("display_name") or "",
                raw=la.get("display_name") or "",
                country=la.get("country_code") or "",
            ))
        stats = best.get("summary_stats") or {}
        result = {
            "openalex_id": best.get("id"),
            "display_name": best.get("display_name"),
            "affiliations": affiliations,
            "h_index": stats.get("h_index"),
            "cited_by_count": best.get("cited_by_count"),
        }
        self._cache_author(key, result)
        return result

    def _cache_author(self, key: str, result: dict | None):
        if result is None:
            payload = {
                "openalex_id": None, "display_name": None,
                "affiliations": [], "h_index": None, "cited_by_count": None,
            }
        else:
            payload = result
        with self._db_lock, closing(self.db.cursor()) as c:
            c.execute("""INSERT OR REPLACE INTO authors
                         (key, openalex_id, display_name, affiliations_json, h_index, cited_by_count, fetched_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      (key, payload.get("openalex_id"), payload.get("display_name"),
                       json.dumps([_aff_to_jsonable(a) for a in payload.get("affiliations", [])]),
                       payload.get("h_index"), payload.get("cited_by_count"),
                       int(time.time())))
            self.db.commit()

    # --- low-level HTTP ------------------------------------------------------

    def _get_json(self, url: str, retries: int = 4) -> dict | None:
        # Short-circuit if today's quota is gone.
        if self._quota_exhausted:
            return None
        for attempt in range(retries):
            try:
                r = self.session.get(url, timeout=30)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 404:
                    return None
                if r.status_code == 429:
                    # 429 from OpenAlex. Two sub-cases:
                    #   - burst limit: Retry-After is small (< 60s); honor it
                    #   - daily quota: Retry-After is hours; sleeping that long
                    #     is worse than returning None and continuing. We set a
                    #     run-scoped flag so subsequent author lookups in the
                    #     same run skip OpenAlex entirely.
                    retry_after = int(r.headers.get("Retry-After", "0") or 0)
                    if retry_after > 60:
                        if not self._quota_exhausted:
                            log.warning("openalex 429 Retry-After=%ds — daily quota exhausted; "
                                        "skipping remaining OpenAlex calls this run", retry_after)
                            self._quota_exhausted = True
                        return None
                    wait = max(retry_after, min(60, 5 * (2 ** attempt)))
                    log.warning("openalex 429; sleeping %ds", wait)
                    time.sleep(wait)
                    continue
                if r.status_code in (500, 502, 503, 504):
                    time.sleep(min(30, 2 ** attempt))
                    continue
                log.warning("openalex HTTP %d: %s", r.status_code, url)
                return None
            except requests.RequestException as e:
                log.warning("openalex request error: %s", e)
                time.sleep(min(30, 2 ** attempt))
        return None


# --- helpers -----------------------------------------------------------------

def _aff_to_jsonable(a) -> dict:
    if isinstance(a, Affiliation):
        return {"name": a.name, "raw": a.raw, "country": a.country}
    return a  # already a dict from prior cache load


def _format_authorships(authorships: list[dict]) -> list[dict]:
    out = []
    for a in authorships:
        author = a.get("author") or {}
        affs: list[Affiliation] = []
        for inst in (a.get("institutions") or []):
            affs.append(Affiliation(
                name=inst.get("display_name") or "",
                raw=inst.get("display_name") or "",
                country=inst.get("country_code") or "",
            ))
        # also include raw_affiliation_strings — sometimes the only signal
        for raw in (a.get("raw_affiliation_strings") or []):
            if raw and not any(af.raw == raw for af in affs):
                affs.append(Affiliation(name=raw, raw=raw))
        out.append({
            "name": author.get("display_name") or "",
            "openalex_id": author.get("id"),
            "affiliations": affs,
        })
    return out


def _best_authorship_match(arxiv_name: str, authorships: list[dict]) -> dict | None:
    norm = arxiv_name.lower().split()
    if not norm:
        return None
    # Exact full-name match wins.
    for a in authorships:
        if (a["name"] or "").lower() == arxiv_name.lower():
            return a
    # Otherwise: surname + first initial.
    surname = norm[-1]
    first_initial = norm[0][0] if norm[0] else ""
    for a in authorships:
        oa_norm = (a["name"] or "").lower().split()
        if not oa_norm: continue
        oa_surname = oa_norm[-1]
        oa_first = oa_norm[0][0] if oa_norm[0] else ""
        if oa_surname == surname and oa_first == first_initial:
            return a
    return None


def _disambiguate_author(name: str, candidates: list[dict], coauthors: list[str], resolver) -> dict | None:
    """Pick best OpenAlex author from search results.

    Heuristic: prefer the candidate with the most prolific recent work and
    name match. For now (Phase 1) we trust OpenAlex's relevance ranking +
    name string match. A future enhancement can fetch each candidate's
    coauthor list and pick max overlap.
    """
    norm = name.lower().split()
    surname = norm[-1] if norm else ""

    # Filter to candidates whose display_name shares the surname.
    plausible = []
    for c in candidates:
        cn = (c.get("display_name") or "").lower().split()
        if cn and cn[-1] == surname:
            plausible.append(c)
    if not plausible:
        plausible = candidates  # last-ditch

    # Skip enormous disambiguation clusters (>10k works) — those are name-collision groups.
    plausible = [c for c in plausible if (c.get("works_count") or 0) <= 10000]
    if not plausible:
        return None

    # Score: prefer higher cited_by_count (more established → more cite signal),
    # but penalize candidates with extremely high works_count (likely cluster).
    def score(c):
        cites = c.get("cited_by_count") or 0
        works = c.get("works_count") or 1
        return cites / max(1, works) * 10 + cites * 0.001

    return max(plausible, key=score)


def _author_cache_key(name: str, coauthors: list[str]) -> str:
    """Stable cache key combining author name + top-3 coauthor surnames.

    Coauthor overlap is our weak disambiguation signal: two researchers named
    "Wei Yang" rarely share three coauthors with each other across papers.
    """
    name_l = name.lower().strip()
    surnames = []
    for co in coauthors:
        if co.lower().strip() == name_l:
            continue
        parts = co.lower().split()
        if parts:
            surnames.append(parts[-1])
    surnames = sorted(set(surnames))[:3]
    return f"{name_l}|{'|'.join(surnames)}"
