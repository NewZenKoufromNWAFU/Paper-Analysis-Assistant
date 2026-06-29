import streamlit as st
import os, re
from datetime import datetime
from config import EMAIL_RECIPIENT
from tools.academic_search import search_papers
from tools.paper_downloader import batch_download
from tools.report_generator import save_html_report
from tools.email_sender import create_zip, send_email
from tools.paper_validator import batch_enrich, paper_tags, authority_score
from tools.auth import register, login, update_profile, check_search_limit, increment_search_count, activate_pro, FREE_SEARCH_LIMIT, PRO_PRICE
from tools.auth import save_search_history, get_search_history
from tools.auth import save_report, get_reports
from tools.auth import subscribe, unsubscribe, get_subscriptions
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE
from agents.retriever import retrieval_agent
from agents.planner import planner_agent

st.set_page_config(page_title="论文学习路径生成器", page_icon="🎓", layout="wide")

# ============================================================
# 会话状态
# ============================================================
if "user" not in st.session_state: st.session_state.user = None
if "page" not in st.session_state: st.session_state.page = "login"
INIT_MAIN = {
    "selected_papers": [], "search_results": [], "last_keyword": "",
    "search_offset": 0, "search_count": 5, "search_mode": "keyword",
    "generating": False, "download_only": False, "report_ready": False,
    "html_path": "", "zip_path": "", "confirm_new_search": False,
    "score_threshold": 0, "show_filters": False,
}
if "seen_paper_keys" not in st.session_state: st.session_state.seen_paper_keys = []
for k, v in INIT_MAIN.items():
    if k not in st.session_state: st.session_state[k] = v

# ============================================================
# 工具函数
# ============================================================
def paper_key(p): return (p.get("arxiv_id") or p.get("paper_id") or p.get("title","")).strip().lower()

def one_line_insight(paper: dict) -> str:
    abstract = paper.get("abstract","") or ""
    if not abstract: return ""
    for m in re.finditer(r'[。！？.!?\n]', abstract):
        sent = abstract[:m.start()+1].strip().replace("\n"," ")
        if len(sent) >= 15: return sent[:120]
    return abstract[:120]

def generate_learning_path_report(papers, keyword):
    llm = ChatOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL, temperature=0.1)
    rows = []; pl = []
    for i, pp in enumerate(papers, 1):
        rv = pp.get("real_venue","") or pp.get("venue","N/A") or "arXiv"
        rows.append(f"|{i}|{pp.get('title','N/A')[:40]}|{pp.get('real_year',pp.get('year','N/A'))}|{rv}|{pp.get('citation_count',0)}|")
        pl.append(f"###{i}.{pp.get('title','N/A')}({pp.get('real_year',pp.get('year','N/A'))})\n作者:{pp.get('authors','N/A')}|期刊:{rv}|引用:{pp.get('citation_count',0)}\n摘要:{pp.get('abstract','(无)')[:300]}\n")
    tbl = "|#|论文|年份|期刊|引用|\n|---|---|---|---|---|\n"+"\n".join(rows)
    blob = "\n---\n".join(pl)
    sys = SystemMessage(content=f"学术导师。研究方向:{keyword}。中文回复，简洁。结构:1.概述 2.论文对比表 3.逐篇导读(2-3句) 4.阅读顺序 5.下一步。emoji。")
    return llm.invoke([sys, HumanMessage(content=f"对比表:\n{tbl}\n\n论文:\n{blob}\n\n生成学习路径。")]).content

def reset_main():
    for k in list(st.session_state.keys()):
        if k in INIT_MAIN: st.session_state[k] = INIT_MAIN[k]
        elif k == "seen_paper_keys": st.session_state[k] = []
        elif k not in ("user","page"): del st.session_state[k]

def do_logout(): st.session_state.user = None; st.session_state.page = "login"; reset_main(); st.rerun()

# ============================================================
# === 登录/注册页面 ===
# ============================================================
if st.session_state.page == "login":
    _, col_c, _ = st.columns([1,2,1])
    with col_c:
        st.title("🎓 论文学习路径生成器")
        st.caption("搜索论文 → 选择 → 生成学习路径 → 下载/发送邮箱")
        tab_login, tab_reg = st.tabs(["登录","注册"])
        with tab_login:
            l_u = st.text_input("用户名", key="l_u")
            l_p = st.text_input("密码", type="password", key="l_p")
            c1,c2 = st.columns(2)
            with c1:
                if st.button("登录", type="primary", use_container_width=True):
                    ok,msg,user = login(l_u,l_p)
                    if ok: st.session_state.user=user; st.session_state.page="main"; st.rerun()
                    else: st.error(msg)
            with c2:
                if st.button("游客访问", use_container_width=True): st.session_state.user=None; st.session_state.page="main"; st.rerun()
        with tab_reg:
            r_u = st.text_input("用户名", key="r_u", placeholder="2位以上")
            r_e = st.text_input("邮箱", key="r_e", placeholder="your@email.com")
            r_p = st.text_input("密码 (6位以上)", type="password", key="r_p")
            r_role = st.selectbox("学术身份", ["暂不选择","本科","硕士","博士","博士后","教师/研究员"], index=0, key="r_role")
            if st.button("注册", type="primary", use_container_width=True):
                role = r_role if r_role!="暂不选择" else ""
                ok,msg,user = register(r_u,r_e,r_p,role)
                if ok: st.session_state.user=user; st.session_state.page="main"; st.rerun()
                else: st.error(msg)
        st.divider(); st.caption("游客可直接访问，不会保存搜索历史和报告。")
    st.stop()

# ============================================================
# === 主页面 ===
# ============================================================
user = st.session_state.user
is_guest = user is None

# ---- 顶部栏 ----
with st.container():
    c1,c2 = st.columns([5,1])
    with c1:
        if is_guest: st.markdown("👤 **游客模式**")
        else:
            nn = user.get("nickname","") or user.get("username","用户")
            role = user.get("role","")
            rw = " ⚠️ 请选择角色" if not role else ""
            is_pro = user.get("is_pro", False)
            pro_badge = " 💎 Pro" if is_pro else ""
            st.markdown(f"👤 **{nn}**{pro_badge} | 🎓 {role or '未选择'}{rw} | 📧 {user.get('email','')}")
    with c2:
        if is_guest:
            if st.button("🔐 登录/注册", use_container_width=True): st.session_state.page="login"; st.rerun()
        else:
            if st.button("👤 账户", use_container_width=True): st.session_state.show_profile = not st.session_state.get("show_profile",False)

# ---- 账户弹窗 ----
if st.session_state.get("show_profile") and not is_guest:
    with st.expander("👤 账户信息", expanded=True):
        is_pro = user.get("is_pro", False)
        pro_text = "💎 Pro 会员 · 无限搜索" if is_pro else f"🆓 免费用户 · 剩余 {max(0, FREE_SEARCH_LIMIT - (user.get('search_count', 0) or 0))}/{FREE_SEARCH_LIMIT} 次搜索"
        st.markdown(f"**{user.get('username','')}** · {pro_text}")
        st.markdown(f"📧 {user.get('email','')} · 🎓 {user.get('role','未选择')}")
        c_ed,c_hi,c_pr,c_ou = st.columns(4)
        with c_ed:
            if st.button("✏️ 修改", use_container_width=True): st.session_state.show_edit = not st.session_state.get("show_edit",False)
        with c_hi:
            if st.button("📋 历史", use_container_width=True): st.session_state.show_history = not st.session_state.get("show_history",False)
        with c_pr:
            if not is_pro:
                if st.button(f"💎 升级 Pro (${PRO_PRICE})", use_container_width=True):
                    st.session_state.show_pro = True
        with c_ou:
            if st.button("🚪 退出", use_container_width=True): do_logout()

# ---- Pro 升级页面 ----
if st.session_state.get("show_pro") and not is_guest:
    with st.expander("💎 升级 Pro 会员", expanded=True):
        st.markdown(f"""
        ### 💎 Pro 会员权益
        - 🔍 **无限搜索** — 不再受 {FREE_SEARCH_LIMIT} 次限制
        - 📬 **论文订阅推送** — 每 3 天推送最新论文
        - 📊 **高级评分筛选** — 百分制评分 + 多维过滤
        - 📄 **学习路径报告** — AI 生成 + 打包下载
        - 📧 **邮件发送** — 报告和论文一键发送到邮箱

        **价格: ${PRO_PRICE}/永久**
        """)
        if st.button("💳 确认升级 Pro", type="primary", use_container_width=True):
            activate_pro(user["id"])
            user["is_pro"] = 1
            st.session_state.user = user
            st.session_state.show_pro = False
            st.success("升级成功！你现在是 Pro 会员了 💎")
            st.rerun()

if st.session_state.get("show_edit") and not is_guest:
    with st.expander("✏️ 编辑个人信息", expanded=True):
        st.markdown(f"**用户名:** {user.get('username','')} *(不可修改)*")
        n_e = st.text_input("邮箱", value=user.get("email",""), key="edit_email")
        n_r = st.selectbox("学术身份", ["","本科","硕士","博士","博士后","教师/研究员"],
                           index=["","本科","硕士","博士","博士后","教师/研究员"].index(user.get("role","")) if user.get("role","") in ["本科","硕士","博士","博士后","教师/研究员"] else 0)
        cs,cc = st.columns(2)
        with cs:
            if st.button("保存", use_container_width=True):
                ok,msg,u = update_profile(user["id"], role=n_r, email=n_e)
                if ok: st.session_state.user=u; st.success(msg); st.rerun()
                else: st.error(msg)
        with cc:
            if st.button("关闭", use_container_width=True): st.session_state.show_edit=False; st.rerun()

if st.session_state.get("show_history") and not is_guest:
    with st.expander("📋 历史记录", expanded=True):
        t1,t2,t3 = st.tabs(["搜索历史","学习报告","仅下载论文"])
        with t1:
            for h in get_search_history(user["id"]): st.caption(f"🔍 {h['keyword']} — {h['created_at']}")
        with t2:
            for r in [r for r in get_reports(user["id"]) if r.get("html_path") and os.path.exists(r.get("html_path",""))]:
                st.markdown(f"📄 **{r['keyword']}** — {r['paper_count']}篇 — {r['created_at']}")
                cd1,cd2 = st.columns(2)
                with cd1:
                    if os.path.exists(r.get("html_path","")):
                        with open(r["html_path"],"rb") as ff: st.download_button("📥 下载报告", ff, os.path.basename(r["html_path"]), "text/html", key=f"dh_{r['id']}")
                with cd2:
                    if os.path.exists(r.get("zip_path","")):
                        with open(r["zip_path"],"rb") as ff: st.download_button("📦 下载论文包", ff, os.path.basename(r["zip_path"]), "application/zip", key=f"dz_{r['id']}")
                st.divider()
        with t3:
            for r in [r for r in get_reports(user["id"]) if not r.get("html_path")]:
                st.markdown(f"📦 **{r['keyword']}** — {r['paper_count']}篇 — {r['created_at']}")
                if os.path.exists(r.get("zip_path","")):
                    with open(r["zip_path"],"rb") as ff: st.download_button("📥 下载", ff, os.path.basename(r["zip_path"]), "application/zip", key=f"dz_{r['id']}")
                st.divider()
        if st.button("关闭历史", use_container_width=True): st.session_state.show_history=False; st.rerun()

if not is_guest and not user.get("role"): st.warning("💡 请设置学术身份，点击右上角「👤 账户」→「✏️ 修改」设置。")

st.divider()

# ============================================================
# === 搜索栏（置顶居中）===
# ============================================================
col_search = st.columns([1, 3, 1])
with col_search[1]:
    with st.form("search_form", border=False):
        kw_input = st.text_input("🔍 研究方向或论文关键词", placeholder="例如：Transformer注意力机制… 按 Enter 搜索", label_visibility="collapsed", key="search_kw")
        cm1, cm2, cm3 = st.columns([1, 1, 2])
        with cm1:
            mode = st.radio("模式", ["⚡ 快速搜索", "🧠 深度检索"], horizontal=True, label_visibility="collapsed")
        with cm2:
            count = st.select_slider("数量", options=list(range(1,11)), value=st.session_state.search_count)
        with cm3:
            submitted = st.form_submit_button("🔍 搜索", type="primary", use_container_width=True)

    if st.checkbox("⚙️ 高级筛选（时间范围·评分门槛）", value=st.session_state.show_filters):
        st.session_state.show_filters = True
        f1,f2,f3 = st.columns(3)
        with f1:
            to = st.selectbox("📅 发表时间", ["不限时间","近半年","近 1 年","近 3 年","自定义"], key="filter_time")
        with f2:
            st.session_state.score_threshold = st.slider("⭐ 最低评分", 0, 100, st.session_state.score_threshold, 10, key="filter_score")
        with f3:
            st.caption(f"过滤: {to} · ≥{st.session_state.score_threshold}分")
    else:
        st.session_state.show_filters = False
        to = "不限时间"; st.session_state.score_threshold = 0

if submitted and kw_input.strip():
    # Pro search limit check
    if not is_guest:
        can, remaining, is_pro = check_search_limit(user["id"])
        if not is_pro and remaining <= 0:
            st.warning(f"免费搜索次数已用完（{FREE_SEARCH_LIMIT}次），点击「👤 账户」→「💎 升级 Pro」解锁无限搜索。")
            st.stop()
    st.session_state.search_mode = "agent" if "深度" in mode else "keyword"
    st.session_state.search_count = count
    st.session_state.search_offset = 0
    st.session_state.seen_paper_keys = []
    st.session_state.confirm_new_search = False
    yf_val, yt_val = None, None
    yr = datetime.now().year
    if to == "近半年": yf_val = yr if datetime.now().month > 6 else yr - 1
    elif to == "近 1 年": yf_val = yr - 1
    elif to == "近 3 年": yf_val = yr - 3
    if st.session_state.search_mode == "agent":
        with st.spinner("AI Agent 正在规划…"):
            state = planner_agent({"research_interest": kw_input, "research_keyword": kw_input, "search_results": [], "max_total_results": count})
            state["max_total_results"] = count; state = retrieval_agent(state)
        results = state.get("search_results", [])
    else:
        with st.spinner(f"正在搜索「{kw_input}」…"):
            results = search_papers(kw_input, count=count, year_from=yf_val, year_to=yt_val, authoritative_only=True)
    st.session_state.last_keyword = kw_input.strip()
    st.session_state.seen_paper_keys = [paper_key(r) for r in results]
    batch_enrich(results)
    st.session_state.search_results = results
    if not is_guest:
        save_search_history(user["id"], kw_input.strip(), results)
        increment_search_count(user["id"])
        user["search_count"] = (user.get("search_count", 0) or 0) + 1
    st.rerun()

if st.session_state.search_results:
    cr,cn = st.columns([1,1])
    with cr:
        if st.button("🔀 换一批", use_container_width=True):
            st.session_state.search_offset += st.session_state.search_count
            yr2 = datetime.now().year
            yf2 = yr2 if datetime.now().month>6 else yr2-1 if to=="近半年" else (yr2-1 if to=="近 1 年" else (yr2-3 if to=="近 3 年" else None))
            with st.spinner("搜索下一批…"):
                results = search_papers(st.session_state.last_keyword, count=st.session_state.search_count,
                                        year_from=yf2, offset=st.session_state.search_offset,
                                        authoritative_only=True, exclude_keys=set(st.session_state.seen_paper_keys))
            st.session_state.seen_paper_keys += [paper_key(r) for r in results]
            batch_enrich(results); st.session_state.search_results = results; st.rerun()
    with cn:
        if st.button("🔄 重新搜索", use_container_width=True):
            if st.session_state.report_ready: st.session_state.confirm_new_search=True
            else: st.session_state.search_results=[]; st.session_state.seen_paper_keys=[]
            st.rerun()

st.divider()

# ============================================================
# === 主内容区 ===
# ============================================================
display_results = st.session_state.search_results
if st.session_state.search_results and st.session_state.score_threshold > 0:
    display_results = [r for r in st.session_state.search_results
                       if authority_score(r, st.session_state.last_keyword) >= st.session_state.score_threshold]

left, right = st.columns([1, 2])

with left:
    st.subheader(f"📋 已选论文（{len(st.session_state.selected_papers)}）")
    if not st.session_state.selected_papers:
        st.caption("暂无已选论文。")
    else:
        for i,pp in enumerate(st.session_state.selected_papers):
            ct,cx = st.columns([5,1])
            with ct:
                st.markdown(f"**{i+1}.** {pp['title'][:45]}{'…' if len(pp['title'])>45 else ''}")
                st.caption(f"{pp.get('year','?')} | {pp.get('authors','')[:25]}")
            with cx:
                if st.button("❌", key=f"rm_{i}"): st.session_state.selected_papers.pop(i); st.rerun()
    if len(st.session_state.selected_papers) > 0:
        st.divider()
        cg,cd = st.columns(2)
        with cg:
            if st.button("✅ 生成学习路径", type="primary", use_container_width=True):
                st.session_state.generating=True; st.session_state.download_only=False
                st.session_state.confirm_new_search=False; st.rerun()
        with cd:
            if st.button("📥 仅下载论文", use_container_width=True):
                st.session_state.generating=True; st.session_state.download_only=True
                st.session_state.confirm_new_search=False; st.rerun()
    if not is_guest and user.get("email"):
        st.divider(); st.subheader("📬 订阅")
        sk = st.text_input("订阅关键词", key="sub_kw", placeholder="每3天推送一篇…")
        cs1,cs2 = st.columns(2)
        with cs1:
            if st.button("➕ 订阅", use_container_width=True):
                ok,msg = subscribe(user["id"], sk)
                if ok: st.success(msg)
                else: st.warning(msg)
        with cs2:
            if st.button("📋 我的", use_container_width=True): st.session_state.show_subs = not st.session_state.get("show_subs",False)
        if st.session_state.get("show_subs"):
            for s in get_subscriptions(user["id"]):
                st.caption(f"🔔 {s['keyword']}")
                if st.button("取消", key=f"unsub_{s['id']}"): unsubscribe(user["id"], s["keyword"]); st.rerun()

with right:
    if st.session_state.confirm_new_search:
        st.warning("确定要开始新一轮搜索吗？将清空已生成的学习路径报告和所有已选论文。")
        cc1,cc2 = st.columns(2)
        with cc1:
            if st.button("确定", type="primary", use_container_width=True): reset_main(); st.rerun()
        with cc2:
            if st.button("取消", use_container_width=True): st.session_state.confirm_new_search=False; st.rerun()

    elif st.session_state.generating:
        papers = st.session_state.selected_papers
        if not papers: st.warning("没有已选论文"); st.session_state.generating=False
        elif st.session_state.download_only:
            status = st.empty(); prog = st.progress(0); status.info("📥 并行下载论文 PDF…")
            prog.progress(20); downloaded = batch_download(papers, max_workers=8)
            if not downloaded: st.error("下载失败"); st.session_state.generating=False
            else:
                status.info("📦 打包中…"); prog.progress(80)
                zp = create_zip(downloaded, None)
                if zp is None: st.error("打包失败"); st.session_state.generating=False
                else:
                    status.success("✅ 完成！"); prog.progress(100)
                    st.session_state.generating=False; st.session_state.report_ready=True
                    st.session_state.html_path=""; st.session_state.zip_path=zp
                    st.session_state.report_md=""; st.session_state.downloaded=downloaded
                    if not is_guest: save_report(user["id"], st.session_state.last_keyword or "学术论文", "", zp, len(downloaded))
                    st.rerun()
        else:
            status = st.empty(); prog = st.progress(0); status.info("📥 下载论文 PDF…")
            prog.progress(20); downloaded = batch_download(papers, max_workers=8)
            status.info("🤖 AI 撰写学习路径（30-60秒）…"); prog.progress(40)
            kw = st.session_state.last_keyword or "学术论文"
            md = generate_learning_path_report(downloaded, kw)
            status.info("📄 渲染 HTML 报告…"); prog.progress(75)
            hp = save_html_report(md, "learning_path")
            status.info("📦 打包…"); prog.progress(90)
            zp = create_zip(downloaded, hp)
            status.success("✅ 完成！"); prog.progress(100)
            st.session_state.generating=False; st.session_state.report_ready=True
            st.session_state.html_path=hp; st.session_state.zip_path=zp
            st.session_state.report_md=md; st.session_state.downloaded=downloaded
            if not is_guest: save_report(user["id"], kw, hp, zp, len(downloaded))
            st.rerun()

    elif st.session_state.report_ready:
        n = len(st.session_state.get("downloaded",[]))
        if st.session_state.report_md:
            st.subheader("学习路径已生成！"); st.success(f"共 {n} 篇论文 + HTML 报告")
            with st.expander("📊 预览", expanded=True): st.markdown(st.session_state.report_md)
        else: st.subheader("下载完成！"); st.success(f"共 {n} 篇论文")
        st.divider(); st.subheader("下载 & 发送邮箱")
        cd,cs = st.columns(2)
        with cd:
            with open(st.session_state.zip_path,"rb") as f:
                st.download_button("下载全部" if st.session_state.report_md else "下载 zip", f,
                                   os.path.basename(st.session_state.zip_path), "application/zip", use_container_width=True)
        with cs:
            de = user.get("email","") if not is_guest else EMAIL_RECIPIENT
            send_to = st.text_input("收件人邮箱", value=de, key="send_email_input")
            if st.button("发送到邮箱", type="primary", use_container_width=True):
                with st.spinner("发送中…"):
                    subj = f"[学习路径] {st.session_state.last_keyword}（{n} 篇）"
                    body = f"<h2>你的学习路径</h2><p><b>{n} 篇论文</b> 及报告。</p><hr><small>论文学习路径生成器</small>"
                    sent,msg = send_email(subj, body, st.session_state.zip_path, send_to)
                    if sent: st.success(f"已发送: {msg}"); st.balloons()
                    else: st.warning(f"发送失败: {msg}")

    elif display_results:
        results = display_results
        st.subheader(f"📄 搜索结果 —「{st.session_state.last_keyword}」（{len(results)} 篇）")
        if st.session_state.score_threshold > 0:
            st.caption(f"⭐ 评分筛选：≥ {st.session_state.score_threshold} 分（{len(st.session_state.search_results)} → {len(results)} 篇）")
        if len(results) == 0:
            st.warning("未找到匹配的论文。请尝试放宽筛选条件或更换关键词。")
        sel_ids = {paper_key(p) for p in st.session_state.selected_papers}
        for i,paper in enumerate(results):
            pid = paper_key(paper); selected = pid in sel_ids
            score = authority_score(paper, st.session_state.last_keyword)
            sc = "🟢" if score >= 70 else ("🟡" if score >= 40 else "🔴")
            with st.container(border=True):
                c_t,c_b = st.columns([6,1])
                with c_t: st.markdown(f"### {i+1}. {paper['title']}")
                with c_b:
                    if selected:
                        st.success("✅")
                        if st.button("取消", key=f"desel_{i}"):
                            st.session_state.selected_papers = [p for p in st.session_state.selected_papers if paper_key(p)!=pid]; st.rerun()
                    else:
                        if st.button("+", key=f"sel_{i}"): st.session_state.selected_papers.append(paper); st.rerun()
                rv = paper.get("real_venue","") or paper.get("venue","N/A")
                src = paper.get("venue_source","")
                sh = f" [{src}]" if src and src != "category-whitelist" else ""
                cites = paper.get("citation_count")
                ct = f"📊 {cites:,} 次" if (cites is not None and cites > 0) else ("📊 0 次" if cites is not None else "📊 暂无数据")
                st.markdown(f"🏛 **{rv}**{sh} · {ct} · 📅 {paper.get('real_year',paper.get('year','N/A'))} · ✍ {paper.get('authors','N/A')[:40]}")
                st.progress(score/100, text=f"{sc} 评分: {score}/100")
                insight = one_line_insight(paper)
                if insight: st.caption(f"💡 {insight}")
                tags = paper_tags(paper)
                if tags: st.caption(" · ".join(tags))
                abstract = paper.get("abstract","")
                if abstract:
                    with st.expander(f"📝 完整摘要 ({len(abstract)} 字)"): st.markdown(abstract)
                aid = paper.get("arxiv_id","")
                if aid: st.markdown(f"[📎 arXiv](https://arxiv.org/abs/{aid})")
    else:
        st.markdown("""<div style="text-align:center;padding:60px 20px">
          <div style="font-size:80px">🔍</div>
          <h2>开始你的学术探索之旅</h2>
          <p style="color:#888;font-size:16px">在上方搜索框输入研究方向，发现领域最前沿的论文</p>
          <p style="color:#aaa;font-size:14px">支持中英文关键词 · AI Agent 深度检索 · 学习路径自动生成 · 论文打包下载 · 邮件推送</p>
        </div>""", unsafe_allow_html=True)
