import streamlit as st
import os
from datetime import datetime
from config import EMAIL_RECIPIENT
from tools.academic_search import search_papers
from tools.paper_downloader import batch_download
from tools.report_generator import save_html_report
from tools.email_sender import create_zip, send_email
from tools.paper_validator import batch_enrich, paper_tags
from tools.auth import (
    register, login, bind_email, update_profile,
    save_search_history, get_search_history,
    save_report, get_reports,
    subscribe, unsubscribe, get_subscriptions,
)
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE
from agents.retriever import retrieval_agent
from agents.planner import planner_agent

st.set_page_config(page_title="论文学习路径生成器", page_icon="🎓", layout="wide")

# ============================================================
# 会话状态初始化
# ============================================================
if "user" not in st.session_state:
    st.session_state.user = None           # None=游客, dict=注册用户
if "page" not in st.session_state:
    st.session_state.page = "login"        # login | main
if "show_bind_email" not in st.session_state:
    st.session_state.show_bind_email = False

INIT_MAIN = {
    "selected_papers": [],
    "search_results": [],
    "last_keyword": "",
    "search_offset": 0,
    "search_count": 5,
    "search_mode": "keyword",       # "keyword" or "agent"
    "generating": False,
    "download_only": False,
    "report_ready": False,
    "html_path": "",
    "zip_path": "",
    "confirm_new_search": False,
    "sub_keyword": "",
}
if "seen_paper_keys" not in st.session_state:
    st.session_state.seen_paper_keys = []
for k, v in INIT_MAIN.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# 工具函数
# ============================================================
def paper_key(paper: dict) -> str:
    return (paper.get("arxiv_id") or paper.get("paper_id") or paper.get("title", "")).strip().lower()

def truncate_abstract(text: str, max_chars: int = 300) -> str:
    if not text: return "(无摘要)"
    text = text.strip().replace("\n", " ")
    if len(text) <= max_chars: return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."

def generate_learning_path_report(papers: list, keyword: str) -> str:
    llm = ChatOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL, temperature=LLM_TEMPERATURE)
    comparison_rows = []
    for i, pp in enumerate(papers, 1):
        real_v = pp.get("real_venue", "") or pp.get("venue", "N/A") or "arXiv"
        comparison_rows.append(
            f"| {i} | {pp.get('title', 'N/A')[:50]} | {pp.get('real_year', pp.get('year', 'N/A'))} | "
            f"{real_v} | {pp.get('citation_count', 0)} | {pp.get('authors', 'N/A')[:30]} |"
        )
    comparison_table = ("| # | 论文 | 年份 | 期刊/会议 | 引用数 | 作者 |\n"
                        "|---|------|------|-----------|--------|------|\n" + "\n".join(comparison_rows))
    papers_list = []
    for i, pp in enumerate(papers, 1):
        real_v = pp.get("real_venue", "") or pp.get("venue", "N/A") or "arXiv"
        papers_list.append(
            f"### 论文 {i}: {pp.get('title', 'N/A')} ({pp.get('real_year', pp.get('year', 'N/A'))})\n\n"
            f"- **作者:** {pp.get('authors', 'N/A')}\n- **期刊/会议:** {real_v}\n"
            f"- **引用数:** {pp.get('citation_count', 0)}\n- **摘要:** {pp.get('abstract', '(无)')[:400]}\n"
            f"- **arXiv ID:** {pp.get('arxiv_id', 'N/A')}\n"
        )
    papers_blob = "\n---\n\n".join(papers_list)
    system = SystemMessage(content=(
        f"你是一位学术导师，研究方向：{keyword}。请用中文撰写一份学习路径指南。使用 Markdown 和 emoji。"
        "结构：1.概述 2.论文对比总览 3.逐篇导读 4.阅读顺序建议 5.进阶建议。"
    ))
    human = HumanMessage(content=f"论文对比表：\n\n{comparison_table}\n\n论文详情：\n\n{papers_blob}\n\n请生成中文学习路径指南。")
    return llm.invoke([system, human]).content

def reset_main():
    for k in list(st.session_state.keys()):
        if k in INIT_MAIN: st.session_state[k] = INIT_MAIN[k]
        elif k == "seen_paper_keys": st.session_state[k] = []
        elif k not in ("user", "page", "show_bind_email"): del st.session_state[k]

def logout():
    st.session_state.user = None
    st.session_state.page = "login"
    reset_main()
    st.rerun()


# ============================================================
# === 登录/注册页面 ===
# ============================================================
if st.session_state.page == "login":
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        st.title("🎓 论文学习路径生成器")
        st.caption("搜索论文 → 选择 → 生成学习路径 → 下载/发送邮箱")

        tab_login, tab_reg = st.tabs(["登录", "注册"])

        with tab_login:
            st.subheader("账号登录")
            login_acc = st.text_input("手机号 / 邮箱", key="login_acc", placeholder="请输入手机号或邮箱")
            login_pw = st.text_input("密码", type="password", key="login_pw", placeholder="请输入密码")
            cl1, cl2 = st.columns(2)
            with cl1:
                if st.button("登录", type="primary", use_container_width=True):
                    ok, msg, user = login(login_acc, login_pw)
                    if ok:
                        st.session_state.user = user
                        st.session_state.page = "main"
                        st.session_state.show_bind_email = (not user.get("email"))
                        st.rerun()
                    else:
                        st.error(msg)
            with cl2:
                if st.button("游客访问", use_container_width=True):
                    st.session_state.user = None
                    st.session_state.page = "main"
                    st.rerun()

        with tab_reg:
            st.subheader("注册新账号")
            reg_acc = st.text_input("手机号（或邮箱）", key="reg_acc", placeholder="请输入手机号或邮箱")
            reg_pw = st.text_input("设置密码 (6位以上)", type="password", key="reg_pw")
            reg_role = st.selectbox("学术身份（可选，有助于精准推荐论文）",
                                     options=["暂不选择", "本科", "硕士", "博士", "博士后", "教师/研究员"],
                                     index=0, key="reg_role")
            if st.button("注册", type="primary", use_container_width=True):
                ok, msg, user = register(reg_acc, reg_pw)
                if ok and reg_role != "暂不选择":
                    update_profile(user["id"], role=reg_role)
                    user["role"] = reg_role
                    st.session_state.user = user
                if ok:
                    st.session_state.user = user
                    st.session_state.page = "main"
                    st.session_state.show_bind_email = True
                    st.success("注册成功！建议绑定邮箱以使用更多功能。")
                    st.rerun()
                else:
                    st.error(msg)

        st.divider()
        st.caption("游客可直接访问，但不会保存搜索历史和报告记录。")

    st.stop()  # Don't render main page when on login page


# ============================================================
# === 主页面 ===
# ============================================================
user = st.session_state.user
is_guest = user is None

# ---- 顶部用户栏 ----
with st.container():
    cu1, cu2, cu3, cu4, cu5 = st.columns([3, 1, 1, 1, 1])
    with cu1:
        if is_guest:
            st.markdown("👤 **游客模式** — 搜索和报告不会被保存")
        else:
            nn = user.get("nickname", "") or user.get("phone", "") or user.get("email", "") or "用户"
            role = user.get("role", "")
            role_text = f"🎓 {role}" if role else ""
            st.markdown(f"👤 **{nn}** {role_text} | 📱 {user.get('phone','未绑定')} | 📧 {user.get('email','未绑定')}")
    with cu2:
        if not is_guest and not user.get("email") and st.button("📧 绑定邮箱", use_container_width=True):
            st.session_state.show_bind_email = True
    with cu3:
        if not is_guest and st.button("✏️ 个人信息", use_container_width=True):
            st.session_state.show_profile = not st.session_state.get("show_profile", False)
    with cu4:
        if not is_guest and st.button("📋 历史", use_container_width=True):
            st.session_state.show_history = not st.session_state.get("show_history", False)
    with cu5:
        if not is_guest:
            if st.button("🚪 退出", use_container_width=True):
                logout()

# ---- 个人信息编辑 ----
if st.session_state.get("show_profile") and not is_guest:
    with st.expander("✏️ 编辑个人信息", expanded=True):
        new_nick = st.text_input("用户名", value=user.get("nickname", ""), key="edit_nick")
        new_role = st.selectbox("学术身份", options=["", "本科", "硕士", "博士", "博士后", "教师/研究员"],
                                index=(["", "本科", "硕士", "博士", "博士后", "教师/研究员"].index(user.get("role", "")) if user.get("role", "") in ["本科", "硕士", "博士", "博士后", "教师/研究员"] else 0),
                                key="edit_role")
        c_save, c_close = st.columns(2)
        with c_save:
            if st.button("保存", use_container_width=True):
                ok, msg, updated = update_profile(user["id"], nickname=new_nick, role=new_role)
                if ok:
                    st.session_state.user = updated
                    st.success(msg); st.rerun()
                else:
                    st.error(msg)
        with c_close:
            if st.button("关闭", use_container_width=True):
                st.session_state.show_profile = False; st.rerun()

# ---- 绑定邮箱弹窗 ----
if st.session_state.show_bind_email and not is_guest:
    with st.expander("📧 绑定邮箱（可选，用于接收论文推送和报告）", expanded=True):
        be = st.text_input("输入邮箱地址", key="bind_email_input", placeholder="your@email.com")
        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("确认绑定", use_container_width=True):
                ok, msg = bind_email(user["id"], be)
                if ok:
                    st.session_state.user["email"] = be
                    st.session_state.show_bind_email = False
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        with bc2:
            if st.button("以后再说", use_container_width=True):
                st.session_state.show_bind_email = False
                st.rerun()

# ---- 历史记录 ----
if st.session_state.get("show_history") and not is_guest:
    with st.expander("📋 历史记录", expanded=True):
        th1, th2 = st.tabs(["搜索历史", "已生成报告"])
        with th1:
            history = get_search_history(user["id"])
            if history:
                for h in history:
                    st.caption(f"🔍 {h['keyword']} — {h['created_at']}")
            else:
                st.caption("暂无搜索记录")
        with th2:
            reports = get_reports(user["id"])
            if reports:
                for r in reports:
                    st.caption(f"📄 {r['keyword']} — {r['paper_count']}篇 — {r['created_at']}")
            else:
                st.caption("暂无报告记录")
        if st.button("关闭历史", use_container_width=True):
            st.session_state.show_history = False
            st.rerun()

st.divider()

# ============================================================
# 主界面（搜索 + 结果 + 生成）
# ============================================================
left, right = st.columns([1, 2])

# ========== 左栏 ==========
with left:
    st.subheader("🔍 搜索论文")

    search_mode = st.radio(
        "搜索模式",
        options=["快速搜索", "深度检索 (AI Agent)"],
        index=0, horizontal=True, key="search_mode_radio",
        label_visibility="collapsed",
    )
    st.session_state.search_mode = "agent" if "深度" in search_mode else "keyword"
    st.caption(f"当前模式：{'🧠 AI Agent 智能规划' if st.session_state.search_mode == 'agent' else '⚡ 快速关键词搜索'}")

    keyword = st.text_input("关键词 / 论文标题", placeholder="例如：Transformer、GNN…", key="search_keyword")

    research_interest = ""
    if st.session_state.search_mode == "agent":
        research_interest = st.text_area(
            "研究兴趣（自然语言描述）",
            placeholder="用自然语言描述你的研究兴趣，AI Agent 自动规划搜索策略。\n例如：我对图神经网络在分子性质预测中的应用很感兴趣，尤其关注等变架构…",
            key="research_interest_input",
        )

    search_count = st.slider("每次搜索数量", min_value=1, max_value=10, value=5, step=1)
    time_option = st.selectbox("发表时间", options=["不限时间", "近半年", "近 1 年", "近 3 年", "自定义年份区间"], index=0)
    year_from, year_to = None, None
    yr = datetime.now().year
    if time_option == "近半年": year_from = yr if datetime.now().month > 6 else yr - 1
    elif time_option == "近 1 年": year_from = yr - 1
    elif time_option == "近 3 年": year_from = yr - 3
    elif time_option == "自定义年份区间":
        c1, c2 = st.columns(2)
        with c1: yf = st.number_input("起始年", min_value=1900, max_value=yr, value=yr - 5, step=1)
        with c2: yt = st.number_input("结束年", min_value=1900, max_value=yr, value=yr, step=1)
        year_from, year_to = (yf, yt) if yf <= yt else (yt, yf)

    if st.button("🔍 搜索论文", type="primary", use_container_width=True):
        if st.session_state.search_mode == "agent":
            interest = research_interest.strip() or keyword.strip()
            if not interest:
                st.warning("请输入研究兴趣描述或关键词")
            else:
                st.session_state.last_keyword = keyword.strip() or interest[:40]
                st.session_state.search_count = search_count
                st.session_state.search_offset = 0
                st.session_state.seen_paper_keys = []
                st.session_state.confirm_new_search = False
                with st.spinner("AI Agent 正在规划搜索策略…"):
                    state = planner_agent({"research_interest": interest, "research_keyword": keyword.strip() or interest[:40], "search_results": [], "max_total_results": search_count})
                    state["max_total_results"] = search_count
                    state = retrieval_agent(state)
                results = state.get("search_results", [])
                st.session_state.seen_paper_keys = [paper_key(r) for r in results]
                batch_enrich(results)
                st.session_state.search_results = results
                if not is_guest:
                    save_search_history(user["id"], keyword.strip() or interest[:40], results)
                st.rerun()
        elif not keyword.strip():
            st.warning("请输入关键词")
        else:
            st.session_state.last_keyword = keyword.strip()
            st.session_state.search_count = search_count
            st.session_state.search_offset = 0
            st.session_state.seen_paper_keys = []
            st.session_state.confirm_new_search = False
            with st.spinner(f"正在搜索「{keyword}」…"):
                results = search_papers(keyword.strip(), count=search_count, year_from=year_from, year_to=year_to, authoritative_only=True)
            st.session_state.seen_paper_keys = [paper_key(r) for r in results]
            batch_enrich(results)
            st.session_state.search_results = results
            # 保存搜索历史
            if not is_guest:
                save_search_history(user["id"], keyword.strip(), results)
            st.rerun()

    # 换一批 / 重新搜索
    if st.session_state.search_results:
        st.divider()
        cr, cn = st.columns(2)
        with cr:
            if st.button("🔀 换一批", use_container_width=True):
                st.session_state.search_offset += st.session_state.search_count
                with st.spinner("正在搜索下一批…"):
                    results = search_papers(st.session_state.last_keyword, count=st.session_state.search_count,
                                            year_from=year_from, year_to=year_to,
                                            offset=st.session_state.search_offset, authoritative_only=True,
                                            exclude_keys=set(st.session_state.seen_paper_keys))
                nk = [paper_key(r) for r in results]
                st.session_state.seen_paper_keys = st.session_state.seen_paper_keys + nk
                batch_enrich(results)
                st.session_state.search_results = results
                st.rerun()
        with cn:
            if st.button("🔄 重新搜索", use_container_width=True):
                if st.session_state.report_ready: st.session_state.confirm_new_search = True
                else: st.session_state.search_results = []; st.session_state.seen_paper_keys = []
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
                if st.button("❌", key=f"remove_{i}"):
                    st.session_state.selected_papers.pop(i); st.rerun()

    # 生成 / 仅下载 按钮
    if len(st.session_state.selected_papers) > 0:
        st.divider()
        cg, cd = st.columns(2)
        with cg:
            if st.button("✅ 生成学习路径", type="primary", use_container_width=True,
                         help="下载论文 + AI生成学习路径报告"):
                st.session_state.generating = True
                st.session_state.download_only = False
                st.session_state.confirm_new_search = False
                st.rerun()
        with cd:
            if st.button("📥 仅下载论文", use_container_width=True,
                         help="仅下载已选论文，不生成报告"):
                st.session_state.generating = True
                st.session_state.download_only = True
                st.session_state.confirm_new_search = False
                st.rerun()

    # 订阅按钮（注册用户且已绑定邮箱）
    if not is_guest and user.get("email"):
        st.divider()
        st.subheader("📬 论文订阅")
        st.caption("有新论文时推送到你的邮箱")
        sk = st.text_input("订阅关键词", key="sub_keyword_input", placeholder="输入要订阅的研究方向…")
        cs1, cs2 = st.columns(2)
        with cs1:
            if st.button("➕ 订阅", use_container_width=True):
                ok, msg = subscribe(user["id"], sk)
                if ok: st.success(msg)
                else: st.warning(msg)
        with cs2:
            if st.button("📋 我的订阅", use_container_width=True):
                st.session_state.show_subs = not st.session_state.get("show_subs", False)
        if st.session_state.get("show_subs"):
            subs = get_subscriptions(user["id"])
            if subs:
                for s in subs:
                    st.caption(f"🔔 {s['keyword']} — {s['created_at'][:10]}")
                    if st.button("取消", key=f"unsub_{s['id']}"):
                        unsubscribe(user["id"], s["keyword"]); st.rerun()
            else:
                st.caption("暂无订阅")


# ========== 右栏 ==========
with right:
    # 确认重新搜索
    if st.session_state.confirm_new_search:
        st.warning("确定要开始新一轮搜索吗？将清空已生成的学习路径报告和所有已选论文。")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("确定，重新开始", type="primary", use_container_width=True):
                reset_main(); st.rerun()
        with cc2:
            if st.button("取消", use_container_width=True):
                st.session_state.confirm_new_search = False; st.rerun()

    # 阶段 2：生成报告 / 仅下载
    elif st.session_state.generating:
        papers = st.session_state.selected_papers
        if not papers:
            st.warning("没有已选论文"); st.session_state.generating = False
        else:
            dl_only = st.session_state.download_only
            if dl_only:
                st.subheader("正在下载论文…")
                progress = st.progress(0, text="下载中…")
                progress.progress(50, text="正在下载论文 PDF…")
                downloaded = batch_download(papers, max_workers=5)
                progress.progress(90, text="正在打包…")
                zip_path = create_zip(downloaded, None)
                progress.progress(100, text="完成！")
                st.session_state.generating = False
                st.session_state.report_ready = True
                st.session_state.html_path = ""
                st.session_state.zip_path = zip_path
                st.session_state.report_md = ""
                st.session_state.downloaded = downloaded
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
                if not is_guest:
                    save_report(user["id"], kw, html_path, zip_path, len(downloaded))
            st.rerun()

    # 阶段 3：预览 + 下载 / 发送
    elif st.session_state.report_ready:
        n = len(st.session_state.get("downloaded", []))
        if st.session_state.report_md:
            st.subheader("学习路径已生成！")
            st.success(f"共 {n} 篇论文 + 1 份 HTML 学习路径报告")
            with st.expander("预览学习路径报告", expanded=True):
                st.markdown(st.session_state.report_md)
        else:
            st.subheader("论文下载完成！")
            st.success(f"共 {n} 篇论文已打包")
        st.divider()
        st.subheader("下载 & 发送邮箱")
        c_dl, c_send = st.columns(2)
        with c_dl:
            with open(st.session_state.zip_path, "rb") as f:
                label = "下载全部（论文 + HTML 报告）" if st.session_state.report_md else "下载论文 zip 包"
                st.download_button(label, data=f,
                                   file_name=os.path.basename(st.session_state.zip_path),
                                   mime="application/zip", use_container_width=True)
        with c_send:
            # 注册用户已绑定邮箱则默认使用，否则手动输入
            default_email = ""
            if not is_guest and user.get("email"):
                default_email = user["email"]
            elif not is_guest and not user.get("email"):
                default_email = ""
            else:
                default_email = EMAIL_RECIPIENT
            send_to = st.text_input("收件人邮箱", value=default_email, key="send_email_input")
            if st.button("发送到邮箱", type="primary", use_container_width=True):
                with st.spinner("正在发送…"):
                    kw = st.session_state.last_keyword
                    subject = f"[学习路径] {kw}（{n} 篇论文）"
                    html_body = (f"<h2>你的学习路径</h2><p>这是你选择的 <b>{n} 篇论文</b> 及 HTML 报告。</p>"
                                 f"<p>祝你阅读愉快！</p><hr><small>由论文学习路径生成器自动生成</small>")
                    sent, msg = send_email(subject, html_body, st.session_state.zip_path, send_to)
                    if sent: st.success(f"已发送: {msg}"); st.balloons()
                    else: st.warning(f"发送失败: {msg}")

    # 阶段 1：展示搜索结果
    elif st.session_state.search_results:
        results = st.session_state.search_results
        st.subheader(f"搜索结果 —「{st.session_state.last_keyword}」（{len(results)} 篇）")
        if len(results) == 0:
            st.warning("未找到匹配的论文，请尝试更换关键词或放宽时间范围。")
        selected_ids = {paper_key(p) for p in st.session_state.selected_papers}
        for i, paper in enumerate(results):
            pid = paper_key(paper); selected = pid in selected_ids
            with st.container(border=True):
                cm, cb = st.columns([6, 1])
                with cm:
                    st.markdown(f"### {i+1}. {paper['title']}")
                    # --- 期刊 + 引用数突出显示 ---
                    real_v = paper.get("real_venue", "") or paper.get("venue", "N/A")
                    real_src = paper.get("venue_source", "")
                    src_hint = f" [{real_src}]" if real_src and real_src != "category-whitelist" else ""
                    cites = paper.get("citation_count")
                    if cites is not None and cites > 0:
                        cite_text = f"📊 **引用: {cites:,} 次**"
                    elif cites is not None and cites == 0:
                        cite_text = "📊 引用: 0 次"
                    else:
                        cite_text = "📊 引用: 暂无数据"
                    st.markdown(f"🏛 **{real_v}**{src_hint}  |  {cite_text}  |  📅 {paper.get('real_year', paper.get('year', 'N/A'))}")
                    st.caption(f"✍ {paper.get('authors', 'N/A')}")
                    # 标签
                    tags = paper_tags(paper)
                    if tags: st.caption(" | ".join(tags))
                    # --- 摘要折叠 ---
                    abstract = paper.get("abstract", "")
                    if abstract:
                        with st.expander(f"📝 摘要 ({len(abstract)} 字)"):
                            st.markdown(abstract)
                    else:
                        st.caption("(无摘要)")
                    aid = paper.get("arxiv_id", "")
                    if aid: st.markdown(f"[📎 arXiv: {aid}](https://arxiv.org/abs/{aid})")
                with cb:
                    if selected:
                        st.success("已选")
                        if st.button("取消", key=f"desel_{i}"):
                            st.session_state.selected_papers = [p for p in st.session_state.selected_papers if paper_key(p) != pid]
                            st.rerun()
                    else:
                        if st.button("+ 选择", key=f"sel_{i}"):
                            st.session_state.selected_papers.append(paper); st.rerun()

    # 阶段 0：空状态
    else:
        st.info("👈 在左侧输入关键词并点击搜索，开始探索论文吧！")
        with st.expander("使用说明"):
            st.markdown("""
            1. **输入关键词** — 在左侧输入你感兴趣的研究方向
            2. **浏览结果** — 查看论文标题、作者、摘要、权威性
            3. **选择论文** — 点击「+ 选择」加入已选篮
            4. **多次搜索** — 可换关键词，已选累积
            5. **生成学习路径** — AI 生成 HTML 报告
            6. **下载 / 发送** — 下载到本地或发送邮箱
            """)
