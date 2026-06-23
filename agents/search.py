
from state import AgentState
from tools.academic_search import search_semantic_scholar, search_arxiv

def search_agent(state: AgentState) -> AgentState:
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
    with_id = [r for r in all_results if r.get("arxiv_id")]
    without_id = [r for r in all_results if not r.get("arxiv_id")]
    state["search_results"] = (with_id + without_id)[:18]
    state["status_message"] = f"[Search] Found {len(state['search_results'])} papers, {len(with_id)} downloadable"
    return state
