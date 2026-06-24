import requests
import xml.etree.ElementTree as ET
from typing import List, Optional
from config import MAX_SEARCH_RESULTS

# --- 权威期刊/会议列表 ---
TOP_VENUES = {
    # AI / ML / CV / NLP
    "neurips", "nips", "icml", "iclr", "cvpr", "iccv", "eccv",
    "acl", "emnlp", "naacl", "aaai", "ijcai", "uai", "aistats",
    "jmlr", "tpami", "ijcv", "tacl", "colt",
    # Systems / Theory / DB
    "osdi", "sosp", "sigmod", "vldb", "stoc", "focs", "soda",
    "nsdi", "eurosys", "isca", "micro", "hpca", "asplos",
    "pldi", "popl", "icse", "sigcomm", "mobicom", "sensys",
    # Science / Interdisciplinary
    "nature", "science", "cell", "pnas", "nature communications",
    "nature methods", "nature machine intelligence",
    # HCI / Visualization / Robotics
    "chi", "vis", "infovis", "icra", "iros", "rss",
    # Security / Crypto
    "ccs", "s&p", "usenix security", "crypto", "eurocrypt",
    # General top CS journals
    "cacm", "ieee transactions on",
}

def _is_top_venue(venue: str) -> bool:
    """Check if a venue name matches known top venues."""
    if not venue:
        return False
    v = venue.lower().strip()
    # Direct match
    for tv in TOP_VENUES:
        if tv in v:
            return True
    return False


def _paper_key(paper: dict) -> str:
    """Generate a unique key for a paper, preferring arxiv_id over paper_id over title."""
    return (paper.get("arxiv_id") or paper.get("paper_id") or paper.get("title", "")).strip().lower()


def search_semantic_scholar(query: str, max_results: int = MAX_SEARCH_RESULTS,
                            year_from: Optional[int] = None, year_to: Optional[int] = None,
                            offset: int = 0) -> List[dict]:
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": min(max_results, 100),
        "offset": offset,
        "fields": "title,authors,year,venue,abstract,url,citationCount,externalIds,publicationVenue,journal",
    }
    # Semantic Scholar year filter: "2019-2023" format
    if year_from and year_to:
        params["year"] = f"{year_from}-{year_to}"
    elif year_from:
        params["year"] = f"{year_from}-"
    elif year_to:
        params["year"] = f"1900-{year_to}"

    try:
        resp = requests.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Search error: {e}")
        return []
    results = []
    for p in data.get("data", []):
        authors = ", ".join([a.get("name","") for a in p.get("authors",[])[:5]])
        if p.get("authors") and len(p["authors"]) > 5:
            authors += " et al."
        ext = p.get("externalIds", {}) or {}
        # Extract journal/venue info
        venue_raw = p.get("venue", "") or ""
        journal = p.get("journal", {}) or {}
        journal_name = journal.get("name", "") if journal else ""
        venue_display = journal_name or venue_raw or ""
        results.append({
            "title": p.get("title",""),
            "authors": authors,
            "year": str(p.get("year","")),
            "venue": venue_display,
            "abstract": p.get("abstract","") or "",
            "url": p.get("url",""),
            "citation_count": p.get("citationCount", 0) or 0,
            "arxiv_id": ext.get("ArXiv",""),
            "paper_id": p.get("paperId",""),
        })
    return results


def search_arxiv(query: str, max_results: int = MAX_SEARCH_RESULTS,
                  year_from: Optional[int] = None, year_to: Optional[int] = None) -> List[dict]:
    base_url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}", "start": 0,
        "max_results": min(max_results, 50),
        "sortBy": "relevance", "sortOrder": "descending",
    }
    try:
        resp = requests.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"arXiv error: {e}")
        return []
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


def search_papers(query: str, count: int = 5,
                  year_from: Optional[int] = None,
                  year_to: Optional[int] = None,
                  offset: int = 0,
                  authoritative_only: bool = False,
                  exclude_keys: Optional[set] = None) -> List[dict]:
    """Unified search: returns `count` merged + deduplicated results.

    Args:
        query: search keyword or paper title.
        count: desired number of results (1-10).
        year_from / year_to: year filter.
        offset: pagination offset for Semantic Scholar.
        authoritative_only: if True, only return papers from known top venues
                            or with >= 50 citations.
        exclude_keys: set of paper keys already shown in previous batches;
                      these will be filtered out.

    Returns:
        List of paper dicts, length <= count.
    """
    exclude_keys = exclude_keys or set()
    count = max(1, min(count, 10))
    # 多搜一些，留出被 exclude_keys 过滤掉的余量
    fetch_count = max(count * 3 + len(exclude_keys), 20)
    sem_results = search_semantic_scholar(query, fetch_count, year_from, year_to, offset)
    arx_results = search_arxiv(query, fetch_count, year_from, year_to)

    # Merge + dedup by unique key, excluding already-shown papers
    seen = set()
    merged = []
    for r in sem_results + arx_results:
        key = _paper_key(r)
        if not key:
            continue
        if key in seen or key in exclude_keys:
            continue
        seen.add(key)

        # 权威过滤：arXiv 预印本放行（最终发表期刊未知），
        # 已知期刊但不是顶级且低引用的才过滤
        if authoritative_only:
            venue = r.get("venue", "")
            cites = r.get("citation_count", 0) or 0
            if not venue or venue.lower() == "arxiv":
                # arXiv 预印本 / 无 venue → 放行
                pass
            elif cites >= 50 or _is_top_venue(venue):
                pass
            else:
                continue

        merged.append(r)

    return merged[:count]
