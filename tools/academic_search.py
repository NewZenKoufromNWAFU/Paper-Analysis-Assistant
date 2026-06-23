import requests
import xml.etree.ElementTree as ET
from typing import List, Optional
from config import MAX_SEARCH_RESULTS

def search_semantic_scholar(query: str, max_results: int = MAX_SEARCH_RESULTS, year_from: Optional[int] = None) -> List[dict]:
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": query, "limit": min(max_results, 100), "fields": "title,authors,year,venue,abstract,url,citationCount,externalIds"}
    if year_from:
        params["year"] = f"{year_from}-"
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
        results.append({
            "title": p.get("title",""),
            "authors": authors,
            "year": str(p.get("year","")),
            "venue": p.get("venue",""),
            "abstract": p.get("abstract","") or "",
            "url": p.get("url",""),
            "citation_count": p.get("citationCount",0),
            "arxiv_id": ext.get("ArXiv",""),
            "paper_id": p.get("paperId",""),
        })
    return results
def search_arxiv(query: str, max_results: int = MAX_SEARCH_RESULTS) -> List[dict]:
    base_url = "http://export.arxiv.org/api/query"
    params = {"search_query": f"all:{query}", "start": 0, "max_results": min(max_results,50), "sortBy": "relevance", "sortOrder": "descending"}
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
        year = pub.text[:4] if pub is not None and pub.text else ""
        lid = entry.find("atom:id", ns)
        url = lid.text if lid is not None and lid.text else ""
        arxiv_id = url.split("/abs/")[-1] if "/abs/" in url else ""
        results.append({
            "title": title,
            "authors": ", ".join(authors[:5]),
            "year": year,
            "venue": "arXiv",
            "abstract": abstract,
            "url": url,
            "citation_count": 0,
            "arxiv_id": arxiv_id,
            "paper_id": "",
        })
    return results

def search_all(query: str, max_results: int = MAX_SEARCH_RESULTS) -> List[dict]:
    seen = set()
    merged = []
    for r in search_semantic_scholar(query, max_results) + search_arxiv(query, max_results):
        key = r["title"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            merged.append(r)
    return merged[:max_results]
