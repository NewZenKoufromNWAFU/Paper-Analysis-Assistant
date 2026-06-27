import streamlit as st
import os
from datetime import datetime
from config import EMAIL_RECIPIENT
from tools.academic_search import search_papers
from tools.paper_downloader import batch_download
from tools.report_generator import save_html_report
from tools.email_sender import create_zip, send_email
from tools.paper_validator import batch_enrich, paper_tags
from tools.auth import register, login, update_profile
from tools.auth import save_search_history, get_search_history
from tools.auth import save_report, get_reports
from tools.auth import subscribe, unsubscribe, get_subscriptions
from tools.auth import check_search_limit, increment_search_count, upgrade_to_pro
from tools.auth import FREE_SEARCH_LIMIT, PRO_PRICE
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE
from agents.retriever import retrieval_agent
from agents.planner import planner_agent

st.set_page_config(page_title="论文学习路径生成器", page_icon="🎓", layout="wide")

st.markdown("""
<style>
  .badge-container { display:flex; align-items:center; gap:10px; padding:10px 12px; background:rgba(0,0,0,0.03); border:1px solid #e0e0e0; border-radius:12px; margin:8px 0; }
  .badge-avatar { width:38px; height:38px; border-radius:50%; background:linear-gradient(135deg,#667eea,#764ba2); display:flex; align-items:center; justify-content:center; color:white; font-weight:bold; font-size:16px; flex-shrink:0; }
  .badge-info { flex:1; line-height:1.3; }
  .badge-name { font-weight:600; font-size:14px; color:#1a1a2e; }
  .badge-label { display:inline-block; font-size:11px; padding:1px 8px; border-radius:10px; font-weight:600; }
  .badge-pro { background:#ffd700; color:#1a1a2e; }
  .badge-free { background:#e2e8f0; color:#4a5568; }
  .search-count { font-size:12px; color:#718096; margin-top:2px; }
  .pro-card { background:white; border:1px solid #e0e0e0; border-radius:16px; padding:24px; margin:12px 0; text-align:center; box-shadow:0 2px 8px rgba(0,0,0,0.06); }
  .pro-card h3 { color:#1a202c; margin-bottom:8px; }
  .pro-card .price { font-size:32px; font-weight:bold; color:#1a202c; }
  .pro-card .price span { font-size:16px; color:#718096; }
  .pro-card ul { list-style:none; padding:0; text-align:left; }
  .pro-card li { padding:6px 0; color:#4a5568; }
  .pro-card-highlight { border:2px solid #ffd700; background:linear-gradient(145deg,#fffbea,#ffffff); }
</style>
""", unsafe_allow_html=True)
st.set_page_config(page_title="论文学习路径生成器", page_icon="🎓", layout="wide")

# ============================================================
# 会话状态
# ============================================================
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "login"

INIT_MAIN = {
    "selected_papers": [], "search_results": [], "last_keyword": "",
    "search_offset": 0, "search_count": 5, "search_mode": "keyword",
    "generating": False, "download_only": False, "report_ready": False,
    "html_path": "", "zip_path": "", "confirm_new_search": False,
    "report_md": "", "downloaded": [],
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

def generate_learning_path_report(papers: list, keyword: str) -> str:
    llm = ChatOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL, temperature=0.1)
    rows = []
    for i, pp in enumerate(papers, 1):
        rv = pp.get("real_venue","") or pp.get("venue","N/A") or "arXiv"
        rows.append(f"|{i}|{pp.get('title','N/A')[:40]}|{pp.get('real_year',pp.get('year','N/A'))}|{rv}|{pp.get('citation_count',0)}|")
    tbl = "|#|论文|年份|期刊|引用|\n|---|---|---|---|---|\n"+"\n".join(rows)
    pl = []
    for i, pp in enumerate(papers, 1):
        rv = pp.get("real_venue","") or pp.get("venue","N/A") or "arXiv"
        pl.append(f"###{i}.{pp.get('title','N/A')}({pp.get('real_year',pp.get('year','N/A'))})\n"
                  f"作者:{pp.get('authors','N/A')} | 期刊:{rv} | 引用:{pp.get('citation_count',0)}\n"
                  f"摘要:{pp.get('abstract','(无)')[:300]}\n")
    blob = "\n---\n".join(pl)
    sys = SystemMessage(content=f"学术导师。研究方向:{keyword}。中文回复，简洁。结构:1.概述 2.论文对比表 3.逐篇导读(每篇2-3句) 4.建议阅读顺序 5.下一步。用emoji。")
    return llm.invoke([sys, HumanMessage(content=f"对比表:\n{tbl}\n\n论文:\n{blob}\n\n请生成学习路径。")]).content

def reset_main():
    for k in list(st.session_state.keys()):
        if k in INIT_MAIN: st.session_state[k] = INIT_MAIN[k]
        elif k == "seen_paper_keys": st.session_state[k] = []
        elif k not in ("user", "page", "show_profile", "show_edit", "show_history", "show_subs"): del st.session_state[k]

def do_logout():
    st.session_state.user = None
    st.session_state.page = "login"
    reset_main()
    st.rerun()



# ============================================================
# === 登录/注册页面 ===
# ============================================================
if st.session_state.page == "login":
    _, col_c, _ = st.columns([1, 2, 1])
    with col_c:
        st.title("🎓 论文学习路径生成器")
        st.caption("搜索论文 → 选择 → 生成学习路径 → 下载/发送邮箱")

        tab_login, tab_reg = st.tabs(["登录", "注册"])

        with tab_login:
            st.subheader("账号登录")
            l_u = st.text_input("用户名", key="l_u", placeholder="请输入用户名")
            l_p = st.text_input("密码", type="password", key="l_p", placeholder="请输入密码")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("登录", type="primary", use_container_width=True):
                    ok, msg, user = login(l_u, l_p)
                    if ok:
                        st.session_state.user = user
                        st.session_state.page = "main"
                        st.rerun()
                    else:
                        st.error(msg)
            with c2:
                if st.button("游客访问", use_container_width=True):
                    st.session_state.user = None
                    st.session_state.page = "main"
                    st.rerun()

        with tab_reg:
            st.subheader("注册新账号")
            r_u = st.text_input("用户名", key="r_u", placeholder="2位以上")
            r_e = st.text_input("邮箱", key="r_e", placeholder="your@email.com")
            r_p = st.text_input("密码 (6位以上)", type="password", key="r_p")
            r_role = st.selectbox("学术身份（推荐选择，有助于精准推荐论文）",
                                  options=["暂不选择", "本科", "硕士", "博士", "博士后", "教师/研究员"],
                                  index=0, key="r_role")
            if st.button("注册", type="primary", use_container_width=True):
                role = r_role if r_role != "暂不选择" else ""
                ok, msg, user = register(r_u, r_e, r_p, role)
                if ok:
                    st.session_state.user = user
                    st.session_state.page = "main"
                    st.rerun()
                else:
                    st.error(msg)

        st.divider()
        st.caption("游客可直接访问，不会保存搜索历史和报告。")

    st.stop()


# ============================================================
# === 主页面 ===
# ============================================================
user = st.session_state.user
is_guest = user is None
is_guest = user is None
is_pro = False
remaining = 0
if user:
    is_pro = user.get("is_pro", 0) == 1
    allowed, rem, is_p, msg = check_search_limit(user["id"])
    remaining = rem


# ---- 顶部栏 ----
with st.container():
    c1, c2 = st.columns([5, 1])
    with c1:
        if is_guest:
            st.markdown("👤 **游客模式**")
        else:
            nn = user.get("nickname", "") or user.get("username", "用户")
            role = user.get("role", "")
            role_warn = " ⚠️ 请选择角色" if not role else ""
            st.markdown(f"👤 **{nn}**  |  🎓 {role or '未选择'}{role_warn}  |  📧 {user.get('email','')}")
    with c2:
        if is_guest:
            if st.button("🔐 登录/注册", use_container_width=True):
                st.session_state.page = "login"
                st.rerun()
        else:
            if st.button("👤 账户", use_container_width=True):
                st.session_state.show_profile = not st.session_state.get("show_profile", False)

# ---- 账户信息弹出 ----
if st.session_state.get("show_profile") and not is_guest:
    with st.expander("👤 账户信息", expanded=True):
        st.markdown(f"**用户名:** {user.get('username','')}")
        st.markdown(f"**邮箱:** {user.get('email','')}")
        st.markdown(f"**角色:** {user.get('role','未选择')}")
        c_edit, c_hist, c_out = st.columns(3)
        with c_edit:
            if st.button("✏️ 修改", use_container_width=True):
                st.session_state.show_edit = not st.session_state.get("show_edit", False)
        with c_hist:
            if st.button("📋 历史", use_container_width=True):
                st.session_state.show_history = not st.session_state.get("show_history", False)
        with c_out:
            if st.button("🚪 退出登录", use_container_width=True):
                do_logout()

# ---- 个人信息编辑 ----
if st.session_state.get("show_edit") and not is_guest:
    with st.expander("✏️ 编辑个人信息", expanded=True):
        st.markdown(f"**用户名:** {user.get('username','')} *(不可修改)*")
        n_e = st.text_input("邮箱", value=user.get("email", ""), key="edit_email")
        n_r = st.selectbox("学术身份", options=["", "本科", "硕士", "博士", "博士后", "教师/研究员"],
                           index=(["","本科","硕士","博士","博士后","教师/研究员"].index(user.get("role","")) if user.get("role","") in ["本科","硕士","博士","博士后","教师/研究员"] else 0),
                           key="edit_role")
        cs, cc = st.columns(2)
        with cs:
            if st.button("保存", use_container_width=True):
                ok, msg, u = update_profile(user["id"], role=n_r, email=n_e)
                if ok: st.session_state.user = u; st.success(msg); st.rerun()
                else: st.error(msg)
        with cc:
            if st.button("关闭", use_container_width=True):
                st.session_state.show_edit = False; st.rerun()

# ---- 历史记录 ----
if st.session_state.get("show_history") and not is_guest:
    with st.expander("📋 历史记录", expanded=True):
        t1, t2, t3 = st.tabs(["搜索历史", "学习报告", "仅下载论文"])
        with t1:
            sh = get_search_history(user["id"])
            if sh:
                for h in sh:
                    st.caption(f"🔍 {h['keyword']} — {h['created_at']}")
            else:
                st.caption("暂无搜索记录")
        with t2:
            rpts = [r for r in get_reports(user["id"]) if r.get("html_path")]
            if rpts:
                for r in rpts:
                    st.markdown(f"📄 **{r['keyword']}** — {r['paper_count']}篇 — 报告+论文 — {r['created_at']}")
                    c1, c2 = st.columns(2)
                    with c1:
                        if r.get("html_path") and os.path.exists(r["html_path"]):
                            with open(r["html_path"], "rb") as ff:
                                st.download_button("📥 下载报告", data=ff, file_name=os.path.basename(r["html_path"]),
                                                   mime="text/html", key=f"dl_r_all_{r['id']}")
                    with c2:
                        if r.get("zip_path") and os.path.exists(r["zip_path"]):
                            with open(r["zip_path"], "rb") as ff:
                                st.download_button("📦 下载论文包", data=ff, file_name=os.path.basename(r["zip_path"]),
                                                   mime="application/zip", key=f"dl_z_all_{r['id']}")
                    st.divider()
            else:
                st.caption("暂无学习报告")
        with t3:
            dls = [r for r in get_reports(user["id"]) if not r.get("html_path")]
            if dls:
                for r in dls:
                    st.markdown(f"📦 **{r['keyword']}** — {r['paper_count']}篇 — 仅论文 — {r['created_at']}")
                    if r.get("zip_path") and os.path.exists(r["zip_path"]):
                        with open(r["zip_path"], "rb") as ff:
                            st.download_button("📥 下载论文包", data=ff, file_name=os.path.basename(r["zip_path"]),
                                               mime="application/zip", key=f"dl_z_only_{r['id']}")
                    st.divider()
            else:
                st.caption("暂无仅下载论文记录")
        if st.button("关闭历史", use_container_width=True):
            st.session_state.show_history = False; st.rerun()

# ---- 角色提醒 ----
if not is_guest and not user.get("role"):
    st.warning("💡 请设置你的学术身份（本科/硕士/博士等），以便获得更精准的论文推荐。点击右上角「👤 账户」→「✏️ 修改」设置。")

st.divider()

# ============================================================
# 主界面

current_tab = st.sidebar.radio("导航", ["\U0001f50d 搜索", "\u2b50 Pro"], index=0, key="nav_tab", label_visibility="collapsed")
st.sidebar.divider()

if user:
    initial = (user.get("nickname") or user.get("username", "?"))[0].upper()
    display_name = user.get("nickname") or user.get("username", "用户")
    b_label = "Pro" if is_pro else "免费"
    b_cls = "badge-pro" if is_pro else "badge-free"
    info_text = "无限搜索" if is_pro else f"剩余 {remaining}/{FREE_SEARCH_LIMIT} 次"
    st.sidebar.markdown(f"""
    <div class=\"badge-container\">
      <div class=\"badge-avatar\">{initial}</div>
      <div class=\"badge-info\">
        <div class=\"badge-name\">{display_name}</div>
        <span class=\"badge-label {b_cls}\">{b_label}</span>
        <div class=\"search-count\">{info_text}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.sidebar.markdown('<div class=\"badge-container\"><div class=\"badge-avatar\">?</div><div class=\"badge-info\"><div class=\"badge-name\">游客</div><span class=\"badge-label badge-free\">免费</span><div class=\"search-count\">未登录</div></div></div>', unsafe_allow_html=True)

if not is_guest and not is_pro:
    if remaining <= 0:
        st.sidebar.warning("免费搜索次数已用完，请升级 Pro", icon=":smile:")
    elif remaining <= 2:
        st.sidebar.info(f"免费搜索剩余 {remaining} 次", icon=":information_source:")

st.sidebar.divider()

if "Pro" in current_tab:
    st.title("\u2b50 Pro 会员升级")
    st.caption("解锁无限搜索与更多高级功能")
    st.divider()
    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.markdown("""
        <div class=\"pro-card\">
          <h3>免费版</h3>
          <div class=\"price\">\u00a50 <span>/ 永久</span></div>
          <ul>
            <li>最多 5 次搜索</li>
            <li>每次搜索 5 篇论文</li>
            <li>基础搜索功能</li>
            <li>AI 学习路径生成</li>
          </ul>
        </div>
        """, unsafe_allow_html=True)
    with col_b:
        st.markdown("""
        <div class=\"pro-card pro-card-highlight\">
          <h3>\u2b50 Pro 会员</h3>
          <div class=\"price\">\u00a54.99 <span>/ 月</span></div>
          <ul>
            <li>无限搜索次数</li>
            <li>每次搜索最多 10 篇</li>
            <li>优先处理队列</li>
            <li>全部高级功能</li>
          </ul>
        </div>
        """, unsafe_allow_html=True)
    if is_pro:
        st.success("\U0001f389 您已经是 Pro 会员，感谢支持！")
    else:
        st.divider()
        st.subheader("\U0001f4b3 升级到 Pro")
        qr_path = os.path.join(os.path.dirname(__file__), "assets", "wechat_pay.png")
        if os.path.exists(qr_path):
            st.image(qr_path, width=200, caption="微信支付收款码")
        else:
            st.info("付款码图片未找到，请将收款码放到 assets/wechat_pay.png")
        pro_email = st.text_input("付款邮箱", placeholder="输入付款时使用的邮箱", key="pro_email_input")
        if st.button("激活 Pro", type="primary", use_container_width=True, key="activate_pro"):
            if not pro_email.strip():
                st.warning("请输入邮箱")
            else:
                with st.spinner("正在激活..."):
                    ok, result = upgrade_to_pro(user["id"])
                    if ok:
                        st.session_state.user = result
                        st.success("\U0001f389 Pro 会员激活成功！")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(result)

if "Pro" not in current_tab:
    left, right = st.columns([1, 2])

    with left:
        st.subheader("🔍 搜索论文")
        mode = st.radio("搜索模式", options=["快速搜索", "深度检索 (AI Agent)"],
                        index=0, horizontal=True, key="search_mode_radio", label_visibility="collapsed")
        st.session_state.search_mode = "agent" if "深度" in mode else "keyword"
        st.caption(f"当前模式：{'🧠 AI Agent 智能规划' if st.session_state.search_mode == 'agent' else '⚡ 快速关键词搜索'}")
    
        keyword = st.text_input("关键词 / 论文标题", placeholder="例如：Transformer、GNN…", key="search_keyword")
        ri = ""
        if st.session_state.search_mode == "agent":
            ri = st.text_area("研究兴趣（自然语言描述）",
                              placeholder="用自然语言描述你的研究兴趣…", key="research_interest_input")
    
        search_count = st.slider("每次搜索数量", 1, 10, 5, 1)
        to = st.selectbox("发表时间", ["不限时间","近半年","近 1 年","近 3 年","自定义年份区间"], 0)
        yf_val, yt_val = None, None
        yr = datetime.now().year
        if to == "近半年": yf_val = yr if datetime.now().month > 6 else yr - 1
        elif to == "近 1 年": yf_val = yr - 1
        elif to == "近 3 年": yf_val = yr - 3
        elif to == "自定义年份区间":
            c1, c2 = st.columns(2)
            with c1: a = st.number_input("起始年", 1900, yr, yr - 5, 1)
            with c2: b = st.number_input("结束年", 1900, yr, yr, 1)
            yf_val, yt_val = (a, b) if a <= b else (b, a)
    
        if st.button("🔍 搜索论文", type="primary", use_container_width=True):
            # Check search limit for non-pro, non-guest users
            if not is_guest and not is_pro:
                allowed, remaining, _, _ = check_search_limit(user["id"])
                if not allowed:
                    st.warning("免费搜索次数已用完，请前往 Pro 页面升级", icon=":-)")
                    st.stop()
                increment_search_count(user["id"])
                remaining = remaining - 1
            if st.session_state.search_mode == "agent":
                interest = ri.strip() or keyword.strip()
                if not interest:
                    st.warning("请输入研究兴趣或关键词")
                else:
                    st.session_state.last_keyword = keyword.strip() or interest[:40]
                    st.session_state.search_count = search_count
                    st.session_state.search_offset = 0
                    st.session_state.seen_paper_keys = []
                    st.session_state.confirm_new_search = False
                    with st.spinner("AI Agent 正在规划…"):
                        state = planner_agent({"research_interest": interest, "research_keyword": keyword.strip() or interest[:40], "search_results": [], "max_total_results": search_count})
                        state["max_total_results"] = search_count
                        state = retrieval_agent(state)
                    results = state.get("search_results", [])
                    st.session_state.seen_paper_keys = [paper_key(r) for r in results]
                    batch_enrich(results)
                    st.session_state.search_results = results
                    if not is_guest: save_search_history(user["id"], keyword.strip() or interest[:40], results)
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
                    results = search_papers(keyword.strip(), count=search_count, year_from=yf_val, year_to=yt_val, authoritative_only=True)
                st.session_state.seen_paper_keys = [paper_key(r) for r in results]
                batch_enrich(results)
                st.session_state.search_results = results
                if not is_guest: save_search_history(user["id"], keyword.strip(), results)
                st.rerun()
    
        if st.session_state.search_results:
            st.divider()
            cr, cn = st.columns(2)
            with cr:
                if st.button("🔀 换一批", use_container_width=True):
                    st.session_state.search_offset += st.session_state.search_count
                    with st.spinner("搜索下一批…"):
                        results = search_papers(st.session_state.last_keyword, count=st.session_state.search_count,
                                                year_from=yf_val, year_to=yt_val, offset=st.session_state.search_offset,
                                                authoritative_only=True, exclude_keys=set(st.session_state.seen_paper_keys))
                    st.session_state.seen_paper_keys += [paper_key(r) for r in results]
                    batch_enrich(results)
                    st.session_state.search_results = results
                    st.rerun()
            with cn:
                if st.button("🔄 重新搜索", use_container_width=True):
                    if st.session_state.report_ready: st.session_state.confirm_new_search = True
                    else: st.session_state.search_results = []; st.session_state.seen_paper_keys = []
                    st.rerun()
    
        st.divider()
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
                    if st.button("❌", key=f"remove_{i}"): st.session_state.selected_papers.pop(i); st.rerun()
    
        if len(st.session_state.selected_papers) > 0:
            st.divider()
            cg, cd = st.columns(2)
            with cg:
                if st.button("✅ 生成学习路径", type="primary", use_container_width=True):
                    st.session_state.generating = True; st.session_state.download_only = False
                    st.session_state.confirm_new_search = False; st.rerun()
            with cd:
                if st.button("📥 仅下载论文", use_container_width=True):
                    st.session_state.generating = True; st.session_state.download_only = True
                    st.session_state.confirm_new_search = False; st.rerun()
    
        if not is_guest and user.get("email"):
            st.divider()
            st.subheader("📬 论文订阅")
            sk = st.text_input("订阅关键词", key="sub_kw", placeholder="输入研究方向…")
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
                for s in get_subscriptions(user["id"]):
                    st.caption(f"🔔 {s['keyword']}")
                    if st.button("取消", key=f"unsub_{s['id']}"):
                        unsubscribe(user["id"], s["keyword"]); st.rerun()
    
    
    # ========== 右栏 ==========
    with right:
        if st.session_state.confirm_new_search:
            st.warning("确定要开始新一轮搜索吗？将清空已生成的学习路径报告和所有已选论文。")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("确定，重新开始", type="primary", use_container_width=True): reset_main(); st.rerun()
            with c2:
                if st.button("取消", use_container_width=True): st.session_state.confirm_new_search = False; st.rerun()
        
        elif st.session_state.generating:
            papers = st.session_state.selected_papers
            if not papers:
                st.warning("没有已选论文"); st.session_state.generating = False
            elif st.session_state.download_only:
                st.subheader("📥 正在下载论文…")
                status = st.empty()
                prog = st.progress(0, text="🚀 启动中…")
                status.info("📥 正在并行下载论文 PDF…")
                prog.progress(20, "📥 下载中…")
                downloaded = batch_download(papers, max_workers=8)
                if not downloaded:
                    st.error("下载失败：所选论文均无 arXiv ID。"); st.session_state.generating = False
                else:
                    status.info("📦 正在打包…")
                    prog.progress(80, "📦 打包中…")
                    zp = create_zip(downloaded, None)
                    if zp is None:
                        st.error("打包失败。"); st.session_state.generating = False
                    else:
                        status.success("✅ 完成！")
                        prog.progress(100, "🎉 下载完成！")
                        st.session_state.generating = False; st.session_state.report_ready = True
                        st.session_state.html_path = ""; st.session_state.zip_path = zp
                        st.session_state.report_md = ""; st.session_state.downloaded = downloaded
                        if not is_guest:
                            kw = st.session_state.last_keyword or "学术论文"
                            save_report(user["id"], kw, "", zp, len(st.session_state.selected_papers))
                        st.rerun()
            else:
                st.subheader("🔨 正在生成学习路径…")
                status = st.empty()
                prog = st.progress(0, text="🚀 启动中…")
        
                status.info("📥 正在下载论文 PDF…")
                prog.progress(10, "📥 下载论文中（并行加速）…")
                downloaded = batch_download(papers, max_workers=8)
        
                status.info("🤖 AI 正在撰写学习路径报告（30-60秒）…")
                prog.progress(40, "🤖 AI 分析中…")
                kw = st.session_state.last_keyword or "学术论文"
                md = generate_learning_path_report(papers, kw)
        
                status.info("📄 正在生成 HTML 报告…")
                prog.progress(75, "📄 渲染 HTML…")
                hp = save_html_report(md, "learning_path")
        
                status.info("📦 正在打包…")
                prog.progress(90, "📦 打包中…")
                zp = create_zip(downloaded, hp)
        
                status.success("✅ 完成！")
                prog.progress(100, "🎉 学习路径已生成！")
                st.session_state.generating = False; st.session_state.report_ready = True
                st.session_state.html_path = hp; st.session_state.zip_path = zp
                st.session_state.report_md = md; st.session_state.downloaded = downloaded
                if not is_guest: save_report(user["id"], kw, hp, zp, len(papers))
                st.rerun()
        
        elif st.session_state.report_ready:
            n = len(st.session_state.downloaded)
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
            cd, cs = st.columns(2)
            with cd:
                with open(st.session_state.zip_path, "rb") as f:
                    label = "下载全部（论文 + 报告）" if st.session_state.report_md else "下载论文 zip 包"
                    st.download_button(label, data=f, file_name=os.path.basename(st.session_state.zip_path),
                                       mime="application/zip", use_container_width=True)
            with cs:
                de = user.get("email","") if not is_guest else EMAIL_RECIPIENT
                send_to = st.text_input("收件人邮箱", value=de, key="send_email_input")
                if st.button("发送到邮箱", type="primary", use_container_width=True):
                    with st.spinner("发送中…"):
                        kw = st.session_state.last_keyword
                        subj = f"[学习路径] {kw}（{n} 篇论文）"
                        body = f"<h2>你的学习路径</h2><p>这是你选择的 <b>{n} 篇论文</b> 及报告。</p><hr><small>由论文学习路径生成器自动生成</small>"
                        sent, msg = send_email(subj, body, st.session_state.zip_path, send_to)
                        if sent: st.success(f"已发送: {msg}"); st.balloons()
                        else: st.warning(f"发送失败: {msg}")
        
        elif st.session_state.search_results:
            results = st.session_state.search_results
            st.subheader(f"搜索结果 —「{st.session_state.last_keyword}」（{len(results)} 篇）")
            if len(results) == 0:
                st.warning("未找到匹配的论文。")
            sel_ids = {paper_key(p) for p in st.session_state.selected_papers}
            for i, paper in enumerate(results):
                pid = paper_key(paper); selected = pid in sel_ids
                with st.container(border=True):
                    cm, cb = st.columns([6, 1])
                    with cm:
                        st.markdown(f"### {i+1}. {paper['title']}")
                        rv = paper.get("real_venue","") or paper.get("venue","N/A")
                        src = paper.get("venue_source","")
                        sh = f" [{src}]" if src and src != "category-whitelist" else ""
                        cites = paper.get("citation_count")
                        if cites is not None and cites > 0: ct = f"📊 **引用: {cites:,} 次**"
                        elif cites is not None and cites == 0: ct = "📊 引用: 0 次"
                        else: ct = "📊 引用: 暂无数据"
                        st.markdown(f"🏛 **{rv}**{sh}  |  {ct}  |  📅 {paper.get('real_year',paper.get('year','N/A'))}")
                        st.caption(f"✍ {paper.get('authors','N/A')}")
                        tags = paper_tags(paper)
                        if tags: st.caption(" | ".join(tags))
                        abstract = paper.get("abstract","")
                        if abstract:
                            with st.expander(f"📝 摘要 ({len(abstract)} 字)"): st.markdown(abstract)
                        else: st.caption("(无摘要)")
                        aid = paper.get("arxiv_id","")
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
