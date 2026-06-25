import streamlit as st
import os
from datetime import datetime
from config import EMAIL_RECIPIENT
from tools.academic_search import search_papers
from agents.retriever import retrieval_agent
from state import AgentState
from tools.paper_downloader import batch_download
from tools.report_generator import save_html_report
from tools.email_sender import create_zip, send_email
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE

st.set_page_config(page_title="论文学习路径生成器", page_icon="🎓", layout="wide")

# ============================================================
# 工具函数
# ============================================================
def paper_key(paper: dict) -> str:
    return (paper.get("arxiv_id") or paper.get("paper_id") or paper.get("title", "")).strip().lower()


def truncate_abstract(text: str, max_chars: int = 200) -> str:
    if not text:
        return "(无摘要)"
    text = text.strip().replace("\n", " ")
    if len(text) <= max_chars:
        return text
    # Search backward from max_chars for a sentence-ending punctuation
    # so Chinese/English text is cut at a natural boundary, not mid-sentence.
    for i in range(max_chars - 1, max(0, max_chars - 150), -1):
        if text[i] in "。！？；.!?;":
            return text[:i + 1] + "..."
    return text[:max_chars] + "..."


def authority_stars(paper: dict) -> str:
    """Return 1-5 star rating based on venue prestige + citations.

    ⭐⭐⭐⭐⭐ — Top venue (NeurIPS/CVPR/Nature/etc) or 1000+ citations
    ⭐⭐⭐⭐   — Good venue or 500+ citations
    ⭐⭐⭐     — Published somewhere or 100+ citations
    ⭐⭐       — arXiv only, some citations
    ⭐         — arXiv only, zero citations
    """
    venue = (paper.get("venue", "") or "").lower()
    cites = paper.get("citation_count", 0) or 0

    # Top venue check
    top = {"neurips", "nips", "icml", "iclr", "cvpr", "iccv", "eccv",
           "acl", "emnlp", "naacl", "aaai", "ijcai",
           "nature", "science", "cell", "pnas",
           "osdi", "sosp", "sigmod", "vldb", "pldi", "popl",
           "chi", "sigcomm", "mobicom", "ccs", "crypto",
           "jmlr", "tpami", "ijcv", "tacl"}
    is_top = any(t in venue for t in top)

    if is_top or cites >= 1000:
        return "⭐⭐⭐⭐⭐"
    elif cites >= 500:
        return "⭐⭐⭐⭐"
    elif (venue and venue != "arxiv") or cites >= 100:
        return "⭐⭐⭐"
    elif cites >= 10:
        return "⭐⭐"
    else:
        return "⭐"


def generate_learning_path_report(papers: list, keyword: str) -> str:
    llm = ChatOpenAI(
        api_key=LLM_API_KEY, base_url=LLM_BASE_URL,
        model=LLM_MODEL, temperature=LLM_TEMPERATURE,
    )

    comparison_rows = []
    for i, pp in enumerate(papers, 1):
        comparison_rows.append(
            f"| {i} | {pp.get('title', 'N/A')[:50]} | {pp.get('year', 'N/A')} | "
            f"{pp.get('venue', 'N/A') or 'arXiv'} | {pp.get('citation_count', 0)} | "
            f"{pp.get('authors', 'N/A')[:30]} |"
        )
    comparison_table = (
        "| # | 论文 | 年份 | 期刊/会议 | 引用数 | 作者 |\n"
        "|---|------|------|-----------|--------|------|\n"
        + "\n".join(comparison_rows)
    )

    papers_list = []
    for i, pp in enumerate(papers, 1):
        papers_list.append(
            f"### 论文 {i}: {pp.get('title', 'N/A')} ({pp.get('year', 'N/A')})\n\n"
            f"- **作者:** {pp.get('authors', 'N/A')}\n"
            f"- **期刊/会议:** {pp.get('venue', 'N/A') or 'arXiv'}\n"
            f"- **引用数:** {pp.get('citation_count', 0)}\n"
            f"- **摘要:** {pp.get('abstract', '(无)')[:400]}\n"
            f"- **arXiv ID:** {pp.get('arxiv_id', 'N/A')}\n"
        )
    papers_blob = "\n---\n\n".join(papers_list)

    system = SystemMessage(content=(
        f"你是一位学术导师，正在为用户制定论文阅读路径。研究方向：{keyword}。"
        "请用中文撰写一份温暖、鼓励、结构清晰的学习路径指南。使用 Markdown 格式和 emoji。"
        "报告结构：\n"
        "1. 📌 概述：该研究方向的重要性、当前趋势、本路径的设计思路\n"
        "2. 📊 论文对比总览：包含对比表（标题、年份、期刊、引用、核心贡献）\n"
        "3. 逐篇导读：每篇论文的核心贡献、创新点、算法突破、基准数据、阅读重点\n"
        "4. 📅 建议阅读顺序 + 每篇预估时间\n"
        "5. 🚀 后续进阶建议\n"
        "请写得让初学者感到亲切、有方向感。"
    ))
    human = HumanMessage(content=(
        f"论文对比表：\n\n{comparison_table}\n\n"
        f"论文详情：\n\n{papers_blob}\n\n"
        f"请生成完整的中文学习路径指南。"
    ))
    resp = llm.invoke([system, human])
    return resp.content


# ============================================================
# 会话状态
# ============================================================
INIT = {
    "selected_papers": [],
    "search_results": [],
    "last_keyword": "",
    "search_offset": 0,
    "search_count": 5,
    "generating": False,
    "search_mode": "keyword",       # "keyword" or "agent"
    "report_ready": False,
    "html_path": "",
    "zip_path": "",
    "confirm_new_search": False,
}
if "seen_paper_keys" not in st.session_state:
    st.session_state["seen_paper_keys"] = []
for k, v in INIT.items():
    if k not in st.session_state:
        st.session_state[k] = v


def reset_all():
    for k in list(st.session_state.keys()):
        if k in INIT:
            st.session_state[k] = INIT[k]
        elif k == "seen_paper_keys":
            st.session_state[k] = []
        else:
            del st.session_state[k]


# ============================================================
# UI
# ============================================================
st.title("🎓 论文搜索 & 学习路径生成器")
st.caption("搜索论文 → 选择感兴趣的 → 生成学习路径 → 预览 → 下载 / 发送邮箱")

left, right = st.columns([1, 2])

# ==================
# 左栏
# ==================
with left:
    st.subheader("🔍 搜索论文")

    search_mode = st.radio(
        "搜索模式",
        options=["快速搜索", "深度检索 (AI Agent)"],
        index=0,
        horizontal=True,
        key="search_mode_radio",
    )
    st.session_state.search_mode = "agent" if "深度" in search_mode else "keyword"

    keyword = st.text_input(
        "关键词 / 论文标题",
        placeholder="例如：Transformer、GNN、Diffusion Model…",
        key="search_keyword",
    )

    research_interest = ""
    if st.session_state.search_mode == "agent":
        research_interest = st.text_area(
            "研究兴趣（自然语言描述）",
            placeholder=(
                "用自然语言描述你的研究兴趣，AI Agent 会自动规划搜索策略。\n"
                "例如：我对图神经网络在分子性质预测中的应用很感兴趣，\n"
                "尤其关注等变架构（equivariant architectures）的最新进展，\n"
                "希望能找到相关的综述、经典论文和最新突破。"
            ),
            key="research_interest_input",
        )

    search_count = st.slider(
        "每次搜索数量", min_value=1, max_value=10, value=5, step=1,
    )

    time_option = st.selectbox(
        "发表时间",
        options=["不限时间", "近半年", "近 1 年", "近 3 年", "自定义年份区间"],
        index=0,
    )

    year_from, year_to = None, None
    yr = datetime.now().year
    if time_option == "近半年":
        year_from = yr if datetime.now().month > 6 else yr - 1
    elif time_option == "近 1 年":
        year_from = yr - 1
    elif time_option == "近 3 年":
        year_from = yr - 3
    elif time_option == "自定义年份区间":
        c1, c2 = st.columns(2)
        with c1:
            yf = st.number_input("起始年", min_value=1900, max_value=yr, value=yr - 5, step=1)
        with c2:
            yt = st.number_input("结束年", min_value=1900, max_value=yr, value=yr, step=1)
        year_from, year_to = (yf, yt) if yf <= yt else (yt, yf)

    if st.button("🔍 搜索论文", type="primary", use_container_width=True):
        if not keyword.strip():
            st.warning("请输入关键词")
        else:
            st.session_state.last_keyword = keyword.strip()
            st.session_state.search_count = search_count
            st.session_state.search_offset = 0
            st.session_state.seen_paper_keys = []
            st.session_state.confirm_new_search = False
            if st.session_state.search_mode == "agent" and research_interest.strip():
                # ── Agent mode: plan → retrieve ──
                agent_state: AgentState = {
                    "research_interest": research_interest.strip(),
                    "research_keyword": keyword.strip() or research_interest.strip()[:30],
                    "max_total_results": search_count,
                    "search_results": [],
                }
                from agents.planner import planner_agent
                with st.spinner("AI Agent 正在规划搜索策略…"):
                    agent_state = planner_agent(agent_state)
                    plan = agent_state.get("search_plan", {})
                    st.info(
                        f"**搜索计划**：{plan.get('core_topic', 'N/A')}\n\n"
                        + "\n".join(
                            f"- [{s['type']}] {s['query']} ({s.get('reason','')})"
                            for s in plan.get("strategies", [])
                        )
                    )
                with st.spinner(f"正在执行 {len(plan.get('strategies',[]))} 条搜索策略…"):
                    agent_state = retrieval_agent(agent_state)
                results = agent_state.get("search_results", [])
                # Warn if every result has 0 citations (all from arXiv — Semantic Scholar down)
                if results and all(r.get("citation_count", 0) == 0 for r in results):
                    st.warning(
                        "⚠️ Semantic Scholar API 请求全部被限速（HTTP 429），"
                        "当前结果均来自 arXiv，引用数为 0。请等待 30 秒后重试。"
                    )
                # Fallback: if agent returned nothing, try keyword mode automatically
                if not results and keyword.strip():
                    st.warning("Agent 模式未找到结果，自动回退到关键词快速搜索…")
                    with st.spinner(f"关键词搜索「{keyword}」…"):
                        results = search_papers(
                            keyword.strip(), count=search_count,
                            year_from=year_from, year_to=year_to,
                            authoritative_only=True,
                        )
            else:
                # ── Keyword mode (original) ──
                with st.spinner(f"正在搜索「{keyword}」…"):
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

    # 换一批 / 重新搜索
    if st.session_state.search_results:
        st.divider()
        cr, cn = st.columns(2)
        with cr:
            if st.button("🔀 换一批", use_container_width=True,
                         help="同一关键词翻页搜索下一批，不会重复"):
                st.session_state.search_offset += st.session_state.search_count
                with st.spinner("正在搜索下一批…"):
                    results = search_papers(
                        st.session_state.last_keyword,
                        count=st.session_state.search_count,
                        year_from=year_from,
                        year_to=year_to,
                        offset=st.session_state.search_offset,
                        authoritative_only=True,
                        exclude_keys=set(st.session_state.seen_paper_keys),
                    )
                nk = [paper_key(r) for r in results]
                st.session_state.seen_paper_keys = st.session_state.seen_paper_keys + nk
                st.session_state.search_results = results
                st.rerun()
        with cn:
            if st.button("🔄 重新搜索", use_container_width=True,
                         help="清空当前结果，可换关键词或参数重新搜索"):
                if st.session_state.report_ready:
                    st.session_state.confirm_new_search = True
                else:
                    st.session_state.search_results = []
                    st.session_state.seen_paper_keys = []
                st.rerun()

    st.divider()

    # 已选论文篮
    st.subheader(f"📋 已选论文（{len(st.session_state.selected_papers)} 篇）")
    if not st.session_state.selected_papers:
        st.caption("暂无已选论文，在右侧搜索结果中点击「+ 选择」添加。")
    else:
        for i, pp in enumerate(st.session_state.selected_papers):
            ct, cx = st.columns([5, 1])
            with ct:
                ts = pp["title"][:50] + ("…" if len(pp["title"]) > 50 else "")
                st.markdown(f"**{i+1}.** {ts}")
                st.caption(f"{pp.get('year','?')} | {pp.get('authors','')[:30]}")
            with cx:
                if st.button("❌", key=f"remove_{i}", help="移除此论文"):
                    st.session_state.selected_papers.pop(i)
                    st.rerun()

    # 生成按钮
    if len(st.session_state.selected_papers) > 0:
        st.divider()
        if st.button("✅ 完成选择，生成学习路径", type="primary", use_container_width=True):
            st.session_state.generating = True
            st.session_state.confirm_new_search = False
            st.rerun()


# ==================
# 右栏
# ==================
with right:

    # --- 确认重新搜索 ---
    if st.session_state.confirm_new_search:
        st.warning(
            "确定要开始新一轮搜索吗？将清空已生成的学习路径报告和所有已选论文。"
        )
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("确定，重新开始", type="primary", use_container_width=True):
                reset_all()
                st.rerun()
        with cc2:
            if st.button("取消", use_container_width=True):
                st.session_state.confirm_new_search = False
                st.rerun()

    # --- 阶段 2：正在生成报告 ---
    elif st.session_state.generating:
        papers = st.session_state.selected_papers
        if not papers:
            st.warning("没有已选论文，请先搜索并选择。")
            st.session_state.generating = False
        else:
            st.subheader("正在生成学习路径…")
            progress = st.progress(0, text="准备中…")

            progress.progress(20, text="正在下载论文 PDF…")
            downloaded = batch_download(papers, max_workers=5)

            progress.progress(50, text="AI 正在撰写学习路径报告…")
            kw = st.session_state.last_keyword or "学术论文"
            report_md = generate_learning_path_report(downloaded, kw)

            progress.progress(80, text="正在生成 HTML 报告…")
            html_path = save_html_report(report_md, "learning_path")

            progress.progress(95, text="正在打包…")
            zip_path = create_zip(downloaded, html_path)

            progress.progress(100, text="完成！")

            st.session_state.generating = False
            st.session_state.report_ready = True
            st.session_state.html_path = html_path
            st.session_state.zip_path = zip_path
            st.session_state.report_md = report_md
            st.session_state.downloaded = downloaded
            st.rerun()

    # --- 阶段 3：预览 + 下载 / 发送邮箱 ---
    elif st.session_state.report_ready:
        st.subheader("学习路径已生成！")
        n = len(st.session_state.get("downloaded", []))
        st.success(f"共 {n} 篇论文 + 1 份 HTML 学习路径报告（浏览器打开，Ctrl+P 可另存 PDF）")

        with st.expander("预览学习路径报告", expanded=True):
            st.markdown(st.session_state.report_md)

        st.divider()

        st.subheader("下载 & 发送邮箱")
        c_dl, c_send = st.columns(2)
        with c_dl:
            with open(st.session_state.zip_path, "rb") as f:
                st.download_button(
                    "下载全部（论文 + HTML 报告）",
                    data=f,
                    file_name=os.path.basename(st.session_state.zip_path),
                    mime="application/zip",
                    use_container_width=True,
                )
        with c_send:
            send_to = st.text_input(
                "收件人邮箱", value=EMAIL_RECIPIENT, key="send_email_input",
            )
            if st.button("发送到邮箱", type="primary", use_container_width=True):
                with st.spinner("正在发送…"):
                    kw = st.session_state.last_keyword
                    subject = f"[学习路径] {kw}（{n} 篇论文）"
                    html_body = (
                        f"<h2>你的学习路径</h2>"
                        f"<p>这是你选择的 <b>{n} 篇论文</b> 及 HTML 学习路径报告（浏览器打开即可查看，Ctrl+P 另存 PDF）。</p>"
                        f"<p>祝你阅读愉快！</p>"
                        f"<hr><small>由论文学习路径生成器自动生成</small>"
                    )
                    sent, msg = send_email(
                        subject, html_body, st.session_state.zip_path, send_to
                    )
                    if sent:
                        st.success(f"已发送: {msg}")
                        st.balloons()
                    else:
                        st.warning(f"发送失败: {msg}")

    # --- 阶段 1：展示搜索结果 ---
    elif st.session_state.search_results:
        results = st.session_state.search_results
        st.subheader(
            f"搜索结果 —「{st.session_state.last_keyword}」"
            f"（{len(results)} 篇）"
        )

        if len(results) == 0:
            st.warning("未找到匹配的论文，请尝试更换关键词或放宽时间范围。")

        selected_ids = {paper_key(p) for p in st.session_state.selected_papers}

        for i, paper in enumerate(results):
            pid = paper_key(paper)
            selected = pid in selected_ids

            with st.container(border=True):
                cm, cb = st.columns([6, 1])
                with cm:
                    st.markdown(f"### {i+1}. {paper['title']}")
                    st.caption(
                        f"作者: {paper.get('authors', 'N/A')}  |  "
                        f"年份: {paper.get('year', 'N/A')}  |  "
                        f"期刊: {paper.get('venue', 'N/A') or '未知'}"
                    )
                    stars = authority_stars(paper)
                    st.caption(
                        f"权威性: {stars}  |  引用: {paper.get('citation_count', 0)} 次"
                    )
                    st.markdown(truncate_abstract(paper.get("abstract", "")))
                    aid = paper.get("arxiv_id", "")
                    if aid:
                        st.markdown(f"[arXiv: {aid}](https://arxiv.org/abs/{aid})")
                with cb:
                    if selected:
                        st.success("已选")
                        if st.button("取消", key=f"desel_{i}"):
                            st.session_state.selected_papers = [
                                p for p in st.session_state.selected_papers
                                if paper_key(p) != pid
                            ]
                            st.rerun()
                    else:
                        if st.button("+ 选择", key=f"sel_{i}"):
                            st.session_state.selected_papers.append(paper)
                            st.rerun()

    # --- 阶段 0：空状态 ---
    else:
        st.info("在左侧输入关键词并点击搜索，开始探索论文吧！")
        with st.expander("使用说明"):
            st.markdown("""
            1. **输入关键词** — 在左侧输入你感兴趣的研究方向或论文标题
            2. **设置搜索参数** — 选择返回数量和发表时间范围
            3. **浏览结果** — 在右侧查看论文标题、作者、摘要、权威性
            4. **选择论文** — 点击「+ 选择」将论文加入已选篮
            5. **多次搜索** — 可换关键词多次搜索，已选论文会累积
            6. **生成学习路径** — 点击「完成选择」，AI 自动生成 HTML 学习路径
            7. **下载 / 发送** — 下载到本地，或一键发送到邮箱
            """)
