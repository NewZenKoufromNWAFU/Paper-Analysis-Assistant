"""Writer Agent - generates the beginner learning path report."""
from state import AgentState
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE

def writer_agent(state):
    llm = ChatOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL, temperature=LLM_TEMPERATURE)
    keyword = state.get("research_keyword", "")
    ranked = state.get("ranked_papers", [])
    if not ranked:
        state["learning_path_report"] = "No papers to report"
        state["status_message"] = "[Writer] No papers"
        return state
    papers_lines = []
    for i, rp in enumerate(ranked, 1):
        lines = []
        lines.append(f"## Paper {i}: {rp["title"]} ({rp["year"]})")
        lines.append(f"- Difficulty: {rp["difficulty_label"]} ({rp["difficulty_score"]}/10)")
        lines.append(f"- Authors: {rp["authors"]}")
        lines.append(f"- Estimated reading time: {rp["estimated_hours"]}h")
        lines.append(f"- Why here: {rp["reason"]}")
        lines.append(f"- Learning goal: {rp["learning_goal"]}")
        algo = rp.get("algorithm_improvement", "")
        if algo:
            lines.append(f"- Algorithm: {algo}")
        bench = rp.get("benchmark_data", "")
        if bench:
            lines.append(f"- Benchmark: {bench}")
        lines.append(f"- Prerequisite: {rp["prerequisite"]}")
        lines.append(f"- Key sections: {rp["key_sections"]}")
        papers_lines.append("\n".join(lines))
    papers_blob = "\n\n".join(papers_lines)
    system = SystemMessage(content=f"You are an academic mentor creating a beginner learning path for {keyword}. Write in Chinese. Generate a warm, encouraging, structured guide. Include: 1. An engaging overview of the learning path. 2. For each numbered paper: a summary, why it is placed at this position, key algorithm breakthroughs, important benchmark results, and practical reading tips. 3. A final summary with next steps after completing the path. Use Markdown with emoji for visual appeal.")
    human = HumanMessage(content=f"Papers to create learning path for:\n{papers_blob}\n\nWrite a comprehensive Chinese learning path guide. Make it beginner-friendly and motivating.")
    resp = llm.invoke([system, human])
    state["learning_path_report"] = resp.content
    state["status_message"] = f"[Writer] Learning path generated for {len(ranked)} papers"
    return state
