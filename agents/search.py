"""Search Agent - searches academic databases."""
from state import AgentState
from tools.academic_search import search_semantic_scholar, search_arxiv


def search_agent(state: AgentState) -> AgentState:
    keywords = state.get("search_keywords", [state.get("research_direction", "AI")])
    all_results = []
    seen = set()

    for keyword in keywords[:5]:
        try:
            results = search_semantic_scholar(keyword)
            for r in results:
                key = r["title"].lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    all_results.append(r)
        except Exception as e:
            state.setdefault("status_message", "")
            state["status_message"] += f"\nSearch warning for '{keyword}': {e}"

    # Also try arXiv
    try:
        arxiv_results = search_arxiv(keywords[0])
        for r in arxiv_results:
            key = r["title"].lower().strip()
            if key and key not in seen:
                seen.add(key)
                all_results.append(r)
    except Exception:
        pass

    state["search_results"] = all_results[:15]
    state["status_message"] = f"[Search] Found {len(state['search_results'])} related papers"
    return state
