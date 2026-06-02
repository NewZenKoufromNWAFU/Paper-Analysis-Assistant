"""Reader Agent - extracts structured info from papers."""
from state import AgentState
from tools.pdf_parser import extract_paper_info
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE


def _llm_call(prompt: str) -> str:
    llm = ChatOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL, temperature=LLM_TEMPERATURE)
    return llm.invoke([HumanMessage(content=prompt)]).content


def reader_agent(state: AgentState) -> AgentState:
    # Extract primary paper info
    if state.get("pdf_text"):
        direction = state.get("research_direction", "")
        info = extract_paper_info(state["pdf_text"], _llm_call, direction)
        state["primary_paper"] = info
    else:
        state["primary_paper"] = {}

    # Summarize each related paper
    summaries = []
    for i, r in enumerate(state.get("search_results", [])[:8]):
        title = r.get("title", "")
        abstract = r.get("abstract", "")
        if abstract:
            prompt = f"""Summarize the following paper abstract in 2-3 sentences in Chinese, noting the key contribution:

Title: {title}
Abstract: {abstract}

Chinese summary:"""
            try:
                s = _llm_call(prompt)
                summaries.append(f"**{title}** ({r.get('year','')}): {s.strip()}")
            except Exception:
                summaries.append(f"**{title}** ({r.get('year','')}): Abstract not available")

    state["related_papers_summary"] = summaries
    state["status_message"] = f"[Reader] Extracted info from primary paper + {len(summaries)} related paper summaries"
    return state
