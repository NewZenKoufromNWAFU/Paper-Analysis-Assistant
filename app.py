import streamlit as st
import os
import tempfile
import traceback
from langgraph.graph import StateGraph
from agents.planner import planner_agent
from agents.search import search_agent
from agents.reader import reader_agent
from agents.writer import writer_agent
from agents.reviewer import reviewer_agent
from config import OUTPUT_DIR, validate_config, LLM_API_KEY
from tools.report_generator import save_markdown_report, build_report_markdown
from tools.pdf_parser import parse_pdf

st.set_page_config(page_title="Paper Analyzer", page_icon="📄", layout="wide")
st.title("📄 AI Auto Paper Analysis Assistant")
st.caption("Multi-Agent System: Planner | Search | Reader | Writer | Reviewer")

# API key check
api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
if not api_key:
    st.warning("API Key not set. Set DEEPSEEK_API_KEY or OPENAI_API_KEY environment variable.", icon="⚠️")
    with st.expander("How to set API Key"):
        st.code('$env:DEEPSEEK_API_KEY="sk-your-key"  # PowerShell', language="powershell")
        st.caption("Get a free key: https://platform.deepseek.com")

tab1, tab2 = st.tabs(["Analysis", "History"])

PROGRESS_STEPS = {
    "planner": "📋 Planning analysis tasks...",
    "search": "🔍 Searching related papers...",
    "reader": "📖 Extracting paper information...",
    "writer": "✍️ Generating literature review...",
    "reviewer": "🔎 Reviewing and scoring...",
    "finalize": "✅ Finalizing report...",
}

with tab1:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("Configuration")
        direction = st.text_input("Research Keyword", placeholder="e.g., Transformer, RLHF")
        st.caption("Used to find related papers. The PDF is the primary subject.")
        uploaded_file = st.file_uploader("Upload PDF Paper", type="pdf")
        st.caption("Required. This paper will be the focus of analysis.")
        run_btn = st.button("Start Analysis", type="primary", use_container_width=True)

    with col2:
        st.subheader("Workflow Progress")
        progress_placeholder = st.empty()

    if run_btn:
        if not direction:
            st.error("Please enter a research keyword.")
        elif not uploaded_file:
            st.error("Please upload a PDF paper to analyze.")
        else:
            issues = validate_config()
            if issues:
                for issue in issues:
                    st.error(issue)
            else:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.read())
                    pdf_path = tmp.name
                with st.spinner("Parsing PDF..."):
                    pdf_text = parse_pdf(pdf_path)
                if not pdf_text or len(pdf_text.strip()) < 100:
                    st.error("PDF appears empty or unreadable.")
                else:
                    st.success(f"PDF loaded: {len(pdf_text)} characters")

                    with progress_placeholder.container():
                        st.info("Multi-agent pipeline running...")
                        progress_bar = st.progress(0, text="Starting...")
                        status_text = st.empty()

                        def show_step(step_name, message, pct):
                            progress_bar.progress(pct, text=PROGRESS_STEPS.get(step_name, step_name))
                            status_text.markdown(message)

                        try:
                            # Build initial state
                            state = {
                                "research_direction": direction,
                                "pdf_file_path": pdf_path,
                                "pdf_text": pdf_text,
                                "task_plan": [],
                                "search_keywords": [],
                                "search_results": [],
                                "primary_paper": {},
                                "related_papers_summary": [],
                                "draft_report": "",
                                "draft_references": "",
                                "review_feedback": {},
                                "final_report": "",
                                "final_references": "",
                                "revision_round": 0,
                                "error": None,
                                "status_message": "Starting...",
                            }

                            # Step 1: Planner
                            state = planner_agent(state)
                            show_step("planner", state.get("status_message", ""), 10)

                            # Step 2: Search
                            state = search_agent(state)
                            show_step("search", state.get("status_message", ""), 25)

                            # Step 3: Reader
                            state = reader_agent(state)
                            show_step("reader", state.get("status_message", ""), 40)

                            # Step 4: Writer
                            state = writer_agent(state)
                            show_step("writer", state.get("status_message", ""), 55)

                            # Step 5-6: Reviewer loop
                            state = reviewer_agent(state)
                            show_step("reviewer", state.get("status_message", ""), 70)

                            rev_round = 0
                            while state.get("review_feedback", {}).get("needs_revision") and rev_round < 2:
                                rev_round += 1
                                state["revision_round"] = rev_round
                                state = writer_agent(state)
                                show_step("writer", f"🔄 Revision round {rev_round}: " + state.get("status_message", ""), 75 + rev_round * 10)
                                state = reviewer_agent(state)
                                show_step("reviewer", f"🔍 Reviewer: Score {state.get('review_feedback',{}).get('score','N/A')}/10", 85 + rev_round * 5)

                            # Finalize
                            state["final_report"] = state.get("draft_report", "")
                            state["final_references"] = state.get("draft_references", "")
                            progress_bar.progress(100, text="✅ Complete!")
                            status_text.markdown(state.get("status_message", "Done"))

                            if state.get("final_report"):
                                report_md = build_report_markdown(
                                    research_direction=state.get("research_direction", ""),
                                    primary_paper=state.get("primary_paper", {}),
                                    search_results=state.get("search_results", []),
                                    draft_report=state.get("final_report", ""),
                                    draft_references=state.get("final_references", ""),
                                    review_feedback=state.get("review_feedback", {}),
                                )
                                filepath = save_markdown_report(report_md)

                                st.divider()
                                st.subheader("📄 Results")
                                st.download_button(
                                    "Download Report (Markdown)",
                                    report_md,
                                    file_name="paper_report.md",
                                    mime="text/markdown",
                                )

                                with st.expander("Paper Analysis Review", expanded=True):
                                    st.markdown(state.get("final_report", ""))
                                with st.expander("References", expanded=False):
                                    st.text(state.get("final_references", "No references"))
                                with st.expander("Review Feedback", expanded=False):
                                    fb = state.get("review_feedback", {})
                                    if fb:
                                        st.metric("Score", f"{fb.get('score', 'N/A')}/10")
                                        for k in ["completeness", "accuracy", "structure", "suggestions"]:
                                            if fb.get(k):
                                                st.caption(f"**{k}**: {fb[k]}")
                            else:
                                st.warning("No report was generated.")
                        except Exception as e:
                            st.error(f"Pipeline error: {e}")
                            st.code(traceback.format_exc())

with tab2:
    st.subheader("Saved Reports")
    if os.path.exists(OUTPUT_DIR):
        files = sorted(os.listdir(OUTPUT_DIR), reverse=True)
        if files:
            for fname in files[:30]:
                fpath = os.path.join(OUTPUT_DIR, fname)
                st.text(fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                with st.expander(f"Preview: {fname}"):
                    st.markdown(content[:5000])
                    if len(content) > 5000:
                        st.caption("... (truncated)")
        else:
            st.caption("No saved reports yet. Run an analysis first!")
    else:
        st.caption("Output directory not found.")
