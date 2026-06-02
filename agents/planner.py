"""Planner Agent - plans paper analysis tasks and generates search keywords."""
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE
from state import AgentState


def planner_agent(state: AgentState) -> AgentState:
    llm = ChatOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL, temperature=LLM_TEMPERATURE)

    direction = state.get("research_direction", "AI")
    pdf_text = state.get("pdf_text", "")
    pdf_preview = pdf_text[:2500] if pdf_text else ""

    system = SystemMessage(content="""You are an academic research planner. Given a paper and a research keyword, create an analysis plan.

The paper is the PRIMARY subject to analyze. The keyword helps find related work.

Return JSON only:
{
  "task_plan": [
    {"step": "1", "task": "Understand the paper's core contributions and methodology", "keyword": "specific keyword from the paper"},
    {"step": "2", "task": "Find related/comparative work", "keyword": "broader keyword"},
    {"step": "3", "task": "Find papers on similar methods or applications", "keyword": "method-specific keyword"}
  ],
  "search_keywords": ["keyword1", "keyword2", "keyword3"]
}""")

    human = HumanMessage(content=f"""Research keyword: {direction}
Paper text excerpt:
{pdf_preview}

Generate a focused analysis plan. Search keywords should combine the paper's specific topic with the research keyword.""")

    response = llm.invoke([system, human])
    content = response.content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

    try:
        plan_data = json.loads(content)
    except json.JSONDecodeError:
        try:
            s, e = content.find("{"), content.rfind("}") + 1
            plan_data = json.loads(content[s:e])
        except:
            plan_data = {"task_plan": [{"step": "1", "task": f"Analyze paper in the context of {direction}", "keyword": direction}], "search_keywords": [direction]}

    state["task_plan"] = plan_data.get("task_plan", [])
    state["search_keywords"] = plan_data.get("search_keywords", [direction])
    state["status_message"] = f"[Planner] Created {len(state['task_plan'])} analysis sub-tasks"
    return state
