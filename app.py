import streamlit as st
import os
import traceback
from state import AgentState
from config import OUTPUT_DIR, EMAIL_RECIPIENT, validate_config
from tools.report_generator import save_markdown_report, save_pdf_report
from tools.email_sender import create_zip, send_email

st.set_page_config(page_title="Academic Learning Path", page_icon="🎓", layout="wide")

# --- 初始化会话状态 ---
if "pipeline_done" not in st.session_state:
    st.session_state.pipeline_done = False
    st.session_state.keyword = ""
    st.session_state.report = ""
    st.session_state.report_md_path = ""
    st.session_state.ranked_papers = []
    st.session_state.downloaded_papers = []
    st.session_state.email_sent = False
    st.session_state.email_msg = ""
st.title("🎓 Academic Learning Path Generator")
st.caption("AI-powered beginner learning path | Search -> Download -> Analyze -> Rank -> Write -> Email")

PROGRESS = {
    "planner": ("📋", "Planning search strategy...", 5),
    "search": ("🔍", "Searching papers on arXiv & Semantic Scholar...", 15),
    "downloader": ("⬇️", "Downloading PDFs from arXiv...", 30),
    "reader": ("📖", "Analyzing paper difficulty and content...", 45),
    "ranker": ("📊", "Ranking papers from easiest to hardest...", 65),
    "writer": ("✍️", "Writing personalized learning path...", 80),
    "email": ("📧", "Packaging and sending email...", 95),
}

tab1, tab2 = st.tabs(["🚀 Generate Path", "📂 Saved Reports"])

with tab1:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("📋 Input")
        keyword = st.text_input("Research Keyword", placeholder="e.g., Transformer, GNN, RLHF, Diffusion Model")
        st.caption("We will search for beginner-friendly papers on this topic.")
        email = st.text_input("Email (optional)", placeholder="your@email.com")
        st.caption("Receive the papers and learning path by email.")
        api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        if not api_key:
            st.warning("API Key not set. Set DEEPSEEK_API_KEY.", icon="⚠️")
        run_btn = st.button("🚀 Generate Learning Path", type="primary", use_container_width=True)

    with col2:
        st.subheader("📊 Progress")
        progress_placeholder = st.empty()

    if run_btn:
        if not keyword:
            st.error("Please enter a research keyword.")
        else:
            issues = validate_config()
            if issues:
                for issue in issues:
                    st.warning(issue)

            with progress_placeholder.container():
                st.info("Running multi-agent pipeline...")
                bar = st.progress(0, text="Starting...")
                log = st.empty()

                def step(name, msg, pct):
                    bar.progress(pct, text=PROGRESS[name][1])
                    log.info(msg)

                try:
                    from agents.planner import planner_agent
                    from agents.search import search_agent
                    from agents.downloader import downloader_agent
                    from agents.reader import reader_agent
                    from agents.ranker import ranker_agent
                    from agents.writer import writer_agent

                    state = {"research_keyword": keyword, "email_recipient": email or EMAIL_RECIPIENT}

                    # 1. Planner
                    state = planner_agent(state)
                    step("planner", state.get("status_message",""), 5)

                    # 2. Search
                    state = search_agent(state)
                    step("search", state.get("status_message",""), 15)

                    # 3. Downloader
                    state = downloader_agent(state)
                    step("downloader", state.get("status_message",""), 30)

                    # 4. Reader
                    state = reader_agent(state)
                    step("reader", state.get("status_message",""), 45)

                    # 5. Ranker
                    state = ranker_agent(state)
                    step("ranker", state.get("status_message",""), 65)

                    # 6. Writer
                    state = writer_agent(state)
                    step("writer", state.get("status_message",""), 80)

                    report = state.get("learning_path_report", "")
                    if report:
                        # 保存 Markdown 报告到本地
                        report_md_path = save_markdown_report(report, "learning_path")
                        bar.progress(100, text="Complete!")

                        # 存入会话状态，供后续预览、选择、发送
                        st.session_state.pipeline_done = True
                        st.session_state.keyword = keyword
                        st.session_state.report = report
                        st.session_state.report_md_path = report_md_path
                        st.session_state.ranked_papers = state.get("ranked_papers", [])
                        st.session_state.downloaded_papers = state.get("downloaded_papers", [])
                        st.session_state.email_sent = False
                        st.session_state.email_msg = ""

                        st.rerun()
                    else:
                        st.warning("No report generated.")
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.code(traceback.format_exc())

    # === 管道完成后：展示报告 + 论文预览 + 邮件发送 ===
    if st.session_state.pipeline_done and st.session_state.ranked_papers:
        st.divider()
        st.subheader("📊 学习路径报告")
        with st.expander("查看完整报告", expanded=True):
            st.markdown(st.session_state.report)
        st.download_button(
            "📥 下载 Markdown 报告",
            st.session_state.report,
            file_name="learning_path.md",
            mime="text/markdown",
        )

        st.divider()
        st.subheader("📄 论文预览与选择")
        st.caption("勾选你想要接收的论文，未勾选的不会打包发送。")

        # 构建 arxiv_id → downloaded_paper 的索引
        paper_by_arxiv = {}
        for dp in st.session_state.downloaded_papers:
            aid = dp.get("arxiv_id", "")
            if aid:
                paper_by_arxiv[aid] = dp

        selected_papers = []
        cols = st.columns(2)
        for i, rp in enumerate(st.session_state.ranked_papers):
            col = cols[i % 2]
            with col:
                aid = rp.get("arxiv_id", "")
                # 检查是否已下载 PDF
                has_pdf = aid in paper_by_arxiv
                local_path = paper_by_arxiv[aid]["local_path"] if has_pdf else ""

                with st.container(border=True):
                    checked = st.checkbox(
                        f"**#{i+1}** {rp['title']}",
                        value=True,
                        key=f"select_paper_{i}",
                        help=f"难度: {rp.get('difficulty_label', 'N/A')} | {rp.get('year', '')}",
                    )
                    st.caption(f"📖 {rp.get('difficulty_label', 'N/A')} ({rp.get('difficulty_score', '?')}/10) | ⏱ {rp.get('estimated_hours', '?')}h | ✍ {rp.get('authors', 'N/A')[:60]}")
                    with st.expander("详情"):
                        st.markdown(f"**学习目标:** {rp.get('learning_goal', 'N/A')}")
                        st.markdown(f"**为何在此位置:** {rp.get('reason', 'N/A')}")
                        st.markdown(f"**前置知识:** {rp.get('prerequisite', 'N/A')}")
                        if has_pdf:
                            st.markdown(f"**本地路径:** `{local_path}`")
                            st.success(f"✅ PDF 已下载 ({rp.get('page_count', '?')} 页)")
                        else:
                            st.warning("⚠ PDF 未下载")
                    if checked:
                        # 只把已下载的加入选择列表
                        if has_pdf:
                            selected_papers.append(paper_by_arxiv[aid])
                        else:
                            st.caption("⚠ 无本地 PDF，跳过")

        st.divider()
        st.subheader("📧 发送到邮箱")

        # 用户邮箱输入
        col_email, col_btn = st.columns([2, 1])
        with col_email:
            user_email = st.text_input(
                "收件人邮箱",
                value=EMAIL_RECIPIENT,
                key="email_input",
                placeholder="your@email.com",
            )
        with col_btn:
            st.caption("")  # 对齐占位

        # 汇总信息
        zip_size_est = 0
        for pp in selected_papers:
            lp = pp.get("local_path", "")
            if lp and os.path.exists(lp):
                zip_size_est += os.path.getsize(lp)
        report_md_size = os.path.getsize(st.session_state.report_md_path) if os.path.exists(st.session_state.report_md_path) else 0
        zip_size_est += report_md_size * 2  # PDF 粗略估计

        st.info(
            f"已选择 **{len(selected_papers)}** 篇论文 + 1 份 PDF 学习路径报告 | "
            f"预估压缩包大小约 **{zip_size_est / (1024*1024):.1f} MB**"
        )

        if st.button("📧 生成 PDF 并发送邮件", type="primary", key="send_email_btn"):
            if not selected_papers:
                st.warning("请至少选择一篇论文。")
            elif not user_email or "@" not in user_email:
                st.warning("请输入有效的收件人邮箱地址。")
            else:
                with st.spinner("正在生成 PDF 报告..."):
                    pdf_path = save_pdf_report(
                        st.session_state.report, "learning_path"
                    )
                    st.session_state.report_pdf_path = pdf_path
                with st.spinner("正在打包..."):
                    zip_path = create_zip(selected_papers, pdf_path)

                if zip_path is None:
                    st.error("打包失败：没有可添加的文件。")
                else:
                    keyword = st.session_state.keyword
                    subject = f"[Learning Path] {keyword} - 精选论文阅读路径（{len(selected_papers)} 篇）"
                    html_body = f"""<h2>你的学习路径: {keyword}</h2>
<p>你好！这是你选择的 <b>{len(selected_papers)} 篇论文</b> 及对应的学习路径报告。</p>
<p>附件包含：</p>
<ul>
  <li>📄 学习路径报告（PDF）</li>
  <li>📑 {len(selected_papers)} 篇精选论文 PDF</li>
</ul>
<p>祝你阅读愉快！</p>
<hr><small>由 AI Multi-Agent Learning Path System 自动生成</small>"""
                    sent, msg = send_email(subject, html_body, zip_path, user_email)
                    if sent:
                        st.session_state.email_sent = True
                        st.session_state.email_msg = msg
                        st.success(f"✅ {msg}")
                        st.balloons()
                    else:
                        st.session_state.email_sent = False
                        st.session_state.email_msg = msg
                        st.warning(f"发送失败: {msg}")
                        st.caption("报告和 zip 包已保存在本地，你也可以手动发送。")

        # 显示上次发送结果
        if st.session_state.email_msg:
            if st.session_state.email_sent:
                st.success(f"上次发送: {st.session_state.email_msg}")
            else:
                st.info(f"上次结果: {st.session_state.email_msg}")

        # 重置按钮
        if st.button("🔄 重新开始", key="reset_btn"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # === 无论文但有报告（边缘情况）===
    elif st.session_state.pipeline_done and not st.session_state.ranked_papers:
        st.warning("No papers were ranked—please try a different keyword.")
        st.markdown(st.session_state.report or "")
        if st.button("🔄 重新开始", key="reset_btn_edge"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
with tab2:
    st.subheader("Saved Reports")
    if os.path.exists(OUTPUT_DIR):
        files = sorted(os.listdir(OUTPUT_DIR), reverse=True)
        if files:
            for fn in files[:30]:
                fp = os.path.join(OUTPUT_DIR, fn)
                st.text(fn)
                if fn.endswith(".md"):
                    with open(fp, "r", encoding="utf-8") as ff:
                        content = ff.read()
                    with st.expander(f"Preview: {fn}"):
                        st.markdown(content[:5000])
                elif fn.endswith(".pdf"):
                    st.caption(f"(PDF 报告: {os.path.getsize(fp) / 1024:.1f} KB)")
        else:
            st.caption("No saved reports yet. Generate a learning path!")
    else:
        st.caption("Output directory not found.")
