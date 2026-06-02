"""Writer Agent - generates paper-focused literature review."""
from state import AgentState
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE


def writer_agent(state: AgentState) -> AgentState:
    llm = ChatOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL, temperature=LLM_TEMPERATURE)

    direction = state.get("research_direction", "")
    primary = state.get("primary_paper", {})
    summaries = state.get("related_papers_summary", [])
    search_results = state.get("search_results", [])
    pdf_text = state.get("pdf_text", "")

    # Build primary paper info block
    primary_title = primary.get("title", "Untitled Paper")
    primary_info = f"""**Paper Title:** {primary_title}
**Authors:** {primary.get('authors','N/A')}
**Year:** {primary.get('year','N/A')}
**Venue:** {primary.get('venue','N/A')}
**Abstract:** {primary.get('abstract','N/A')}
**Methodology:** {primary.get('methodology','N/A')}
**Key Contributions:** {primary.get('contributions','N/A')}
**Limitations:** {primary.get('limitations','N/A')}"""

    # PDF excerpt for deeper context
    pdf_excerpt = pdf_text[:6000] if len(pdf_text) > 6000 else pdf_text

    # Related work
    related_info = "\n\n".join(summaries[:10]) if summaries else "No related papers found."

    # References
    refs = []
    for i, r in enumerate(search_results[:15], 1):
        refs.append(f"[{i}] {r.get('authors','')} ({r.get('year','')}). {r.get('title','')}. {r.get('venue','')}. {r.get('url','')}")
    references = "\n".join(refs)

    # Revision note
    revision_note = ""
    if state.get("review_feedback") and state.get("revision_round", 0) > 0:
        fb = state["review_feedback"]
        revision_note = f"""

IMPORTANT - Revision Round {state['revision_round']}:
Please address these reviewer comments:
- Score: {fb.get('score','N/A')}/10
- Completeness: {fb.get('completeness','')}
- Accuracy: {fb.get('accuracy','')}
- Structure issues: {fb.get('structure','')}
- Suggestions: {fb.get('suggestions','')}"""

    system = SystemMessage(content="""You are a senior academic researcher writing a paper analysis review. You MUST focus your analysis primarily on the UPLOADED PAPER, using related works only for comparison and context.

Write the review in Chinese. Structure as follows:

## 1. Paper Overview
Summarize what this paper is about, the core problem it addresses, and the key contributions.

## 2. Methodology Deep Dive
Analyze in detail the methods, algorithms, or frameworks proposed in this paper. Explain how they work and why they are novel. Reference specific details from the paper text.

## 3. Experimental Analysis
If the paper includes experiments, analyze the experimental setup, baselines, datasets, results, and what the numbers mean.

## 4. Comparison with Related Work
Compare this paper with 3-5 related works. Highlight what makes this paper different or better. Cite as [1], [2] etc.

## 5. Strengths and Weaknesses
Honest assessment: what this paper does well, and where it falls short.

## 6. Conclusion and Future Directions
Summary and potential future work this paper opens up.

IMPORTANT: The uploaded paper IS the primary subject. The research keyword "{direction}" is only used to find contextual related work. Do NOT write a generic literature review about the keyword - write an analysis OF this specific paper.""")

    human = HumanMessage(content=f"""Research keyword (for related work context only): {direction}

PRIMARY PAPER TO ANALYZE:
{primary_info}

PAPER TEXT EXCERPT:
{pdf_excerpt[:5000]}

Related Work Summaries:
{related_info[:3000]}
{revision_note}

Please write a comprehensive analysis OF THIS SPECIFIC PAPER. Every section should reference details from the paper text above. Use citation numbers [1], [2] etc. for related work references.""")

    response = llm.invoke([system, human])
    state["draft_report"] = response.content
    state["draft_references"] = references
    state["status_message"] = f"[Writer] Draft generated (revision round {state.get('revision_round', 0)})"
    return state
