import streamlit as st
import os, re, smtplib
from datetime import datetime
from email.mime.text import MIMEText
from config import EMAIL_RECIPIENT
from tools.academic_search import search_papers
from tools.paper_downloader import batch_download
from tools.report_generator import save_html_report
from tools.email_sender import create_zip, send_email
from tools.paper_validator import batch_enrich, paper_tags, authority_score
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

st.set_page_config(page_title="PaperPath", page_icon="🎓", layout="wide")

# ============================================================
# CSS — liquid glass + tabs
# ============================================================
st.markdown("""
<style>
:root {
  --primary: #1a365d; --primary-light: #2b6cb0; --accent: #d69e2e;
  --bg: #f0f4f8; --card-bg: #ffffff; --text: #1a202c; --text-secondary: #4a5568;
  --border: #e2e8f0; --radius: 16px;
}
.stApp { background: var(--bg); }

/* Glass container */
.glass-box {
  background: rgba(255,255,255,0.35);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(255,255,255,0.5);
  border-radius: 24px;
  padding: 28px 32px;
  margin: 16px 0;
  box-shadow: 0 8px 32px rgba(0,0,0,0.06), inset 0 1px 0 rgba(255,255,255,0.6);
}
.glass-box h3 {
  font-size: 18px; font-weight: 700; color: var(--text); margin-bottom: 8px;
}
.glass-box p { color: var(--text-secondary); font-size: 14px; margin-bottom: 16px; }

/* Paper card */
.paper-card {
  background: var(--card-bg); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px; margin: 12px 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04); transition: all 0.2s;
}
.paper-card:hover { border-color: var(--primary-light); box-shadow: 0 4px 16px rgba(0,0,0,0.08); }

/* Sidebar — no scroll + nav buttons uniform */
[data-testid="stSidebar"] > div:first-child { overflow: hidden; }
[data-testid="stSidebar"] section[data-testid="stSidebarContent"] { overflow: hidden; }
[data-testid="stSidebar"] button[kind="secondary"] { font-size: 14px; }

.selected-panel { background: #e8f0fe; border-radius: 14px; padding: 16px; margin: 8px 0; border: none; }

/* Inputs — white bg to stand out from page */
.stTextInput input, .stTextArea textarea {
  background: #ffffff !important; border: 1px solid #cbd5e0 !important;
  border-radius: 10px !important; box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
  border-color: #3182ce !important; box-shadow: 0 0 0 3px rgba(49,130,206,0.12) !important;
}
/* Selectbox — keep dropdown style, NOT input style */
[data-baseweb="select"] > div {
  background: #ffffff !important; border-color: #cbd5e0 !important;
  border-radius: 10px !important;
}
[data-testid="stExpander"] summary { font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 会话状态
# ============================================================
if "user" not in st.session_state: st.session_state.user = None
if "page" not in st.session_state: st.session_state.page = "login"
if "show_account" not in st.session_state: st.session_state.show_account = False
if "nav_tab" not in st.session_state: st.session_state.nav_tab = "🔍 搜索"
INIT_MAIN = {
    "selected_papers": [], "search_results": [], "last_keyword": "",
    "search_offset": 0, "search_count": 5, "search_mode": "keyword",
    "generating": False, "download_only": False, "report_ready": False,
    "html_path": "", "zip_path": "", "confirm_new_search": False,
    "report_md": "", "downloaded": [], "show_pro_inline": False,
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
    rows=[]; pl=[]
    for i,pp in enumerate(papers,1):
        rv=pp.get("real_venue","") or pp.get("venue","N/A") or "arXiv"
        rows.append(f"|{i}|{pp.get('title','N/A')[:40]}|{pp.get('real_year',pp.get('year','N/A'))}|{rv}|{pp.get('citation_count',0)}|")
        pl.append(f"###{i}.{pp.get('title','N/A')}({pp.get('real_year',pp.get('year','N/A'))})\n作者:{pp.get('authors','N/A')}|期刊:{rv}|引用:{pp.get('citation_count',0)}\n摘要:{pp.get('abstract','(无)')[:300]}\n")
    tbl="|#|论文|年份|期刊|引用|\n|---|---|---|---|---|\n"+"\n".join(rows)
    blob="\n---\n".join(pl)
    sys=SystemMessage(content=f"学术导师。研究方向:{keyword}。中文回复，简洁。结构:1.概述 2.论文对比表 3.逐篇导读(2-3句) 4.阅读顺序 5.下一步。emoji。")
    return llm.invoke([sys,HumanMessage(content=f"对比表:\n{tbl}\n\n论文:\n{blob}\n\n生成学习路径。")]).content

def reset_main():
    for k in list(st.session_state.keys()):
        if k in INIT_MAIN: st.session_state[k]=INIT_MAIN[k]
        elif k=="seen_paper_keys": st.session_state[k]=[]
        elif k not in ("user","page","show_account","show_pro_inline","nav_tab"): del st.session_state[k]
    st.session_state.nav_tab = "🔍 搜索"

def do_logout(): st.session_state.user=None; st.session_state.page="login"; st.session_state.show_account=False; reset_main(); st.rerun()

def _send_feedback_email(subject, body):
    """Send feedback to hardcoded admin email."""
    try:
        from config import EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, EMAIL_SENDER, EMAIL_PASSWORD
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = EMAIL_SENDER
        msg["To"] = "2896819742@qq.com"
        msg["Subject"] = subject
        with smtplib.SMTP_SSL(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, timeout=15) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.sendmail(EMAIL_SENDER, "2896819742@qq.com", msg.as_string())
        return True, "提交成功！感谢你的反馈 🙏"
    except Exception as e:
        return False, f"提交失败: {e}"


# ============================================================
# === 登录/注册页面 ===
# ============================================================
if st.session_state.page=="login":
    _,col_c,_=st.columns([1,2.5,1])
    with col_c:
        st.title("🎓 PaperPath")
        st.caption("论文搜索 · 学习路径 · 打包下载 · 邮件推送")
        tab_login,tab_reg=st.tabs(["登录","注册"])
        with tab_login:
            l_u=st.text_input("用户名",key="l_u",placeholder="请输入用户名")
            l_p=st.text_input("密码",type="password",key="l_p",placeholder="请输入密码")
            c1,c2=st.columns(2)
            with c1:
                if st.button("登录",type="primary",use_container_width=True):
                    ok,msg,user=login(l_u,l_p)
                    if ok: st.session_state.user=user; st.session_state.page="main"; st.rerun()
                    else: st.error(msg)
            with c2:
                if st.button("游客访问",use_container_width=True): st.session_state.user=None; st.session_state.page="main"; st.rerun()
        with tab_reg:
            r_u=st.text_input("用户名",key="r_u",placeholder="2位以上")
            r_e=st.text_input("邮箱",key="r_e",placeholder="your@email.com")
            r_p=st.text_input("密码 (6位以上)",type="password",key="r_p")
            r_role=st.selectbox("学术身份",["暂不选择","本科","硕士","博士","博士后","教师/研究员"],index=0,key="r_role")
            if st.button("注册",type="primary",use_container_width=True):
                role=r_role if r_role!="暂不选择" else ""
                ok,msg,user=register(r_u,r_e,r_p,role)
                if ok: st.session_state.user=user; st.session_state.page="main"; st.rerun()
                else: st.error(msg)
        st.divider();st.caption("游客可直接访问。")
    st.stop()

# ============================================================
# === 主页面 ===
# ============================================================
user=st.session_state.user
is_guest=user is None
is_pro=False;remaining=0
if user:
    is_pro=user.get("is_pro",0)==1
    allowed,rem,is_p,msg=check_search_limit(user["id"])
    remaining=rem

# ============================================================
# 账号全页面弹窗
# ============================================================
if st.session_state.show_account and not is_guest:
    st.title("👤 账户信息")
    nn=user.get("nickname","") or user.get("username","用户")
    st.markdown(f"## {nn}")
    st.markdown(f"📧 **{user.get('email','')}**  |  🎓 **{user.get('role','未选择')}**")
    if is_pro: st.success("💎 Pro 会员 · 无限搜索")
    else: st.info(f"🆓 免费用户 · 剩余 {remaining}/{FREE_SEARCH_LIMIT} 次搜索")
    st.divider()
    st.subheader("✏️ 编辑资料")
    n_e=st.text_input("邮箱",value=user.get("email",""),key="acct_email")
    n_r=st.selectbox("学术身份",["","本科","硕士","博士","博士后","教师/研究员"],
                     index=["","本科","硕士","博士","博士后","教师/研究员"].index(user.get("role","")) if user.get("role","") in ["本科","硕士","博士","博士后","教师/研究员"] else 0,
                     key="acct_role")
    cs,cc,co=st.columns(3)
    with cs:
        if st.button("💾 保存修改",use_container_width=True):
            ok,msg,u=update_profile(user["id"],role=n_r,email=n_e)
            if ok: st.session_state.user=u;st.success(msg);st.rerun()
            else: st.error(msg)
    with cc:
        if not is_pro:
            if st.button("💎 升级 Pro",use_container_width=True): st.session_state.show_pro_full=True
    with co:
        if st.button("🚪 退出登录",use_container_width=True): do_logout()
        if st.button("🔙 返回",use_container_width=True): st.session_state.show_account=False;st.rerun()
    if st.session_state.get("show_pro_full"):
        st.divider()
        st.subheader("💎 升级 Pro")
        st.markdown(f"- 🔍 无限搜索\n- 📬 订阅推送\n- 📊 高级评分\n\n**价格: ${PRO_PRICE}/永久**")
        if st.button("💳 确认升级",type="primary",use_container_width=True):
            u=upgrade_to_pro(user["id"]);st.session_state.user=u
            st.session_state.show_pro_full=False;st.success("升级成功！");st.rerun()
    st.stop()

# ============================================================
# 侧栏
# ============================================================
with st.sidebar:
    st.subheader("🎓 PaperPath")

    # Nav tabs — ▸ marks active, same size all around
    tabs=["🔍 搜索","📬 订阅","📋 历史","📢 社区"]
    for t in tabs:
        is_active = st.session_state.nav_tab==t
        btn_label = f"▸ {t}" if is_active else f"    {t}"
        if st.button(btn_label,use_container_width=True,key=f"nav_{t}"):
            st.session_state.nav_tab=t;st.rerun()

    st.divider()

    # Pro section
    if is_guest:
        st.caption("游客模式")
    elif is_pro:
        st.success("💎 Pro · 无限")
    else:
        st.info(f"🆓 剩余 {remaining}/{FREE_SEARCH_LIMIT}")
        if st.button("💎 升级 Pro",use_container_width=True): st.session_state.show_account=True;st.rerun()

    # Push username to bottom
    for _ in range(10):
        st.markdown("")

    if is_guest:
        if st.button("🔐 登录/注册",use_container_width=True): st.session_state.page="login";st.rerun()
    else:
        nn=user.get("nickname","") or user.get("username","用户")
        pro_icon="💎" if is_pro else ""
        if st.button(f"👤 {nn} {pro_icon}",use_container_width=True): st.session_state.show_account=True;st.rerun()


# ============================================================
# === Tab: 搜索 ===
# ============================================================
if st.session_state.nav_tab=="🔍 搜索":
    # Glass container for search area
    st.markdown("""<div style="padding:0 0 8px 0;">
      <h3 style="margin:0;font-size:18px;color:#1a202c;">🔬 学术探索</h3>
      <p style="color:#4a5568;font-size:14px;margin:4px 0 12px 0;">输入研究方向，发现最前沿的权威论文，AI 为你生成个性化学习路径</p>
    </div>""", unsafe_allow_html=True)

    kw_val=st.text_input("关键词",placeholder="输入研究方向，回车搜索",key="search_kw",label_visibility="collapsed")

    cf1,cf2,cf3=st.columns([1,1,2])
    with cf1:
        mode_val=st.selectbox("搜索模式",["⚡ 快速搜索","🧠 AI Agent"],label_visibility="collapsed")
    with cf2:
        cnt_val=st.select_slider("论文数量",options=list(range(1,11)),value=st.session_state.search_count)
    with cf3:
        search_btn=st.button("🔍 搜索论文",type="primary",use_container_width=True)

    if "Agent" in mode_val:
        ri_val=st.text_area("研究兴趣",placeholder="用自然语言描述你的研究兴趣…",key="ri_input",label_visibility="collapsed")

    f1,f2=st.columns(2)
    with f1:
        to=st.selectbox("📅 发表时间",["不限","近半年","近1年","近3年","自定义"],0)
    with f2:
        score_threshold=st.slider("⭐ 最低评分",0,100,0,10)

    yf_val,yt_val=None,None
    yr=datetime.now().year
    if to=="近半年": yf_val=yr if datetime.now().month>6 else yr-1
    elif to=="近1年": yf_val=yr-1
    elif to=="近3年": yf_val=yr-3
    elif to=="自定义":
        y1,y2=st.columns(2)
        with y1: yf_val=st.number_input("起",1900,yr,yr-5,1)
        with y2: yt_val=st.number_input("止",1900,yr,yr,1)

    # Execute search
    if search_btn and kw_val.strip():
        if not is_guest and not is_pro:
            allowed,_,_,_=check_search_limit(user["id"])
            if not allowed: st.warning("搜索次数用完，点击左下角用户名→升级 Pro");st.stop()
            increment_search_count(user["id"])
        st.session_state.search_mode="agent" if "Agent" in mode_val else "keyword"
        st.session_state.search_count=cnt_val
        kw=kw_val.strip()
        if st.session_state.search_mode=="agent":
            interest=ri_val.strip() or kw.strip()
            if not interest: st.warning("请输入研究兴趣或关键词")
            else:
                st.session_state.last_keyword=kw or interest[:40]
                try:
                    with st.spinner("AI Agent 规划中（超时30秒自动回退快速搜索）…"):
                        state=planner_agent({"research_interest":interest,"research_keyword":kw or interest[:40],"search_results":[],"max_total_results":cnt_val})
                        state["max_total_results"]=cnt_val;state=retrieval_agent(state)
                    results=state.get("search_results",[])
                except Exception:
                    results=search_papers(interest[:80],count=cnt_val,authoritative_only=True)
        else:
            with st.spinner(f"搜索「{kw}」…"):
                results=search_papers(kw,count=cnt_val,year_from=yf_val,year_to=yt_val,authoritative_only=True)
        st.session_state.last_keyword=kw
        st.session_state.search_results=results;st.session_state.search_offset=0
        st.session_state.seen_paper_keys=[paper_key(r) for r in results]
        batch_enrich(results)
        if not is_guest: save_search_history(user["id"],kw,results)
        st.rerun()

    if st.session_state.search_results:
        cr,cn=st.columns(2)
        with cr:
            if st.button("🔀 换一批",use_container_width=True):
                st.session_state.search_offset+=st.session_state.search_count
                with st.spinner("搜索中…"):
                    results=search_papers(st.session_state.last_keyword,count=st.session_state.search_count,
                                          year_from=yf_val,year_to=yt_val,offset=st.session_state.search_offset,
                                          authoritative_only=True,exclude_keys=set(st.session_state.seen_paper_keys))
                st.session_state.seen_paper_keys+=[paper_key(r) for r in results]
                batch_enrich(results);st.session_state.search_results=results;st.rerun()
        with cn:
            if st.button("🔄 重新搜索",use_container_width=True):
                if st.session_state.report_ready: st.session_state.confirm_new_search=True
                else: st.session_state.search_results=[];st.rerun()

    st.divider()

    # Left: selected papers | Right: results
    left,right=st.columns([1,2])

    with left:
        st.subheader(f"📋 已选（{len(st.session_state.selected_papers)}）")
        if not st.session_state.selected_papers:
            st.caption("暂无已选论文")
        else:
            st.markdown('<div class="selected-panel">', unsafe_allow_html=True)
            for i,pp in enumerate(st.session_state.selected_papers):
                ct,cx=st.columns([5,1])
                with ct:
                    st.markdown(f"**{i+1}.** {pp['title'][:45]}{'…' if len(pp['title'])>45 else ''}")
                    st.caption(f"{pp.get('year','?')} | {pp.get('authors','')[:25]}")
                with cx:
                    if st.button("❌",key=f"rm_{i}"): st.session_state.selected_papers.pop(i);st.rerun()
            st.divider()
            cg,cd=st.columns(2)
            with cg:
                if st.button("✅ 生成学习路径",type="primary",use_container_width=True):
                    st.session_state.generating=True;st.session_state.download_only=False;st.rerun()
            with cd:
                if st.button("📥 仅下载",use_container_width=True):
                    st.session_state.generating=True;st.session_state.download_only=True;st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    with right:
        if st.session_state.confirm_new_search:
            st.warning("确定清空已选论文和学习路径？")
            cc1,cc2=st.columns(2)
            with cc1:
                if st.button("确定",type="primary",use_container_width=True): reset_main();st.rerun()
            with cc2:
                if st.button("取消",use_container_width=True): st.session_state.confirm_new_search=False;st.rerun()

        elif st.session_state.generating:
            papers=st.session_state.selected_papers
            if not papers: st.warning("没有已选论文");st.session_state.generating=False
            elif st.session_state.download_only:
                status=st.empty();prog=st.progress(0);status.info("📥 下载中…")
                prog.progress(20);downloaded=batch_download(papers,max_workers=8)
                if not downloaded: st.error("下载失败");st.session_state.generating=False
                else:
                    status.info("📦 打包中…");prog.progress(80)
                    zp=create_zip(downloaded,None)
                    if zp is None: st.error("打包失败");st.session_state.generating=False
                    else:
                        status.success("✅ 完成");prog.progress(100)
                        st.session_state.generating=False;st.session_state.report_ready=True
                        st.session_state.html_path="";st.session_state.zip_path=zp
                        st.session_state.report_md="";st.session_state.downloaded=downloaded
                        if not is_guest: save_report(user["id"],st.session_state.last_keyword or "论文","",zp,len(downloaded))
                        st.rerun()
            else:
                status=st.empty();prog=st.progress(0)
                status.info("📥 下载论文 PDF…");prog.progress(20);downloaded=batch_download(papers,max_workers=8)
                status.info("🤖 AI 撰写学习路径…");prog.progress(40)
                kw=st.session_state.last_keyword or "学术论文"
                md=generate_learning_path_report(downloaded,kw)
                status.info("📄 生成 HTML…");prog.progress(75)
                hp=save_html_report(md,"learning_path")
                status.info("📦 打包…");prog.progress(90)
                zp=create_zip(downloaded,hp)
                status.success("✅ 完成！");prog.progress(100)
                st.session_state.generating=False;st.session_state.report_ready=True
                st.session_state.html_path=hp;st.session_state.zip_path=zp
                st.session_state.report_md=md;st.session_state.downloaded=downloaded
                if not is_guest: save_report(user["id"],kw,hp,zp,len(papers))
                st.rerun()

        elif st.session_state.report_ready:
            n=len(st.session_state.get("downloaded",[]))
            if st.session_state.report_md:
                st.subheader("✅ 学习路径已生成！");st.success(f"共 {n} 篇论文 + HTML 报告")
                with st.expander("📊 预览",expanded=True): st.markdown(st.session_state.report_md)
            else: st.subheader("✅ 下载完成！");st.success(f"共 {n} 篇论文")
            st.divider()
            cd,cs=st.columns(2)
            with cd:
                with open(st.session_state.zip_path,"rb") as f:
                    lb="下载全部" if st.session_state.report_md else "下载 zip"
                    st.download_button(lb,f,os.path.basename(st.session_state.zip_path),"application/zip",use_container_width=True)
            with cs:
                de=user.get("email","") if not is_guest else EMAIL_RECIPIENT
                send_to=st.text_input("收件人邮箱",value=de,key="send_email_input")
                if st.button("发送到邮箱",type="primary",use_container_width=True):
                    with st.spinner("发送中…"):
                        subj=f"[学习路径] {st.session_state.last_keyword}（{n} 篇）"
                        body=f"<h2>学习路径</h2><p><b>{n} 篇论文</b> 及报告。</p><hr><small>PaperPath</small>"
                        sent,msg=send_email(subj,body,st.session_state.zip_path,send_to)
                        if sent: st.success(f"已发送！{msg}");st.balloons()
                        else: st.warning(f"失败: {msg}")

        elif st.session_state.search_results:
            results=st.session_state.search_results
            if score_threshold>0:
                results=[r for r in results if authority_score(r,st.session_state.last_keyword)>=score_threshold]
            st.subheader(f"搜索结果 —「{st.session_state.last_keyword}」（{len(results)} 篇）")
            if score_threshold>0: st.caption(f"评分≥{score_threshold} · 原始{len(st.session_state.search_results)}→筛选{len(results)}篇")
            if not results: st.warning("无匹配论文")
            sel_ids={paper_key(p) for p in st.session_state.selected_papers}
            for i,paper in enumerate(results):
                pid=paper_key(paper);selected=pid in sel_ids
                score=authority_score(paper,st.session_state.last_keyword)
                sc="🟢" if score>=70 else ("🟡" if score>=40 else "🔴")
                with st.container(border=True):
                    c_t,c_b=st.columns([6,1])
                    with c_t: st.markdown(f"### {i+1}. {paper['title']}")
                    with c_b:
                        if selected:
                            st.success("✅")
                            if st.button("取消",key=f"desel_{i}"):
                                st.session_state.selected_papers=[p for p in st.session_state.selected_papers if paper_key(p)!=pid];st.rerun()
                        else:
                            if st.button("+",key=f"sel_{i}"): st.session_state.selected_papers.append(paper);st.rerun()
                    rv=paper.get("real_venue","") or paper.get("venue","N/A")
                    src=paper.get("venue_source","")
                    sh=f" [{src}]" if src and src!="category-whitelist" else ""
                    cites=paper.get("citation_count")
                    ct=f"📊 {cites:,} 次" if (cites is not None and cites>0) else ("📊 0 次" if cites is not None else "📊 暂无数据")
                    st.markdown(f"🏛 **{rv}**{sh} · {ct} · 📅 {paper.get('real_year',paper.get('year','N/A'))} · ✍ {paper.get('authors','N/A')[:40]}")
                    st.progress(score/100,text=f"{sc} 评分: {score}/100")
                    insight=one_line_insight(paper)
                    if insight: st.caption(f"💡 {insight}")
                    tags=paper_tags(paper)
                    if tags: st.caption(" · ".join(tags))
                    abstract=paper.get("abstract","")
                    if abstract:
                        with st.expander(f"📝 摘要 ({len(abstract)} 字)"): st.markdown(abstract)
                    aid=paper.get("arxiv_id","")
                    if aid: st.markdown(f"[📎 arXiv](https://arxiv.org/abs/{aid})")
        else:
            st.markdown("""<div style="text-align:center;padding:60px 20px">
              <div style="font-size:80px">🔍</div>
              <h2>开始学术探索之旅</h2>
              <p style="color:#888">在上方搜索框输入研究方向</p>
            </div>""",unsafe_allow_html=True)


# ============================================================
# === Tab: 订阅 ===
# ============================================================
if st.session_state.nav_tab=="📬 订阅":
    st.title("📬 论文订阅")
    st.caption("每 3 天自动搜索一次订阅关键词，推送 1 篇最新论文到邮箱。")
    st.info("⏰ 推送：每 3 天 08:00 · 每次推送 1 篇最高引用论文")
    if is_guest: st.info("订阅需要登录后使用。")
    elif not user.get("email"): st.warning("请在账户中设置邮箱。")
    else:
        sk=st.text_input("订阅关键词",key="sub_kw",placeholder="输入研究方向…")
        c1,c2=st.columns(2)
        with c1:
            if st.button("🔍 订阅",type="primary",use_container_width=True):
                if not sk.strip(): st.warning("请输入关键词")
                else:
                    ok,msg=subscribe(user["id"],sk)
                    if ok: st.success(msg)
                    else: st.warning(msg)
        with c2:
            if st.button("📋 我的订阅",use_container_width=True): st.session_state.show_subs=not st.session_state.get("show_subs",False)
        if st.session_state.get("show_subs"):
            subs=get_subscriptions(user["id"])
            if subs:
                for s in subs:
                    cc1,cc2=st.columns([4,1])
                    with cc1:
                        st.markdown(f"🔔 {s['keyword']}")
                        st.caption(f"📅 创建于 {s.get('created_at','')} · 推送至 {user['email']}")
                    with cc2:
                        if st.button("取消",key=f"unsub_{s['id']}"): unsubscribe(user["id"],s["keyword"]);st.rerun()
            else: st.caption("暂无订阅")


# ============================================================
# === Tab: 历史 ===
# ============================================================
if st.session_state.nav_tab=="📋 历史":
    st.title("📋 历史记录")
    if is_guest: st.info("历史记录需要登录后查看。")
    else:
        t1,t2,t3=st.tabs(["搜索历史","学习报告","仅下载论文"])
        with t1:
            for h in get_search_history(user["id"]): st.caption(f"🔍 {h['keyword']} — {h['created_at']}")
        with t2:
            for r in [r for r in get_reports(user["id"]) if r.get("html_path") and os.path.exists(r.get("html_path",""))]:
                st.markdown(f"📄 **{r['keyword']}** — {r['paper_count']}篇 — {r['created_at']}")
                cd1,cd2=st.columns(2)
                with cd1:
                    if os.path.exists(r.get("html_path","")):
                        with open(r["html_path"],"rb") as ff: st.download_button("📥 报告",ff,os.path.basename(r["html_path"]),"text/html",key=f"dh_{r['id']}")
                with cd2:
                    if os.path.exists(r.get("zip_path","")):
                        with open(r["zip_path"],"rb") as ff: st.download_button("📦 论文包",ff,os.path.basename(r["zip_path"]),"application/zip",key=f"dz_{r['id']}")
                st.divider()
        with t3:
            for r in [r for r in get_reports(user["id"]) if not r.get("html_path")]:
                st.markdown(f"📦 **{r['keyword']}** — {r['paper_count']}篇 — {r['created_at']}")
                if os.path.exists(r.get("zip_path","")):
                    with open(r["zip_path"],"rb") as ff: st.download_button("📥 下载",ff,os.path.basename(r["zip_path"]),"application/zip",key=f"dz_{r['id']}")
                st.divider()


# ============================================================
# === Tab: 社区（通知 + 建议反馈）===
# ============================================================
if st.session_state.nav_tab=="📢 社区":
    st.title("📢 社区")
    st.caption("最新动态 · 意见反馈 · 让 PaperPath 更好用")

    notif_col, feedback_col = st.columns([1, 1])

    with notif_col:
        st.subheader("📌 通知公告")
        notifs = [
            ("🎉", "正式上线", "2025-06-29", "PaperPath v1.0 正式发布"),
            ("📬", "订阅推送", "2025-06-28", "订阅功能上线，每 3 天推送论文"),
            ("⭐", "Pro 会员", "2025-06-27", "Pro 会员上线，无限搜索"),
            ("🔧", "评分系统", "2025-06-26", "百分制评分 + 标签系统上线"),
        ]
        for icon, title, date, desc in notifs:
            with st.container(border=True):
                st.markdown(f"**{icon} {title}**")
                st.caption(f"📅 {date} · {desc}")

    with feedback_col:
        st.subheader("💬 建议反馈")
        st.caption("每一个建议都在让 PaperPath 变得更好")
        fb_name = st.text_input("你的名字", key="fb_name", placeholder="匿名用户")
        fb_title = st.text_input("反馈标题", key="fb_title", placeholder="一句话描述…")
        fb_content = st.text_area("详细描述", key="fb_content", placeholder="请详细描述你的建议…", height=120)
        if st.button("📤 提交反馈", type="primary", use_container_width=True):
            if not fb_title.strip() or not fb_content.strip():
                st.warning("标题和详细描述不能为空")
            else:
                body = f"来自: {fb_name or '匿名'}\n标题: {fb_title}\n\n{fb_content}"
                ok, msg = _send_feedback_email(f"[PaperPath 反馈] {fb_title}", body)
                if ok: st.success(msg)
                else: st.warning(msg)
