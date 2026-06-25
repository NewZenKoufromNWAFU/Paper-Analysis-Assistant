"""Planner Agent — lightweight: generates 2-3 search strategies from NL input."""
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE
from state import AgentState, SearchPlan

_PLANNER_PROMPT = """\
Given a research interest description, generate 2-3 search strategies.
Return ONLY valid JSON with keys: core_topic, sub_topics, strategies, reasoning.

Each strategy: type (survey|foundational|latest), query (English 4-10 words),
sources (array of "semantic_scholar" and/or "arxiv"), count (5-10), reason (one sentence).

Keep JSON compact. No markdown fences.
"""


def _ensure_sources(raw: list) -> list:
    """Force 'arxiv' into every strategy so Semantic Scholar failure is survivable."""
    allowed = {"semantic_scholar", "arxiv"}
    sources = [s for s in raw if s in allowed]
    if not sources:
        sources = ["semantic_scholar", "arxiv"]
    if "arxiv" not in sources:
        sources.append("arxiv")
    return sources


def planner_agent(state: AgentState) -> AgentState:
    llm = ChatOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL, temperature=0.1)
    interest = state.get("research_interest") or state.get("research_keyword", "AI")

    if len(interest.split()) <= 4:
        interest = f"Research topic: {interest}. Provide survey and latest papers."

    system = SystemMessage(content=_PLANNER_PROMPT)
    human = HumanMessage(content=f"Research interest:\n{interest}")
    resp = llm.invoke([system, human])
    content = resp.content.strip()

    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

    plan: SearchPlan = {}
    try:
        plan = json.loads(content)
    except Exception:
        s, e = content.find("{"), content.rfind("}") + 1
        try:
            plan = json.loads(content[s:e])
        except Exception:
            kw = state.get("research_keyword", interest.split()[-1] if interest else "AI")
            plan = {
                "core_topic": kw,
                "sub_topics": [kw],
                "strategies": [
                    {"type": "survey", "query": f"{kw} survey", "sources": ["semantic_scholar"], "count": 8, "reason": "Broad overview"},
                    {"type": "latest", "query": kw, "sources": ["semantic_scholar", "arxiv"], "count": 8, "reason": "Recent advances"},
                ],
                "reasoning": f"Fallback for '{kw}'",
            }

    plan.setdefault("core_topic", interest[:60])
    plan.setdefault("sub_topics", [])
    strategies: list = plan.get("strategies", [])
    plan["strategies"] = [
        {**s, "count": max(3, min(s.get("count", 8), 15)),
         "sources": _ensure_sources(s.get("sources", []))}
        for s in strategies
    ]

    state["search_plan"] = plan
    state["search_queries"] = [s["query"] for s in plan["strategies"]]
    state["research_interest"] = interest
    state["status_message"] = (
        f"[Planner] {plan.get('core_topic','?')} | {len(plan['strategies'])} strategies"
    )
    return state
