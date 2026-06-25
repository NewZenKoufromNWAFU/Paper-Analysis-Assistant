# 更新日志

## 2026-06-24

### 1. 交互式论文搜索与学习路径生成器（commit `66a35f1`）

**重构为交互式流程：** 从一键管道改为用户主导的多次搜索 → 选择论文 → 生成报告 → 下载/发邮件。

- **app.py 完全重写** — 左栏搜索表单 + 右栏结果展示，左右分栏布局
- **论文搜索增强** — `search_papers()` 统一入口，支持 1-10 篇数量选择、年份区间过滤、Semantic Scholar + arXiv 双源合并去重
- **论文预览与选择** — 搜索结果卡片展示标题/作者/年份/期刊/摘要/引用数，可勾选加入已选篮
- **多次搜索累积** — 换关键词搜索，已选论文保留不丢失
- **权威过滤** — 后台默认仅搜索顶会/顶刊论文（NeurIPS、CVPR、Nature 等 50+ 期刊）
- **换一批翻页** — 同一关键词翻页搜索，跨批次去重
- **已选论文篮** — 左侧实时显示，可随时移除
- **学习路径报告** — LLM 生成含论文对比表的中文学习路径
- **清除 `.pyc` 缓存文件** — 从 Git 追踪中删除所有 `__pycache__/`
- **`.gitignore`** — 忽略 `.env`、缓存、输出、论文目录

---

### 2. 搜索优化 + PDF改HTML + 星级权威评分（commit `220d249`）

**PDF 中文乱码彻底解决：** 放弃所有纯 Python PDF 库，改为 HTML 输出。

- **PDF → HTML** — `report_generator.py` 重写，用 `markdown` 库渲染 HTML，内嵌 CSS 样式，浏览器打开中文完美，Ctrl+P 可另存 PDF
- **搜索超时与重试** — 超时 15s，Semantic Scholar 429 限流自动等 2s 重试，arXiv 同样加重试
- **权威性星级评分** — 1-5 星评分：顶会/顶刊 = 5 星，arXiv 预印本 = 1 星
- **期刊名提取优化** — `publicationVenue.name` → `journal.name` → `venue` 三级 fallback
- **摘要扩展** — 搜索卡片摘要从 150 字扩展到 300 字
- **隐藏 Deploy 工具栏** — `.streamlit/config.toml` 设置 `toolbarMode = "minimal"`
- **全中文界面** — 所有按钮/标签/提示改为中文
- **新搜索确认** — 有已生成报告时点重新搜索弹窗确认

---

### 3. 切换 LLM 后端（未提交）

**DeepSeek → AgnES AI**

| 配置项 | 旧值 | 新值 |
|--------|------|------|
| API Key | `DEEPSEEK_API_KEY` | `AGNES_API_KEY` |
| Base URL | `https://api.deepseek.com` | `https://apihub.agnes-ai.com/v1` |
| Model | `deepseek-chat` | `agnes-2.0-flash` |

改动文件：`.env`、`config.py`

---

## 改动文件总览

| 文件 | 今日改动 |
|------|----------|
| `app.py` | 完全重写为交互式流程 |
| `tools/academic_search.py` | 搜索统一入口、超时重试、期刊名优化 |
| `tools/report_generator.py` | PDF → HTML |
| `tools/email_sender.py` | 参数适配 HTML |
| `tools/__init__.py` | 更新导出 |
| `config.py` | 邮箱默认值 + AgnES AI 配置 |
| `.env` | 凭据更新（不提交） |
| `.gitignore` | 新增 |
| `.streamlit/config.toml` | 新增，隐藏 Deploy |
