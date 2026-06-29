import time
import requests
import xml.etree.ElementTree as ET
import sys
import traceback
from typing import List, Optional
from config import MAX_SEARCH_RESULTS
import os
_S2_API_KEY = os.getenv("SEMSCHOLAR_API_KEY", "")

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


_S2_API_CALL_INTERVAL = 1.5   # seconds between Semantic Scholar API calls
_last_s2_call = 0.0           # first call goes immediately


def _fetch_json(url, params):
    """GET JSON from API with rate-limit guard + exponential backoff."""
    global _last_s2_call

    # Enforce minimum interval between calls
    now = time.time()
    gap = now - _last_s2_call
    if gap < _S2_API_CALL_INTERVAL:
        time.sleep(_S2_API_CALL_INTERVAL - gap)
    _last_s2_call = time.time()

    headers = {"x-api-key": _S2_API_KEY} if _S2_API_KEY else {}

    for attempt in range(2):
        try:
            resp = requests.get(url, params=params, timeout=15, headers=headers)
            if resp.status_code == 429:
                wait = 2 * (2 ** attempt)  # 2, 4 seconds
                print(f"[INFO] Semantic Scholar 429 rate-limit, waiting {wait}s (attempt {attempt+1}/2)...",
                      file=sys.stderr)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            print(f"[WARNING] Semantic Scholar HTTP {e.response.status_code} (attempt {attempt}): {e}",
                  file=sys.stderr)
            if attempt < 2:
                time.sleep(1)
                continue
            return None
        except Exception:
            print(f"[WARNING] Semantic Scholar API error (attempt {attempt}):", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            if attempt < 2:
                time.sleep(1)
                continue
            return None
    return None

def search_semantic_scholar(query: str, max_results: int = MAX_SEARCH_RESULTS,
                            year_from: Optional[int] = None, year_to: Optional[int] = None,
                            offset: int = 0) -> List[dict]:
    params = {
        "query": query, "limit": min(max_results, 100), "offset": offset,
        "fields": "title,authors,year,venue,abstract,url,citationCount,externalIds,publicationVenue,journal",
    }
    if year_from and year_to:
        params["year"] = f"{year_from}-{year_to}"
    elif year_from:
        params["year"] = f"{year_from}-"
    elif year_to:
        params["year"] = f"1900-{year_to}"

    data = _fetch_json("https://api.semanticscholar.org/graph/v1/paper/search", params)
    if data is None:
        print("[WARNING] search_semantic_scholar: API returned None (check error above)", file=sys.stderr)
        return []

    paper_count = len(data.get("data", []))
    print(f"[INFO] Semantic Scholar returned {paper_count} papers for query '{query[:40]}'", file=sys.stderr)

    results = []
    for p in data.get("data", []):
        authors = ", ".join([a.get("name", "") for a in p.get("authors", [])[:5]])
        if p.get("authors") and len(p["authors"]) > 5:
            authors += " et al."
        ext = p.get("externalIds", {}) or {}
        # Try multiple sources for the real venue name
        venue_raw = p.get("venue", "") or ""
        journal = p.get("journal", {}) or {}
        journal_name = journal.get("name", "") if journal else ""
        pub_venue = p.get("publicationVenue") or {}
        pub_venue_name = pub_venue.get("name", "") if isinstance(pub_venue, dict) else ""
        # Prefer: publicationVenue name > journal name > venue
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
        })
    return results


def search_arxiv(query: str, max_results: int = MAX_SEARCH_RESULTS,
                  year_from: Optional[int] = None, year_to: Optional[int] = None,
                  offset: int = 0) -> List[dict]:
    base_url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}", "start": offset,
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
            "citation_count": 0,
            "arxiv_id": arxiv_id,
            "paper_id": "",
        })
    return results


def _batch_fetch_citations(sem_results: list, arx_results: list) -> list:
    """When Semantic Scholar fails, try to fetch citations for arXiv papers via single-paper API."""
    if sem_results:
        return sem_results  # SS worked, no need
    arxiv_ids = [p.get("arxiv_id","") for p in arx_results if p.get("arxiv_id")]
    if not arxiv_ids:
        return []
    import time
    fetched = {}
    for aid in arxiv_ids[:5]:  # limit to 5 to avoid rate limiting
        try:
            time.sleep(1.1)
            url = f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{aid}"
            resp = requests.get(url, params={"fields":"citationCount"}, timeout=10)
            if resp.status_code == 200:
                d = resp.json()
                fetched[aid] = d.get("citationCount", 0) or 0
        except:
            pass
    for p in arx_results:
        aid = p.get("arxiv_id","")
        if aid in fetched:
            p["citation_count"] = fetched[aid]
    return arx_results


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
    arx_results = search_arxiv(query, fetch_count, year_from, year_to, offset=offset)
    arx_results = _batch_fetch_citations(sem_results, arx_results)

    seen = set()
    all_merged = []
    for r in sem_results + arx_results:
        key = _paper_key(r)
        if not key or key in seen or key in exclude_keys:
            continue
        seen.add(key)
        all_merged.append(r)

    if authoritative_only:
        # Sort into two tiers 鈥?authoritative papers always first, then remainder as fallback.
        # This guarantees results are never empty when the hard threshold is too high.
        authoritative = []
        non_auth = []
        for r in all_merged:
            venue = r.get("venue", "")
            cites = r.get("citation_count", 0) or 0
            if cites >= 50 or _is_top_venue(venue):
                authoritative.append(r)
            else:
                non_auth.append(r)
        authoritative.sort(key=lambda r: r.get("citation_count", 0) or 0, reverse=True)
        non_auth.sort(key=lambda r: r.get("citation_count", 0) or 0, reverse=True)
        merged = authoritative + non_auth
    else:
        all_merged.sort(key=lambda r: r.get("citation_count", 0) or 0, reverse=True)
        merged = all_merged

    return merged[:count]
