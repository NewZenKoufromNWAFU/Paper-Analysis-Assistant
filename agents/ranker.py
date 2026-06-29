"""Ranker Agent - ranks papers by difficulty for beginners."""
import json
from state import AgentState
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE

def ranker_agent(state):
    llm = ChatOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL, temperature=0.1)
    analyses = state.get("paper_analyses", [])
    if not analyses:
        state["ranked_papers"] = []
        state["status_message"] = "[Ranker] No papers to rank"
        return state
    items = []
    for i, a in enumerate(analyses):
        items.append({"id":i,"title":a.get("title",""),"abstract":(a.get("abstract","")or"")[:500],"year":a.get("year",""),"is_survey":a.get("is_survey",False),"math_density":a.get("math_density","medium"),"concept_level":a.get("concept_level","intermediate"),"page_count":a.get("page_count",10),"citation_count":a.get("citation_count",0),"algorithm_improvement":a.get("algorithm_improvement",""),"benchmark_data":a.get("benchmark_data","")})
    items_json = json.dumps(items, ensure_ascii=False)
    prompt = "You rank academic papers for a beginner learning path. Score each 1-10 (1=easiest). Surveys are easiest. High math = harder. Return JSON array sorted easiest-first: [{id,difficulty_score,difficulty_label,reason,learning_goal,prerequisite,estimated_hours,key_sections}]"
    human = HumanMessage(content=f"Papers: {items_json}. Rank easiest to hardest. Return JSON array only.")
    resp = llm.invoke([SystemMessage(content=prompt), human])
    content = resp.content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
    try:
        ranking = json.loads(content)
    except:
        s, e = content.find("["), content.rfind("]") + 1
        try: ranking = json.loads(content[s:e])
        except: ranking = []
    ranked = []
    for r in ranking:
        idx = r.get("id", 0)
        if isinstance(idx, int) and 0 <= idx < len(analyses):
            pa = analyses[idx]
            ranked.append({
                "title": pa.get("title",""),
                "authors": pa.get("authors",""),
                "year": pa.get("year",""),
                "arxiv_id": pa.get("arxiv_id",""),
                "local_path": pa.get("local_path",""),
                "difficulty_score": r.get("difficulty_score", 5),
                "difficulty_label": r.get("difficulty_label", "Intermediate"),
                "reason": r.get("reason",""),
                "learning_goal": r.get("learning_goal",""),
                "prerequisite": r.get("prerequisite",""),
                "estimated_hours": r.get("estimated_hours", 2),
                "key_sections": r.get("key_sections",""),
                "algorithm_improvement": analyses[idx].get("algorithm_improvement",""),
                "benchmark_data": analyses[idx].get("benchmark_data",""),
            })
    state["ranked_papers"] = ranked
    state["status_message"] = f"[Ranker] Ranked {len(ranked)} papers from easy to hard"
    return state
