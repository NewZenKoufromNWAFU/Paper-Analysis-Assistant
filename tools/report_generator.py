"""Report generation tools — styled HTML output with browser-native CJK rendering."""
import os
import re
from datetime import datetime
from config import OUTPUT_DIR


def _md_to_html(md_content: str = "", title: str = "学习路径报告") -> str:
    """Convert Markdown to a self-contained styled HTML document.

    Uses Python's markdown library for reliable conversion, then wraps in a
    print-friendly HTML page with embedded CSS.  No external PDF library needed —
    the browser renders Chinese perfectly.
    """
    try:
        import markdown as md_lib
        body = md_lib.markdown(
            md_content,
            extensions=["tables", "fenced_code", "codehilite"],
        )
    except ImportError:
        # Fallback: basic line-by-line conversion
        body = md_content.replace("\n", "<br>\n")
        body = re.sub(r'^### (.+)$', r'<h3>\1</h3>', body, flags=re.M)
        body = re.sub(r'^## (.+)$', r'<h2>\1</h2>', body, flags=re.M)
        body = re.sub(r'^# (.+)$', r'<h1>\1</h1>', body, flags=re.M)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  @page {{ size: A4; margin: 18mm 20mm; }}
  @media print {{
    body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
  body {{
    font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "SimHei", sans-serif;
    font-size: 15px; line-height: 1.8; color: #222;
    max-width: 820px; margin: 0 auto; padding: 24px 20px;
  }}
  h1 {{ font-size: 28px; color: #1a5276; border-bottom: 3px solid #2980b9; padding-bottom: 8px; margin-top: 28px; }}
  h2 {{ font-size: 20px; color: #2471a3; border-bottom: 2px solid #aed6f1; padding-bottom: 5px; margin-top: 24px; }}
  h3 {{ font-size: 17px; color: #2e86c1; margin-top: 18px; }}
  p {{ margin: 8px 0; }}
  ul, ol {{ margin: 6px 0 6px 24px; }}
  li {{ margin: 3px 0; }}
  a {{ color: #2980b9; }}
  strong {{ color: #1a5276; }}
  code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 13px; font-family: Consolas, "Courier New", monospace; }}
  pre {{ background: #f7f7f7; border: 1px solid #ddd; border-radius: 6px; padding: 14px; overflow-x: auto; font-size: 13px; line-height: 1.5; }}
  pre code {{ background: none; padding: 0; }}
  blockquote {{
    border-left: 4px solid #3498db; padding: 8px 16px; margin: 12px 0;
    color: #555; background: #f8fafc; border-radius: 0 6px 6px 0;
  }}
  table {{ border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 14px; }}
  th {{ background: #eaf2f8; color: #1a5276; padding: 9px 12px; text-align: left; border: 1px solid #c5d5e5; font-weight: bold; }}
  td {{ padding: 8px 12px; border: 1px solid #ddd; }}
  tr:nth-child(even) td {{ background: #f9fbfd; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 24px 0; }}
  .report-footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #ddd; color: #999; font-size: 12px; text-align: center; }}
</style>
</head>
<body>
{body}
<div class="report-footer">
  <p>由论文学习路径生成器自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
  <p>在浏览器中打开此文件，按 Ctrl+P 可另存为 PDF</p>
</div>
</body>
</html>"""


def save_html_report(content: str, filename_prefix: str = "learning_path") -> str:
    """Convert Markdown → self-contained styled HTML file.

    Returns absolute path to the generated HTML file.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    html = _md_to_html(content)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    return filepath


def save_markdown_report(content: str, filename_prefix: str = "report") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath
