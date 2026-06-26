"""Four-layer lightweight paper validation & enrichment.

L1: arXiv hidden fields — journal-ref / DOI / comments / category (parsed by academic_search.py)
L2: Rebiber — arXiv-to-venue mapping DB (local, 95% accuracy)
L3: Crossref DOI reverse lookup — resolve DOI → venue
L4: arXiv category whitelist — smart pre-rank for pure preprints

Each layer is non-blocking — failures skip silently.
"""

import os
import time
import requests
from typing import Optional

# ================================================================
# ── L2: Rebiber (fixed path loading) ──
# ================================================================
_rebiber_db = None  # lazy-loaded cache


def _load_rebiber_db() -> dict:
    global _rebiber_db
    if _rebiber_db is not None:
        return _rebiber_db
    try:
        import rebiber
        pkg = os.path.dirname(rebiber.__file__)
        bib_list_file = os.path.join(pkg, "bib_list.txt")
        if not os.path.exists(bib_list_file):
            _rebiber_db = {}
            return _rebiber_db

        db = {}
        with open(bib_list_file) as f:
            for line in f:
                fn = line.strip()
                if not fn:
                    continue
                full = os.path.join(pkg, fn)
                if not os.path.exists(full):
                    continue
                try:
                    entries = rebiber.load_bib_file(full)
                    for e in entries:
                        aid = e.get("arxiv", "")
                        if aid:
                            db[aid] = e
                except Exception:
                    continue
        _rebiber_db = db
    except Exception:
        _rebiber_db = {}
    return _rebiber_db


def _rebiber_lookup(arxiv_id: str) -> Optional[dict]:
    """Query local Rebiber database."""
    if not arxiv_id:
        return None
    try:
        db = _load_rebiber_db()
        item = db.get(arxiv_id)
        if item is None:
            return None
        return {
            "venue": item.get("venue", "") or item.get("booktitle", "") or "",
            "year": str(item.get("year", "")),
            "doi": item.get("doi", "") or "",
            "source": "rebiber",
        }
    except Exception:
        return None


# ================================================================
# ── L3: Crossref DOI reverse lookup ──
# ================================================================
def _crossref_lookup(doi: str) -> Optional[dict]:
    """Reverse-resolve DOI via Crossref public API."""
    if not doi:
        return None
    url = f"https://api.crossref.org/works/{doi}"
    for attempt in range(2):
        try:
            resp = requests.get(url, timeout=8)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            msg = data.get("message", {})
            venue = ""
            ct = msg.get("container-title", [])
            if ct:
                venue = ct[0]
            event = msg.get("event", {})
            event_name = event.get("name", "") if event else ""
            return {
                "venue": event_name or venue,
                "year": str(msg.get("created", {}).get("date-parts", [[0]])[0][0]),
                "doi": doi,
                "publisher": msg.get("publisher", ""),
                "source": "crossref",
            }
        except Exception:
            if attempt < 1:
                time.sleep(1)
                continue
            return None
    return None


# ================================================================
# ── L4: arXiv category whitelist ──
# ================================================================
CATEGORY_WEIGHTS = {
    "cs.AI": 0.5, "cs.LG": 0.5, "cs.CV": 0.5, "cs.CL": 0.5,
    "cs.NE": 0.4, "cs.IR": 0.3, "cs.RO": 0.3, "cs.DC": 0.3,
    "cs.OS": 0.3, "cs.CR": 0.3, "cs.DS": 0.3, "cs.SE": 0.2,
    "cs.PL": 0.2, "cs.HC": 0.3, "cs.GR": 0.2, "cs.MM": 0.3,
    "cs.IT": 0.2, "stat.ML": 0.4, "physics.comp-ph": 0.2,
    "physics.data-an": 0.3, "q-bio.QM": 0.2, "q-bio.NC": 0.2,
    "math.OC": 0.2, "eess.IV": 0.2, "eess.SP": 0.2,
}

# Comments acceptance keywords
ACCEPTED_KWS = [
    "accepted", "published", "oral", "poster", "spotlight",
    "to appear", "forthcoming", "in press", "accepted at",
]


# ================================================================
# Unified enrichment pipeline
# ================================================================
def enrich_paper(paper: dict) -> dict:
    """Run L1-L4 validation on a single paper dict (mutates + returns).

    New keys added:
      real_venue     — best known published venue
      real_year      — publication year
      doi            — DOI
      venue_source   — which layer found the venue
      category_score — L4 heuristic score (0-1)
    """
    journal_ref = paper.get("journal_ref", "")
    doi = paper.get("doi", "")
    arxiv_id = paper.get("arxiv_id", "")
    title = paper.get("title", "")
    category = paper.get("category", "")
    comments = paper.get("comments", "")

    paper.setdefault("real_venue", "")
    paper.setdefault("real_year", paper.get("year", ""))
    paper.setdefault("venue_source", "")
    paper.setdefault("category_score", 0.0)

    # ── L1a: journal_ref from arXiv ──
    if journal_ref:
        paper["real_venue"] = journal_ref
        paper["venue_source"] = "arxiv-journal-ref"
        paper["category_score"] = 0.8
        return paper

    # ── L1b: comments acceptance hint ──
    if comments:
        lower = comments.lower()
        if any(kw in lower for kw in ACCEPTED_KWS):
            paper["venue_source"] = "arxiv-comments-accepted"
            paper["category_score"] = 0.7
            for v in ["neurips", "icml", "iclr", "cvpr", "iccv",
                      "eccv", "acl", "emnlp", "aaai", "ijcai",
                      "nature", "science", "osdi", "sosp", "chi"]:
                if v in lower:
                    paper["real_venue"] = v.upper()
                    break

    # ── L2: Rebiber (non-blocking, ~1s first load) ──
    rb = _rebiber_lookup(arxiv_id)
    if rb and rb.get("venue"):
        paper["real_venue"] = paper["real_venue"] or rb["venue"]
        paper["real_year"] = rb.get("year", paper.get("real_year", ""))
        paper["doi"] = paper.get("doi") or rb.get("doi", "")
        paper["venue_source"] = paper["venue_source"] or "rebiber"
        paper["category_score"] = max(paper.get("category_score", 0), 0.75)
        return paper

    # ── L3: Crossref DOI (non-blocking, ~2-5s) ──
    if doi:
        cr = _crossref_lookup(doi)
        if cr and cr.get("venue"):
            paper["real_venue"] = paper["real_venue"] or cr["venue"]
            paper["real_year"] = cr.get("year", paper.get("real_year", ""))
            paper["venue_source"] = paper["venue_source"] or "crossref"
            paper["category_score"] = max(paper.get("category_score", 0), 0.7)
            return paper

    # ── L4: Category whitelist ──
    if category:
        score = CATEGORY_WEIGHTS.get(category, 0.0)
        paper["category_score"] = max(paper.get("category_score", 0), score)
        if not paper["venue_source"]:
            paper["venue_source"] = "category-whitelist"

    return paper


def batch_enrich(papers: list) -> list:
    for p in papers:
        enrich_paper(p)
    return papers


# ================================================================
# Simple tags (no stars)
# ================================================================
def paper_tags(paper: dict) -> list:
    """Generate human-readable tags."""
    tags = []
    cites = paper.get("citation_count") or 0
    # year might be "None" string from str(None), or actual None
    raw_year = paper.get("year", 0) or 0
    try:
        year = int(raw_year)
    except (ValueError, TypeError):
        year = 0
    real_venue = paper.get("real_venue", "") or paper.get("venue", "")
    journal_ref = paper.get("journal_ref", "")
    category = paper.get("category", "")
    from datetime import datetime
    cy = datetime.now().year
    age = max(1, cy - year) if year else 5
    title_lower = (paper.get("title", "") or "").lower()

    # Venue quality
    from tools.academic_search import _is_top_venue
    if _is_top_venue(real_venue) or _is_top_venue(journal_ref):
        tags.append("顶会/顶刊")

    # Citation-based
    if cites >= 500:
        tags.append("高被引")
    elif cites >= 100 and age <= 3:
        tags.append("高被引新星")
    elif cites >= 100 and age >= 5:
        tags.append("入门必读")
    elif age <= 2:
        tags.append("前沿热点")

    # Category-based
    if CATEGORY_WEIGHTS.get(category, 0) >= 0.5:
        tags.append("领域核心")

    # Content-based
    if any(kw in title_lower for kw in ["survey", "review", "综述"]):
        tags.append("综述")
    if any(kw in title_lower for kw in ["benchmark", "dataset"]):
        tags.append("工程落地")

    return tags if tags else ["预印本"]
