"""
Internationalization (i18n) support for the Paper Analysis Assistant.
"""

ZH = "zh"
EN = "en"

TRANSLATIONS = {
    ZH: {
        # App title
        "app.title": "📄 AI 自动论文分析助手",
        "app.subtitle": "多智能体系统：规划师 | 搜索员 | 读者 | 写作者 | 评审员",
        "app.lang_label": "🌐 语言",

        # API key warning
        "api.warning": "⚠️ 未设置 API Key。请设置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY 环境变量。",
        "api.howto_title": "如何设置 API Key",
        "api.get_key": "获取密钥：https://platform.deepseek.com",

        # Tabs
        "tab.analysis": "分析",
        "tab.history": "历史记录",

        # Config panel
        "config.title": "配置",
        "config.keyword_label": "研究方向关键词",
        "config.keyword_placeholder": "例如：Transformer, RLHF",
        "config.keyword_hint": "用于搜索相关论文。上传的 PDF 是分析主体。",
        "config.file_label": "上传 PDF 论文",
        "config.file_hint": "必填。",
        "config.btn_run": "🚀 开始分析",
        "config.btn_run_short": "开始分析",

        # Workflow progress
        "progress.title": "工作流进度",
        "progress.running": "多智能体管道运行中...",
        "progress.starting": "正在启动...",
        "progress.done": "✅ 完成！",

        # Pipeline steps
        "step.planner": "📋 规划分析任务...",
        "step.search": "🔍 搜索相关论文...",
        "step.reader": "📖 提取论文信息...",
        "step.writer": "✍️ 生成文献综述...",
        "step.reviewer": "🔎 评审与评分...",
        "step.finalize": "✅ 最终确定报告...",

        # Status messages
        "step.writer_revision": "🔄 第 {round} 轮修改：",

        # Results
        "results.title": "📄 结果",
        "results.download_btn": "下载报告 (Markdown)",
        "results.no_report": "未生成报告。",
        "results.expander_review": "论文分析报告",
        "results.expander_refs": "参考文献",
        "results.expander_feedback": "评审反馈",
        "results.no_refs": "无参考文献",

        # History tab
        "history.title": "已保存的报告",
        "history.empty": "暂无已保存的报告。请先运行分析！",
        "history.dir_missing": "输出目录不存在。",
        "history.preview": "预览：{name}",
        "history.truncated": "...（已截断）",

        # Errors
        "error.no_keyword": "请输入研究方向关键词。",
        "error.no_file": "请上传要分析的 PDF 论文。",
        "error.empty_pdf": "PDF 文件为空或无法读取。",
        "error.pipeline": "管道错误：{error}",
        "error.pdf_loaded": "PDF 已加载：{chars} 个字符",

        # Validation
        "validate.api_key_missing": "LLM API Key 未设置。请在 .env 文件中设置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY。\n示例：DEEPSEEK_API_KEY=sk-xxxx\n获取密钥：https://platform.deepseek.com",

        # About
        "about.title": "关于",
        "about.description": "📄 **AI 自动论文分析助手**\n\n基于多智能体系统（规划师 → 搜索员 → 读者 → 写作者 → 评审员）的全自动论文分析与文献综述生成工具。",
        "about.tech": "**技术栈**\n- LangGraph (工作流编排)\n- LangChain + DeepSeek (LLM)\n- Streamlit (Web UI)\n- Semantic Scholar & arXiv (检索)\n- PyMuPDF (PDF 解析)",
        "about.github": "🔗 [GitHub 仓库](https://github.com/NewZenKoufromNWAFU/Paper-Analysis-Assistant)",
        "about.footer": "Made by BetaChen & YKMeng & ADLJ",
    },

    EN: {
        # App title
        "app.title": "📄 AI Auto Paper Analysis Assistant",
        "app.subtitle": "Multi-Agent System: Planner | Search | Reader | Writer | Reviewer",
        "app.lang_label": "🌐 Language",

        # API key warning
        "api.warning": "⚠️ API Key not set. Set DEEPSEEK_API_KEY or OPENAI_API_KEY environment variable.",
        "api.howto_title": "How to set API Key",
        "api.get_key": "Get a key: https://platform.deepseek.com",

        # Tabs
        "tab.analysis": "Analysis",
        "tab.history": "History",

        # Config panel
        "config.title": "Configuration",
        "config.keyword_label": "Research Keyword",
        "config.keyword_placeholder": "e.g., Transformer, RLHF",
        "config.keyword_hint": "Used to find related papers. The PDF is the primary subject.",
        "config.file_label": "Upload PDF Paper",
        "config.file_hint": "Required. This paper will be the focus of analysis.",
        "config.btn_run": "🚀 Start Analysis",
        "config.btn_run_short": "Start Analysis",

        # Workflow progress
        "progress.title": "Workflow Progress",
        "progress.running": "Multi-agent pipeline running...",
        "progress.starting": "Starting...",
        "progress.done": "✅ Complete!",

        # Pipeline steps
        "step.planner": "📋 Planning analysis tasks...",
        "step.search": "🔍 Searching related papers...",
        "step.reader": "📖 Extracting paper information...",
        "step.writer": "✍️ Generating literature review...",
        "step.reviewer": "🔎 Reviewing and scoring...",
        "step.finalize": "✅ Finalizing report...",

        # Status messages
        "step.writer_revision": "🔄 Revision round {round}: ",

        # Results
        "results.title": "📄 Results",
        "results.download_btn": "Download Report (Markdown)",
        "results.no_report": "No report was generated.",
        "results.expander_review": "Paper Analysis Review",
        "results.expander_refs": "References",
        "results.expander_feedback": "Review Feedback",
        "results.no_refs": "No references",

        # History tab
        "history.title": "Saved Reports",
        "history.empty": "No saved reports yet. Run an analysis first!",
        "history.dir_missing": "Output directory not found.",
        "history.preview": "Preview: {name}",
        "history.truncated": "... (truncated)",

        # Errors
        "error.no_keyword": "Please enter a research keyword.",
        "error.no_file": "Please upload a PDF paper to analyze.",
        "error.empty_pdf": "PDF appears empty or unreadable.",
        "error.pipeline": "Pipeline error: {error}",
        "error.pdf_loaded": "PDF loaded: {chars} characters",

        # Validation
        "validate.api_key_missing": "LLM API Key is not set. Please set DEEPSEEK_API_KEY or OPENAI_API_KEY in .env file.\nExample: DEEPSEEK_API_KEY=sk-xxxx\nGet a key at: https://platform.deepseek.com",

        # About
        "about.title": "About",
        "about.description": "📄 **AI Auto Paper Analysis Assistant**\n\nAn automated paper analysis and literature review generation tool powered by a multi-agent system (Planner → Search → Reader → Writer → Reviewer).",
        "about.tech": "**Tech Stack**\n- LangGraph (workflow orchestration)\n- LangChain + DeepSeek (LLM)\n- Streamlit (Web UI)\n- Semantic Scholar & arXiv (search)\n- PyMuPDF (PDF parsing)",
        "about.github": "🔗 [GitHub Repo](https://github.com/NewZenKoufromNWAFU/Paper-Analysis-Assistant)",
        "about.footer": "Made with ❤️ by AI Assistant",
    },
}


def get_text(key: str, lang: str = ZH, **kwargs) -> str:
    """Get translated text by key and language, with optional format arguments."""
    text = TRANSLATIONS.get(lang, {}).get(key, TRANSLATIONS.get(EN, {}).get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text


def get_step_text(step_name: str, lang: str = ZH) -> str:
    """Get the progress step display text."""
    key = f"step.{step_name}"
    return get_text(key, lang)


def get_lang_label(lang: str) -> str:
    return "中文" if lang == ZH else "English"
