import streamlit as st
import os
from datetime import datetime
from config import EMAIL_RECIPIENT
from tools.academic_search import search_papers
from tools.paper_downloader import batch_download
from tools.report_generator import save_pdf_report
from tools.email_sender import create_zip, send_email
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE

st.set_page_config(page_title="Paper Learning Path", page_icon="🎓", layout="wide")

# ============================================================
# 辅助函数
# ============================================================
def paper_key(paper: dict) -> str:
    """Generate unique ID for a paper (arxiv_id >> paper_id >> title)."""
    return (paper.get("arxiv_id") or paper.get("paper_id") or paper.get("title", "")).strip().lower()


def truncate_abstract(text: str, max_chars: int = 150) -> str:
    if not text:
        return "(无摘要)"
    text = text.strip().replace("\n", " ")
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."


def infer_authority(paper: dict) -> str:
    cites = paper.get("citation_count", 0) or 0
    if cites >= 1000:
        return "[极高]"
    elif cites >= 500:
        return "[很高]"
    elif cites >= 100:
        return "[较高]"
    elif cites >= 10:
        return "[一般]"
    else:
        return "[新/低引用]"


def generate_learning_path_report(papers: list, keyword: str) -> str:
    """Generate a learning path Markdown report with paper comparison table."""
    llm = ChatOpenAI(
        api_key=LLM_API_KEY, base_url=LLM_BASE_URL,
        model=LLM_MODEL, temperature=LLM_TEMPERATURE,
    )

    # Build comparison table
    comparison_rows = []
    for i, pp in enumerate(papers, 1):
        comparison_rows.append(
            f"| {i} | {pp.get('title', 'N/A')[:50]} | {pp.get('year', 'N/A')} | "
            f"{pp.get('venue', 'N/A') or 'arXiv'} | {pp.get('citation_count', 0)} | "
            f"{pp.get('authors', 'N/A')[:30]} |"
        )
    comparison_table = (
        "| # | Paper | Year | Venue | Citations | Authors |\n"
        "|---|-------|------|-------|-----------|--------|\n"
        + "\n".join(comparison_rows)
    )

    papers_list = []
    for i, pp in enumerate(papers, 1):
        papers_list.append(
            f"### Paper {i}: {pp.get('title', 'N/A')} ({pp.get('year', 'N/A')})\n\n"
            f"- **Authors:** {pp.get('authors', 'N/A')}\n"
            f"- **Venue:** {pp.get('venue', 'N/A') or 'arXiv'}\n"
            f"- **Citations:** {pp.get('citation_count', 0)}\n"
            f"- **Abstract:** {pp.get('abstract', '(none)')[:400]}\n"
            f"- **arXiv ID:** {pp.get('arxiv_id', 'N/A')}\n"
        )
    papers_blob = "\n---\n\n".join(papers_list)

    system = SystemMessage(content=(
        f"You are an academic mentor creating a learning path. Research topic: {keyword}. "
        "Write in Chinese. Use Markdown with emoji. Structure:\n"
        "1. Overview of the research field, its importance, current trends, and the design rationale for this learning path\n"
        "2. Paper comparison overview table showing title, year, venue, citations, and core contributions for each paper\n"
        "3. For each paper: core contributions, innovations, algorithm breakthroughs, benchmark results, why it is worth reading, and practical reading tips\n"
        "4. Suggested reading order with estimated time per paper\n"
        "5. Next steps after completing the path (advanced directions, recommended tools/codebases/datasets)\n"
        "Make it warm, encouraging, and beginner-friendly."
    ))
    human = HumanMessage(content=(
        f"Paper comparison table:\n\n{comparison_table}\n\n"
        f"Paper details:\n\n{papers_blob}\n\n"
        f"Please generate a complete Chinese learning path guide."
    ))
    resp = llm.invoke([system, human])
    return resp.content


# ============================================================
# 会话状态初始化
# ============================================================
DEFAULTS = {
    "selected_papers": [],
    "search_results": [],
    "last_keyword": "",
    "search_offset": 0,
    "search_count": 5,
    "generating": False,
    "report_ready": False,
    "pdf_path": "",
    "zip_path": "",
}
if "seen_paper_keys" not in st.session_state:
    st.session_state["seen_paper_keys"] = []
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ============================================================
# UI
# ============================================================
st.title("🎓 论文搜索 & 学习路径生成器")
st.caption("搜索论文 → 选择感兴趣的 → 生成学习路径 PDF → 预览 → 下载 / 发送邮箱")

left, right = st.columns([1, 2])

# ==================
# 左栏 - 搜索表单
# ==================
with left:
    st.subheader("🔍 搜索论文")

    keyword = st.text_input(
        "关键词 / 论文标题",
        placeholder="e.g., Transformer, GNN, Diffusion Model...",
        key="search_keyword",
    )

    search_count = st.slider(
        "搜索数量", min_value=1, max_value=10, value=5, step=1,
        help="每次搜索返回的论文数量",
    )

    time_option = st.selectbox(
        "发表时间",
        options=["不限时间", "近半年", "近 1 年", "近 3 年", "自定义年份区间"],
        index=0,
    )

    year_from, year_to = None, None
    current_year = datetime.now().year
    if time_option == "近半年":
        year_from = current_year if datetime.now().month > 6 else current_year - 1
    elif time_option == "近 1 年":
        year_from = current_year - 1
    elif time_option == "近 3 年":
        year_from = current_year - 3
    elif time_option == "自定义年份区间":
        c1, c2 = st.columns(2)
        with c1:
            yf = st.number_input("Start Year", min_value=1900, max_value=current_year, value=current_year - 5, step=1)
        with c2:
            yt = st.number_input("End Year", min_value=1900, max_value=current_year, value=current_year, step=1)
        year_from, year_to = (yf, yt) if yf <= yt else (yt, yf)

    if st.button("🔍 搜索论文", type="primary", use_container_width=True):
        if not keyword.strip():
            st.warning("Please enter a keyword")
        else:
            st.session_state.last_keyword = keyword.strip()
            st.session_state.search_count = search_count
            st.session_state.search_offset = 0
            st.session_state.seen_paper_keys = []
            with st.spinner(f"Searching '{keyword}' ..."):
                results = search_papers(
                    keyword.strip(),
                    count=search_count,
                    year_from=year_from,
                    year_to=year_to,
                    authoritative_only=True,
                )
            st.session_state.seen_paper_keys = [paper_key(r) for r in results]
            st.session_state.search_results = results
            st.rerun()

    # Refresh / New search
    if st.session_state.search_results:
        st.divider()
        cr, cn = st.columns(2)
        with cr:
            if st.button("🔀 Refresh", use_container_width=True,
                         help="Same keyword, next batch (no duplicates)"):
                st.session_state.search_offset += st.session_state.search_count
                with st.spinner("Searching next batch..."):
                    results = search_papers(
                        st.session_state.last_keyword,
                        count=st.session_state.search_count,
                        year_from=year_from,
                        year_to=year_to,
                        offset=st.session_state.search_offset,
                        authoritative_only=True,
                        exclude_keys=set(st.session_state.seen_paper_keys),
                    )
                new_keys = [paper_key(r) for r in results]
                st.session_state.seen_paper_keys = st.session_state.seen_paper_keys + new_keys
                st.session_state.search_results = results
                st.rerun()
        with cn:
            if st.button("🔄 New Search", use_container_width=True):
                st.session_state.search_results = []
                st.session_state.seen_paper_keys = []
                st.rerun()

    st.divider()

    # Selected papers basket
    st.subheader(f"Selected Papers ({len(st.session_state.selected_papers)})")
    if not st.session_state.selected_papers:
        st.caption("No papers selected yet. Click [+] in search results to add.")
    else:
        for i, pp in enumerate(st.session_state.selected_papers):
            ct, cx = st.columns([5, 1])
            with ct:
                ts = pp["title"][:50] + ("..." if len(pp["title"]) > 50 else "")
                st.markdown(f"**{i+1}.** {ts}")
                st.caption(f"{pp.get('year','?')} | {pp.get('authors','')[:30]}")
            with cx:
                if st.button("X", key=f"remove_{i}", help="Remove this paper"):
                    st.session_state.selected_papers.pop(i)
                    st.rerun()

    # Generate button
    if len(st.session_state.selected_papers) > 0:
        st.divider()
        if st.button("✅ Done selecting - Generate Learning Path", type="primary", use_container_width=True):
            st.session_state.generating = True
            st.rerun()


# ==================
# 右栏
# ==================
with right:

    # --- Stage 2: Generating report ---
    if st.session_state.generating:
        papers = st.session_state.selected_papers
        if not papers:
            st.warning("No papers selected.")
            st.session_state.generating = False
        else:
            st.subheader("Generating Learning Path...")
            progress = st.progress(0, text="Downloading PDFs...")

            progress.progress(20, text="Downloading paper PDFs...")
            downloaded = batch_download(papers, max_workers=5)

            progress.progress(50, text="AI generating learning path report...")
            keyword = st.session_state.last_keyword or "Academic Papers"
            report_md = generate_learning_path_report(downloaded, keyword)

            progress.progress(80, text="Generating PDF report...")
            pdf_path = save_pdf_report(report_md, "learning_path")

            progress.progress(95, text="Packaging...")
            zip_path = create_zip(downloaded, pdf_path)

            progress.progress(100, text="Done!")

            st.session_state.generating = False
            st.session_state.report_ready = True
            st.session_state.pdf_path = pdf_path
            st.session_state.zip_path = zip_path
            st.session_state.report_md = report_md
            st.session_state.downloaded = downloaded
            st.rerun()

    # --- Stage 3: Preview + Download / Email ---
    elif st.session_state.report_ready:
        st.subheader("Learning Path Report")
        st.success(f"{len(st.session_state.get('downloaded', []))} papers + PDF report ready")

        # Preview the report
        with st.expander("Preview Learning Path Report", expanded=True):
            st.markdown(st.session_state.report_md)

        st.divider()

        # Option A: Download to local
        st.subheader("Download to Local")
        st.caption("Click below to download. Your browser will prompt you to choose where to save.")
        with open(st.session_state.zip_path, "rb") as f:
            st.download_button(
                "Download All (Papers + PDF Report)",
                data=f,
                file_name=os.path.basename(st.session_state.zip_path),
                mime="application/zip",
                use_container_width=True,
            )

        st.divider()

        # Option B: Download + Send to email
        st.subheader("Download & Send to Email")
        send_email_addr = st.text_input(
            "Recipient Email", value=EMAIL_RECIPIENT, key="send_email_input",
        )
        c_dl, c_send = st.columns(2)
        with c_dl:
            with open(st.session_state.zip_path, "rb") as f:
                st.download_button(
                    "Download to Local",
                    data=f,
                    file_name=os.path.basename(st.session_state.zip_path),
                    mime="application/zip",
                    use_container_width=True,
                    key="dl2",
                )
        with c_send:
            if st.button("Send to Email", type="primary", use_container_width=True):
                with st.spinner("Sending..."):
                    kw = st.session_state.last_keyword
                    n = len(st.session_state.get("downloaded", []))
                    subject = f"[Learning Path] {kw} ({n} papers)"
                    html_body = (
                        f"<h2>Your Learning Path</h2>"
                        f"<p>Here is your learning path for <b>{kw}</b> with <b>{n} papers</b> and the PDF report.</p>"
                        f"<p>Happy reading!</p>"
                        f"<hr><small>Generated by Paper Learning Path Generator</small>"
                    )
                    sent, msg = send_email(subject, html_body, st.session_state.zip_path, send_email_addr)
                    if sent:
                        st.success(f"Sent: {msg}")
                        st.balloons()
                    else:
                        st.warning(f"Failed: {msg}")

        st.divider()
        if st.button("Start New Search"):
            for key in list(st.session_state.keys()):
                st.session_state[key] = DEFAULTS.get(key, [])
            st.rerun()

    # --- Stage 1: Show search results ---
    elif st.session_state.search_results:
        st.subheader(f"Search Results - \"{st.session_state.last_keyword}\" ({len(st.session_state.search_results)} papers)")

        selected_ids = {paper_key(p) for p in st.session_state.selected_papers}

        for i, paper in enumerate(st.session_state.search_results):
            pid = paper_key(paper)
            already_selected = pid in selected_ids

            with st.container(border=True):
                cm, cb = st.columns([6, 1])
                with cm:
                    st.markdown(f"### {i+1}. {paper['title']}")
                    st.caption(
                        f"Authors: {paper.get('authors', 'N/A')}  |  "
                        f"Year: {paper.get('year', 'N/A')}  |  "
                        f"Venue: {paper.get('venue', 'N/A') or 'Unknown'}"
                    )
                    auth = infer_authority(paper)
                    st.caption(f"Authority: {auth}  |  Citations: {paper.get('citation_count', 0)}")
                    st.markdown(f"{truncate_abstract(paper.get('abstract', ''), 150)}")
                    aid = paper.get("arxiv_id", "")
                    if aid:
                        st.markdown(f"[arXiv: {aid}](https://arxiv.org/abs/{aid})")
                with cb:
                    if already_selected:
                        st.success("Selected")
                        if st.button("Undo", key=f"desel_{i}"):
                            st.session_state.selected_papers = [
                                p for p in st.session_state.selected_papers
                                if paper_key(p) != pid
                            ]
                            st.rerun()
                    else:
                        if st.button("+ Select", key=f"sel_{i}"):
                            st.session_state.selected_papers.append(paper)
                            st.rerun()

    # --- Stage 0: Empty ---
    else:
        st.info("Enter a keyword on the left and click Search to begin!")
        with st.expander("How to use"):
            st.markdown("""
            1. **Type a keyword** - your research topic or paper title
            2. **Set search parameters** - result count and time range
            3. **Browse results** - view title, authors, abstract, authority
            4. **Select papers** - click [+ Select] to add to your basket
            5. **Search again** - change keywords, selections accumulate
            6. **Generate** - click [Done selecting] to create PDF learning path
            7. **Download or Send** - save locally or email the package
            """)
