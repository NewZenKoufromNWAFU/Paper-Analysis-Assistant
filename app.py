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
from i18n import get_text, get_lang_label, ZH, EN

st.set_page_config(page_title="Paper Analyzer", page_icon="📄", layout="wide")

st.markdown("""
<style>
    * { font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif; }
    .main .block-container { padding-top: 2rem; }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
        border-right: none;
    }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    [data-testid="stSidebar"] .stSelectbox label { color: #94a3b8 !important; }
    [data-testid="stSidebar"] hr { border-color: #334155; }

    .card-empty {
        background: #f8fafc;
        border: 2px dashed #e2e8f0;
        border-radius: 16px;
        padding: 48px 24px;
        text-align: center;
        color: #94a3b8;
    }

    .stButton > button {
        border-radius: 12px !important;
        font-weight: 600 !important;
        padding: 12px 24px !important;
    }

    h1 { font-weight: 700 !important; letter-spacing: -0.02em; }
    h3 { font-weight: 600 !important; }

    [data-testid="stFileUploader"] {
        border: 2px dashed #cbd5e1;
        border-radius: 16px;
        padding: 20px;
        transition: border-color 0.2s;
    }
    [data-testid="stFileUploader"]:hover { border-color: #6366f1; }

    .stProgress > div > div {
        background-color: #6366f1 !important;
        border-radius: 99px !important;
    }

    [data-testid="stExpander"] {
        border: 1px solid #e2e8f0;
        border-radius: 12px;
    }

    .pipeline-step {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 6px 14px; border-radius: 99px;
        font-size: 0.8rem; font-weight: 500;
        background: #f1f5f9; color: #475569;
        margin-right: 8px; margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

if "lang" not in st.session_state:
    st.session_state.lang = ZH

lang = st.session_state.lang

with st.sidebar:
    st.markdown("""
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;">
            <div style="width:36px;height:36px;background:#6366f1;border-radius:10px;
                        display:flex;align-items:center;justify-content:center;font-size:18px;">📄</div>
            <div style="font-weight:700;font-size:1.1rem;">Paper Analyzer</div>
        </div>
    """, unsafe_allow_html=True)

    lang = st.selectbox(
        get_text("app.lang_label", lang),
        options=[ZH, EN],
        format_func=get_lang_label,
        key="lang",
    )

    st.divider()

    with st.expander(get_text("about.title", lang)):
        st.markdown(get_text("about.description", lang))
        st.divider()
        st.markdown(get_text("about.tech", lang))
        st.divider()
        st.markdown(get_text("about.github", lang))
        st.caption(get_text("about.footer", lang))

st.markdown(f"""
    <div style="margin-bottom:24px;">
        <h1 style="margin-bottom:4px;">{get_text("app.title", lang)}</h1>
        <p style="color:#64748b;font-size:0.95rem;margin:0;">{get_text("app.subtitle", lang)}</p>
    </div>
""", unsafe_allow_html=True)

api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
if not api_key:
    with st.container(border=True):
        st.warning(get_text("api.warning", lang), icon="⚠️")
        with st.expander(get_text("api.howto_title", lang)):
            st.code("$env:DEEPSEEK_API_KEY=\"sk-your-key\"  # PowerShell", language="powershell")
            st.caption(get_text("api.get_key", lang))

tab1, tab2 = st.tabs([get_text("tab.analysis", lang), get_text("tab.history", lang)])

AGENTS = ["planner", "search", "reader", "writer", "reviewer"]
AGENT_ICONS = {"planner": "📋", "search": "🔍", "reader": "📖", "writer": "✍️", "reviewer": "🔎"}

with tab1:
    config_col, status_col = st.columns([1, 2], gap="large")

    with config_col:
        st.markdown(f"### ⚙️ {get_text('config.title', lang)}")
        direction = st.text_input(
            get_text("config.keyword_label", lang),
            placeholder=get_text("config.keyword_placeholder", lang),
            help=get_text("config.keyword_hint", lang)
        )
        uploaded_file = st.file_uploader(
            get_text("config.file_label", lang),
            type="pdf",
            help=get_text("config.file_hint", lang)
        )
        st.markdown("<br>", unsafe_allow_html=True)
        run_btn = st.button(
            get_text("config.btn_run", lang),
            type="primary",
            use_container_width=True,
        )

    with status_col:
        if not run_btn:
            steps_html = "".join(
                f"<span class=\"pipeline-step\">{AGENT_ICONS[a]} {a.capitalize()}</span>"
                for a in AGENTS
            )
            st.markdown(f"""
                <div class="card-empty">
                    <div style="font-size:3rem;margin-bottom:12px;">🚀</div>
                    <div style="font-size:1.1rem;font-weight:600;color:#334155;margin-bottom:4px;">
                        {get_text("progress.title", lang)}
                    </div>
                    <div style="font-size:0.85rem;">
                        {get_text("config.keyword_hint", lang)}
                    </div>
                    <div style="margin-top:20px;display:flex;justify-content:center;flex-wrap:wrap;">
                        {steps_html}
                    </div>
                </div>
            """, unsafe_allow_html=True)
            progress_placeholder = st.empty()
        else:
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
                    st.error(get_text(f"validate.{issue}", lang))
            else:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.read())
                    pdf_path = tmp.name
                with st.spinner(""):
                    pdf_text = parse_pdf(pdf_path)

                if not pdf_text or len(pdf_text.strip()) < 100:
                    st.error(get_text("error.empty_pdf", lang))
                else:
                    with progress_placeholder.container():
                        st.markdown(f"""
                            <div style="margin-bottom:12px;color:#64748b;font-weight:500;">
                                {get_text("progress.running", lang)}
                            </div>
                        """, unsafe_allow_html=True)

                        progress_bar = st.progress(0, text="")
                        status_text = st.empty()

                        def show_step(step_name, message, pct):
                            progress_bar.progress(pct, text=message)

                        try:
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
                                "status_message": "",
                            }

                            state = planner_agent(state)
                            show_step("planner", f"📋 {state.get('status_message', '')}", 10)

                            state = search_agent(state)
                            show_step("search", f"🔍 {state.get('status_message', '')}", 25)

                            state = reader_agent(state)
                            show_step("reader", f"📖 {state.get('status_message', '')}", 40)

                            state = writer_agent(state)
                            show_step("writer", f"✍️ {state.get('status_message', '')}", 55)

                            state = reviewer_agent(state)
                            show_step("reviewer", f"🔎 {state.get('status_message', '')}", 70)

                            rev_round = 0
                            while state.get("review_feedback", {}).get("needs_revision") and rev_round < 2:
                                rev_round += 1
                                state["revision_round"] = rev_round
                                state = writer_agent(state)
                                show_step("writer", f"✍️ {get_text('step.writer_revision', lang, round=rev_round)}", 75 + rev_round * 10)
                                state = reviewer_agent(state)
                                score = state.get("review_feedback", {}).get("score", "—")
                                show_step("reviewer", f"🔎 Reviewer: {score}/10", 85 + rev_round * 5)

                            state["final_report"] = state.get("draft_report", "")
                            state["final_references"] = state.get("draft_references", "")
                            progress_bar.progress(100, text=get_text("progress.done", lang))
                            status_text.empty()

                        except Exception as e:
                            st.error(get_text("error.pipeline", lang, error=e))
                            st.code(traceback.format_exc())
                            state = {"final_report": None}

                    if state.get("final_report"):
                        st.divider()

                        report_md = build_report_markdown(
                            research_direction=state.get("research_direction", ""),
                            primary_paper=state.get("primary_paper", {}),
                            search_results=state.get("search_results", []),
                            draft_report=state.get("final_report", ""),
                            draft_references=state.get("final_references", ""),
                            review_feedback=state.get("review_feedback", {}),
                        )
                        filepath = save_markdown_report(report_md)

                        res_left, res_right = st.columns([1, 1], gap="large")

                        with res_left:
                            st.markdown(f"### 📄 {get_text('results.title', lang)}")
                            fb = state.get("review_feedback", {})
                            score = fb.get("score", "—")
                            st.metric(label=get_text("results.expander_feedback", lang), value=f"{score}/10")
                            st.download_button(
                                get_text("results.download_btn", lang),
                                report_md,
                                file_name="paper_report.md",
                                mime="text/markdown",
                                type="primary",
                                use_container_width=True,
                            )

                        with res_right:
                            with st.container(border=True):
                                paper = state.get("primary_paper", {})
                                st.markdown(f"**📝 {paper.get('title', 'Unknown')}**")
                                st.caption(f"{paper.get('authors', '—')} · {paper.get('year', '—')}")
                                if paper.get("abstract"):
                                    st.markdown(paper["abstract"][:400] + ("…" if len(paper.get("abstract", "")) > 400 else ""))

                        with st.expander(get_text("results.expander_review", lang), expanded=True):
                            st.markdown(state.get("final_report", ""))
                        with st.expander(get_text("results.expander_refs", lang)):
                            st.text(state.get("final_references", "—"))
                        with st.expander(get_text("results.expander_feedback", lang)):
                            fb = state.get("review_feedback", {})
                            if fb:
                                st.metric("Score", f"{fb.get('score', 'N/A')}/10")
                                for k in ["completeness", "accuracy", "structure", "suggestions"]:
                                    if fb.get(k):
                                        st.caption(f"**{k.capitalize()}**: {fb[k]}")

with tab2:
    st.markdown(f"### 📚 {get_text('history.title', lang)}")

    if os.path.exists(OUTPUT_DIR):
        files = sorted(os.listdir(OUTPUT_DIR), reverse=True)
        if files:
            cols = st.columns(3)
            for idx, fname in enumerate(files[:30]):
                fpath = os.path.join(OUTPUT_DIR, fname)
                with cols[idx % 3]:
                    with st.container(border=True):
                        st.markdown(f"📄 **{fname}**")
                        with open(fpath, "r", encoding="utf-8") as f:
                            content = f.read()
                        with st.expander(get_text("history.preview", lang, name="")):
                            st.markdown(content[:2000])
                            if len(content) > 2000:
                                st.caption(get_text("history.truncated", lang))
        else:
            st.markdown(f"""
                <div class="card-empty">
                    <div style="font-size:2.5rem;">📭</div>
                    <div style="margin-top:8px;">{get_text("history.empty", lang)}</div>
                </div>
            """, unsafe_allow_html=True)
    else:
        st.caption(get_text("history.dir_missing", lang))
