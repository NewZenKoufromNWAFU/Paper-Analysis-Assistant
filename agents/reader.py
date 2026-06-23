"""Reader Agent - analyzes downloaded papers for learning value."""
import json
from state import AgentState
from tools.pdf_parser import parse_pdf
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE

def _safe_json_parse(response_text, default):
    content = response_text.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
    try:
        return json.loads(content)
    except:
        s, e = content.find("{"), content.rfind("}") + 1
        try: return json.loads(content[s:e])
        except: return default

def reader_agent(state: AgentState) -> AgentState:
    llm = ChatOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL, temperature=LLM_TEMPERATURE)
    papers = state.get("downloaded_papers", [])
    analyses = []
    for i, pp in enumerate(papers[:10]):
        path = pp.get("local_path", "")
        title = pp.get("title", "Unknown")
        abstract = pp.get("abstract", "")
        pdf_text = ""
        page_count = 0
        if path:
            try:
                pdf_text = parse_pdf(path)
                newlines = pdf_text.count(chr(10))
                page_count = newlines // 40 + 1
            except:
                pass
        # Phase 1: Basic metadata extraction
        sys1 = SystemMessage(content="Extract learning-relevant info. Return JSON: {{topic, is_survey, math_density, concept_level, has_tutorial}}")
        human1 = HumanMessage(content=f"Title: {title}. Abstract: {abstract[:2000]}. Pages: {page_count}")
        try:
            resp = llm.invoke([sys1, human1])
            info1 = _safe_json_parse(resp.content, {"topic": title, "is_survey": False, "math_density": "medium", "concept_level": "intermediate", "has_tutorial": False})
        except:
            info1 = {"topic": title, "is_survey": False, "math_density": "medium", "concept_level": "intermediate", "has_tutorial": False}

        # Phase 2: Algorithm improvement and benchmark extraction
        pdf_excerpt = pdf_text[:4000] if pdf_text else abstract[:2000]
        sys2 = SystemMessage(content="You extract algorithm improvements and benchmark data from a paper. Return JSON: {algorithm_improvement, benchmark_data}. algorithm_improvement: what this paper improved over prior methods (in Chinese, 2-3 sentences). benchmark_data: key experimental results, numbers, datasets used (in Chinese, 2-3 sentences). Be specific with numbers when available.")
        human2 = HumanMessage(content=f"Paper: {title}. Text: {pdf_excerpt}")
        try:
            resp = llm.invoke([sys2, human2])
            info2 = _safe_json_parse(resp.content, {"algorithm_improvement": "Not extracted", "benchmark_data": "Not extracted"})
        except:
            info2 = {"algorithm_improvement": "Not extracted", "benchmark_data": "Not extracted"}

        analyses.append({**pp, **info1, **info2, "page_count": page_count})
    state["paper_analyses"] = analyses
    state["status_message"] = f"[Reader] Analyzed {len(analyses)} papers with algorithm insights"
    return state
