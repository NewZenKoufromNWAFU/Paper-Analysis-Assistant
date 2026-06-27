
from tools.academic_search import search_semantic_scholar, search_arxiv

def search_agent(state):
    queries = state.get("search_queries", [state.get("research_keyword", "AI")])
    all_results = []
    seen = set()
    for query in queries[:3]:
        try:
            for r in search_semantic_scholar(query, 8):
                key = r["title"].lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    all_results.append(r)
        except Exception as e:
            pass
    try:
        for r in search_arxiv(queries[0], 8):
            key = r["title"].lower().strip()
            if key and key not in seen:
                seen.add(key)
                all_results.append(r)
    except:
        pass
    # Prioritize papers with arxiv_id so they can be downloaded
    all_results.sort(
        key=lambda r: (-(r.get("citation_count", 0) or 0), 0 if r.get("arxiv_id") else 1),
    )
    state["search_results"] = all_results[:18]
    downloadable = sum(1 for r in all_results[:18] if r.get("arxiv_id"))
    state["status_message"] = f"[Search] Found {len(state['search_results'])} papers, {downloadable} downloadable"
    return state
