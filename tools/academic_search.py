import sys
import time
import traceback
import requests
import xml.etree.ElementTree as ET
from typing import List, Optional
from config import MAX_SEARCH_RESULTS, SEMSCHOLAR_API_KEY

# --- 权威期刊/会议列表 ---
TOP_VENUES = {
    "neurips", "nips", "icml", "iclr", "cvpr", "iccv", "eccv",
    "acl", "emnlp", "naacl", "aaai", "ijcai", "uai", "aistats",
    "jmlr", "tpami", "ijcv", "tacl", "colt",
    "osdi", "sosp", "sigmod", "vldb", "stoc", "focs", "soda",
    "nsdi", "eurosys", "isca", "micro", "hpca", "asplos",
    "pldi", "popl", "icse", "sigcomm", "mobicom", "sensys",
    "nature", "science", "cell", "pnas", "nature communications",
    "nature methods", "nature machine intelligence",
    "chi", "vis", "infovis", "icra", "iros", "rss",
    "ccs", "s&p", "usenix security", "crypto", "eurocrypt",
    "cacm", "ieee transactions on",
}

# 录用关键词（用于 comments 字段匹配）
ACCEPTED_KEYWORDS = [
    "accepted", "published", "oral", "poster", "spotlight",
    "to appear", "forthcoming", "in press", "accepted at",
]

def _is_top_venue(venue: str) -> bool:
    if not venue:
        return False
    v = venue.lower().strip()
    for tv in TOP_VENUES:
        if tv in v:
            return True
    return False


def _paper_key(paper: dict) -> str:
    return (paper.get("arxiv_id") or paper.get("paper_id") or paper.get("title", "")).strip().lower()


_S2_CALL_GAP = 1.5       # minimum seconds between Semantic Scholar API calls
_last_s2_call = 0.0


def _fetch_json(url, params, max_attempts=3, api_key=None):
    """GET JSON with rate-limit guard + exponential backoff + API key support."""
    global _last_s2_call
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    # Enforce minimum interval between API calls (avoids burst 429s)
    now = time.time()
    gap = now - _last_s2_call
    if gap < _S2_CALL_GAP:
        time.sleep(_S2_CALL_GAP - gap)
    _last_s2_call = time.time()

    for attempt in range(max_attempts):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code == 429:
                wait = 2 * (2 ** attempt)  # exponential backoff: 2s, 4s, 8s
                print(f"[INFO] Semantic Scholar 429 rate-limited, waiting {wait}s (attempt {attempt+1}/{max_attempts})...",
                      file=sys.stderr)
                if attempt < max_attempts - 1:
                    time.sleep(wait)
                    continue
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            print(f"[WARNING] Semantic Scholar HTTP {e.response.status_code} (attempt {attempt}): {e}",
                  file=sys.stderr)
            if attempt < max_attempts - 1:
                time.sleep(1)
                continue
            return None
        except Exception:
            print(f"[WARNING] Semantic Scholar API error (attempt {attempt}):", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            if attempt < max_attempts - 1:
                time.sleep(2)
                continue
            return None
    return None


def search_semantic_scholar(query: str, max_results: int = MAX_SEARCH_RESULTS,
                            year_from: Optional[int] = None, year_to: Optional[int] = None,
                            offset: int = 0) -> List[dict]:
    params = {
        "query": query, "limit": min(max_results, 50), "offset": offset,
        "fields": "title,authors,year,venue,abstract,url,citationCount,externalIds,publicationVenue,journal",
    }
    if year_from and year_to:
        params["year"] = f"{year_from}-{year_to}"
    elif year_from:
        params["year"] = f"{year_from}-"
    elif year_to:
        params["year"] = f"1900-{year_to}"

    # Use API key if available (free, 10 req/s vs 1 req/s without)
    api_key = SEMSCHOLAR_API_KEY or None
    data = _fetch_json("https://api.semanticscholar.org/graph/v1/paper/search", params,
                       max_attempts=3 if not api_key else 2, api_key=api_key)
    if data is None:
        return []

    results = []
    for p in data.get("data", []):
        authors = ", ".join([a.get("name", "") for a in p.get("authors", [])[:5]])
        if p.get("authors") and len(p["authors"]) > 5:
            authors += " et al."
        ext = p.get("externalIds", {}) or {}
        venue_raw = p.get("venue", "") or ""
        journal = p.get("journal", {}) or {}
        journal_name = journal.get("name", "") if journal else ""
        pub_venue = p.get("publicationVenue") or {}
        pub_venue_name = pub_venue.get("name", "") if isinstance(pub_venue, dict) else ""
        best_venue = pub_venue_name or journal_name or venue_raw or ""
        results.append({
            "title": p.get("title", ""),
            "authors": authors,
            "year": str(p.get("year", "")),
            "venue": best_venue,
            "abstract": p.get("abstract", "") or "",
            "url": p.get("url", ""),
            "citation_count": p.get("citationCount", 0) or 0,
            "arxiv_id": ext.get("ArXiv", ""),
            "paper_id": p.get("paperId", ""),
            "doi": "",
            "category": "",
            "comments": "",
            "journal_ref": "",
        })
    return results


# ================================================================
# arXiv — Layer 1: 解析隐藏字段 (journal-ref / DOI / comments / category)
# ================================================================
def _parse_arxiv_hidden_fields(entry, ns) -> dict:
    """Extract journal-ref, DOI, comments, and arXiv category from a single entry."""
    hidden = {"journal_ref": "", "doi": "", "comments": "", "category": ""}

    # journal-ref
    jr = entry.find("arxiv:journal_ref", ns)
    if jr is not None and jr.text:
        hidden["journal_ref"] = jr.text.strip()

    # DOI
    d = entry.find("arxiv:doi", ns)
    if d is not None and d.text:
        hidden["doi"] = d.text.strip()

    # comments
    c = entry.find("arxiv:comment", ns)
    if c is not None and c.text:
        hidden["comments"] = c.text.strip()

    # primary category
    cat = entry.find("arxiv:primary_category", ns)
    if cat is not None:
        hidden["category"] = cat.get("term", "")

    return hidden


def _check_comments_for_acceptance(comments: str) -> bool:
    """Check if comments field contains acceptance keywords."""
    if not comments:
        return False
    lower = comments.lower()
    return any(kw in lower for kw in ACCEPTED_KEYWORDS)


def search_arxiv(query: str, max_results: int = MAX_SEARCH_RESULTS,
                  year_from: Optional[int] = None, year_to: Optional[int] = None) -> List[dict]:
    base_url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}", "start": 0,
        "max_results": min(max_results, 50),
        "sortBy": "relevance", "sortOrder": "descending",
    }
    for attempt in range(2):
        try:
            resp = requests.get(base_url, params=params, timeout=15)
            resp.raise_for_status()
            break
        except Exception:
            if attempt == 1:
                return []
            time.sleep(1)

    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return []

    results = []
    for entry in root.findall("atom:entry", ns):
        t = entry.find("atom:title", ns)
        title = " ".join(t.text.split()) if t is not None and t.text else ""
        authors = []
        for a in entry.findall("atom:author", ns):
            n = a.find("atom:name", ns)
            if n is not None and n.text:
                authors.append(n.text)

        s = entry.find("atom:summary", ns)
        abstract = s.text.strip() if s is not None and s.text else ""

        pub = entry.find("atom:published", ns)
        year_str = pub.text[:4] if pub is not None and pub.text else ""

        lid = entry.find("atom:id", ns)
        url = lid.text if lid is not None and lid.text else ""
        arxiv_id = url.split("/abs/")[-1] if "/abs/" in url else ""

        # ===== Layer 1: 解析隐藏字段 =====
        hidden = _parse_arxiv_hidden_fields(entry, ns)

        try:
            year_int = int(year_str)
        except ValueError:
            year_int = 0
        if year_from and year_int < year_from:
            continue
        if year_to and year_int > year_to:
            continue

        results.append({
            "title": title,
            "authors": ", ".join(authors[:5]),
            "year": year_str,
            "venue": "arXiv",
            "abstract": abstract,
            "url": url,
            "citation_count": None,   # arXiv doesn't provide citation counts
            "arxiv_id": arxiv_id,
            "paper_id": "",
            # Layer 1 fields
            "doi": hidden["doi"],
            "category": hidden["category"],
            "comments": hidden["comments"],
            "journal_ref": hidden["journal_ref"],
            "accepted_hint": _check_comments_for_acceptance(hidden["comments"]),
        })
    return results


def search_papers(query: str, count: int = 5,
                  year_from: Optional[int] = None,
                  year_to: Optional[int] = None,
                  offset: int = 0,
                  authoritative_only: bool = False,
                  exclude_keys: Optional[set] = None) -> List[dict]:
    exclude_keys = exclude_keys or set()
    count = max(1, min(count, 10))
    fetch_count = max(count * 3 + len(exclude_keys), 20)

    sem_results = search_semantic_scholar(query, fetch_count, year_from, year_to, offset)
    # Only fetch arXiv if SemSch didn't return enough
    if len(sem_results) < count * 2:
        arx_results = search_arxiv(query, fetch_count, year_from, year_to)
    else:
        arx_results = []

    # Build SemSch index by arxiv_id for enrichment
    sem_by_aid = {}
    for r in sem_results:
        aid = r.get("arxiv_id", "")
        if aid:
            sem_by_aid[aid] = r

    # Smart merge: SemSch papers first (have real data), arXiv as fallback
    seen = set()
    merged = []
    for r in sem_results + arx_results:
        key = _paper_key(r)
        if not key or key in seen or key in exclude_keys:
            continue
        seen.add(key)

        # Enrich arXiv results with SemSch data
        aid = r.get("arxiv_id", "")
        if aid and aid in sem_by_aid:
            sem = sem_by_aid[aid]
            if r.get("citation_count") is None and sem.get("citation_count"):
                r["citation_count"] = sem["citation_count"]
            sem_venue = sem.get("venue", "")
            if (not r.get("venue") or r.get("venue") == "arXiv") and sem_venue and sem_venue != "arXiv":
                r["venue"] = sem_venue

        if authoritative_only:
            venue = r.get("venue", "")
            cites = r.get("citation_count") or 0
            jr = r.get("journal_ref", "")
            accepted = r.get("accepted_hint", False)
            # Keep: top venues, papers with real citations, accepted arXiv, or real journal-ref
            if _is_top_venue(venue) or cites >= 10 or accepted or jr:
                pass
            elif cites is None or cites == 0:
                # Paper with absolutely no data — still keep if it at least has a real venue
                if venue and venue.lower() != "arxiv":
                    pass
                else:
                    continue

        merged.append(r)

    return merged[:count]
