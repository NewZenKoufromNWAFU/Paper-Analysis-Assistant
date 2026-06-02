"""Reviewer Agent - scores the paper analysis report."""
import json
import re
from state import AgentState
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE, MIN_REVIEW_SCORE, MAX_REVIEW_ROUNDS


def reviewer_agent(state: AgentState) -> AgentState:
    llm = ChatOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL, temperature=0.1)

    report = state.get("draft_report", "")
    direction = state.get("research_direction", "")
    primary = state.get("primary_paper", {})
    pdf_text = state.get("pdf_text", "")[:3000]

    system = SystemMessage(content="""You are a rigorous academic peer reviewer. Evaluate whether this review accurately and thoroughly analyzes the UPLOADED PAPER.

Return JSON only:
{
  "score": 8.5,
  "completeness": "Does the review cover all key aspects of THE PAPER? Missing sections?",
  "accuracy": "Are the described methods, results, and contributions faithful to the paper text?",
  "structure": "Is the review well-organized and easy to follow?",
  "suggestions": "Specific improvements to better analyze THIS paper (not generic advice)",
  "needs_revision": false
}

Score 0-10. needs_revision=true if score < 7.5 or the review is generic rather than paper-specific.""")

    human = HumanMessage(content=f"""Paper analyzed: {primary.get('title','Unknown')}
Research keyword: {direction}

Paper text excerpt for fact-checking:
{pdf_text}

Review to evaluate:
{report[:8000]}

Return JSON only.""")

    response = llm.invoke([system, human])
    content = response.content.strip()
    if content.startswith("```json"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
    elif content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

    try:
        feedback = json.loads(content)
    except json.JSONDecodeError:
        try:
            s, e = content.find("{"), content.rfind("}") + 1
            feedback = json.loads(content[s:e])
        except:
            score_match = re.search(r'"score"\s*:\s*([\d.]+)', content)
            score = float(score_match.group(1)) if score_match else 6.0
            feedback = {"score": score, "completeness": "", "accuracy": "", "structure": "", "suggestions": "", "needs_revision": score < MIN_REVIEW_SCORE}

    feedback["needs_revision"] = feedback.get("needs_revision", feedback.get("score", 0) < MIN_REVIEW_SCORE)
    round_num = state.get("revision_round", 0)
    if feedback.get("needs_revision") and round_num >= MAX_REVIEW_ROUNDS:
        feedback["needs_revision"] = False
        state["status_message"] = f"[Reviewer] Score: {feedback.get('score','N/A')}/10 - Max rounds, accepting"
    elif feedback.get("needs_revision"):
        state["status_message"] = f"[Reviewer] Score: {feedback.get('score','N/A')}/10 - Revision needed (round {round_num+1}/{MAX_REVIEW_ROUNDS})"
    else:
        state["status_message"] = f"[Reviewer] Score: {feedback.get('score','N/A')}/10 - Accepted"

    state["review_feedback"] = feedback
    return state
