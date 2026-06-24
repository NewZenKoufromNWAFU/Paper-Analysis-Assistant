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
from i18n import get_text, get_step_text, get_lang_label, ZH, EN

st.set_page_config(page_title="Paper Analyzer", page_icon="📄", layout="wide")

# Initialize language
if "lang" not in st.session_state:
    st.session_state.lang = ZH

lang = st.session_state.lang

# Sidebar language selector
with st.sidebar:
    st.selectbox(
        get_text("app.lang_label", lang),
        options=[ZH, EN],
        format_func=get_lang_label,
        key="lang",
    )
    lang = st.session_state.lang  # refresh after widget update

    st.divider()
    with st.expander(get_text("about.title", lang)):
        st.markdown(get_text("about.description", lang))
        st.markdown("---")
        st.markdown(get_text("about.tech", lang))
        st.markdown(get_text("about.github", lang))
        st.markdown("---")
        st.caption(get_text("about.footer", lang))

st.title(get_text("app.title", lang))
st.caption(get_text("app.subtitle", lang))

# API key check
api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
if not api_key:
    st.warning(get_text("api.warning", lang), icon="⚠️")
    with st.expander(get_text("api.howto_title", lang)):
        st.code('$env:DEEPSEEK_API_KEY="sk-your-key"  # PowerShell', language="powershell")
        st.caption(get_text("api.get_key", lang))

tab1, tab2 = st.tabs([get_text("tab.analysis", lang), get_text("tab.history", lang)])

PROGRESS_STEPS = {
    "planner": get_text("step.planner", lang),
    "search": get_text("step.search", lang),
    "reader": get_text("step.reader", lang),
    "writer": get_text("step.writer", lang),
    "reviewer": get_text("step.reviewer", lang),
    "finalize": get_text("step.finalize", lang),
}

with tab1:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader(get_text("config.title", lang))
        direction = st.text_input(get_text("config.keyword_label", lang), placeholder=get_text("config.keyword_placeholder", lang))
        st.caption(get_text("config.keyword_hint", lang))
        uploaded_file = st.file_uploader(get_text("config.file_label", lang), type="pdf")
        st.caption(get_text("config.file_hint", lang))
        run_btn = st.button(get_text("config.btn_run", lang), type="primary", use_container_width=True)

    with col2:
        st.subheader(get_text("progress.title", lang))
        progress_placeholder = st.empty()

    if run_btn:
        if not direction:
            st.error(get_text("error.no_keyword", lang))
        elif not uploaded_file:
            st.error(get_text("error.no_file", lang))
        else:
            issues = validate_config()
            if issues:
                for issue in issues:
                    key = f"validate.{issue}"
                    st.error(get_text(key, lang))
            else:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.read())
                    pdf_path = tmp.name
                with st.spinner("Parsing PDF..."):
                    pdf_text = parse_pdf(pdf_path)
                if not pdf_text or len(pdf_text.strip()) < 100:
                    st.error(get_text("error.empty_pdf", lang))
                else:
                    st.success(get_text("error.pdf_loaded", lang, chars=len(pdf_text)))

                    with progress_placeholder.container():
                        st.info(get_text("progress.running", lang))
                        progress_bar = st.progress(0, text=get_text("progress.starting", lang))
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
                                "status_message": get_text("progress.starting", lang),
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
                                revision_prefix = get_text("step.writer_revision", lang, round=rev_round)
                                show_step("writer", revision_prefix + state.get("status_message", ""), 75 + rev_round * 10)
                                state = reviewer_agent(state)
                                score = state.get('review_feedback', {}).get('score', 'N/A')
                                show_step("reviewer", f"🔍 Reviewer: Score {score}/10", 85 + rev_round * 5)

                            # Finalize
                            state["final_report"] = state.get("draft_report", "")
                            state["final_references"] = state.get("draft_references", "")
                            progress_bar.progress(100, text=get_text("progress.done", lang))
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
                                st.subheader(get_text("results.title", lang))
                                st.download_button(
                                    get_text("results.download_btn", lang),
                                    report_md,
                                    file_name="paper_report.md",
                                    mime="text/markdown",
                                )

                                with st.expander(get_text("results.expander_review", lang), expanded=True):
                                    st.markdown(state.get("final_report", ""))
                                with st.expander(get_text("results.expander_refs", lang), expanded=False):
                                    st.text(state.get("final_references", get_text("results.no_refs", lang)))
                                with st.expander(get_text("results.expander_feedback", lang), expanded=False):
                                    fb = state.get("review_feedback", {})
                                    if fb:
                                        st.metric("Score", f"{fb.get('score', 'N/A')}/10")
                                        for k in ["completeness", "accuracy", "structure", "suggestions"]:
                                            if fb.get(k):
                                                st.caption(f"**{k}**: {fb[k]}")
                            else:
                                st.warning(get_text("results.no_report", lang))
                        except Exception as e:
                            st.error(get_text("error.pipeline", lang, error=e))
                            st.code(traceback.format_exc())

with tab2:
    st.subheader(get_text("history.title", lang))
    if os.path.exists(OUTPUT_DIR):
        files = sorted(os.listdir(OUTPUT_DIR), reverse=True)
        if files:
            for fname in files[:30]:
                fpath = os.path.join(OUTPUT_DIR, fname)
                st.text(fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                with st.expander(get_text("history.preview", lang, name=fname)):
                    st.markdown(content[:5000])
                    if len(content) > 5000:
                        st.caption(get_text("history.truncated", lang))
        else:
            st.caption(get_text("history.empty", lang))
    else:
        st.caption(get_text("history.dir_missing", lang))
