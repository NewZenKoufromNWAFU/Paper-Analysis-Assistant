"""Planner Agent - generates search queries."""
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE
from state import AgentState

def planner_agent(state: AgentState) -> AgentState:
    llm = ChatOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL, temperature=LLM_TEMPERATURE)
    keyword = state.get("research_keyword", "AI")
    system = SystemMessage(content="""You are an academic learning path planner. Given a research keyword, generate 3 search queries for finding beginner-friendly papers: 1 broad survey query, 1 classic paper query, 1 latest trend query. Return JSON only with key search_queries as array.""")
    human = HumanMessage(content=f"Research keyword: {keyword}. Generate 3 search queries.")
    resp = llm.invoke([system, human])
    content = resp.content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
    try:
        data = json.loads(content)
    except:
        s, e = content.find("{"), content.rfind("}") + 1
        try:
            data = json.loads(content[s:e])
        except:
            data = {"search_queries": [keyword, keyword + " survey", keyword + " tutorial"]}
    state["search_queries"] = data.get("search_queries", [keyword])
    state["status_message"] = f"[Planner] Generated {len(state["search_queries"])} search queries"
    return state