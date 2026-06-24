"""Report generation tools."""
import os
import re
from datetime import datetime
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from config import OUTPUT_DIR

# A4 尺寸 (mm)
A4_W = 210
A4_H = 297
MARGIN = 18

# 中文字体文件自动探测
_FONT_PATH = None
for _candidate in [
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]:
    if os.path.exists(_candidate):
        _FONT_PATH = _candidate
        break


def _get_font() -> str:
    return _FONT_PATH or "Helvetica"


class _MarkdownPDF(FPDF):
    """Minimal Markdown-to-PDF renderer using fpdf2 with CJK font."""

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(True, MARGIN)
        font_path = _get_font()
        if font_path != "Helvetica":
            self.add_font("CJK", "", font_path)
            self.add_font("CJK", "B", font_path)  # fpdf2 will fake bold
        self._font_name = "CJK" if font_path != "Helvetica" else "Helvetica"
        self._w = A4_W - 2 * MARGIN

    def render(self, md_text: str):
        self.add_page()
        lines = md_text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            # Code block
            if line.strip().startswith("```"):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # skip closing ```
                self._render_code("\n".join(code_lines))
                self.ln(4)
                continue
            # Table (starts with | and followed by |---|)
            if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r'^\|[\s\-:|]+\|', lines[i + 1].strip()):
                rows, i = self._parse_table(lines, i)
                self._render_table(rows)
                self.ln(4)
                continue
            # Headers
            m = re.match(r'^(#{1,4})\s+(.+)$', line)
            if m:
                level = len(m.group(1))
                self._render_heading(m.group(2), level)
                i += 1
                continue
            # Blockquote
            if line.strip().startswith("> "):
                quote_lines = []
                while i < len(lines) and lines[i].strip().startswith("> "):
                    quote_lines.append(lines[i].strip()[2:])
                    i += 1
                self._render_quote(" ".join(quote_lines))
                continue
            # Horizontal rule
            if re.match(r'^[-*_]{3,}\s*$', line.strip()):
                self._render_hr()
                i += 1
                continue
            # Unordered list
            if re.match(r'^\s*[-*+]\s+', line):
                while i < len(lines) and re.match(r'^\s*[-*+]\s+', lines[i]):
                    self._render_list_item(re.sub(r'^\s*[-*+]\s+', '', lines[i]))
                    i += 1
                self.ln(2)
                continue
            # Ordered list
            if re.match(r'^\s*\d+[.)]\s+', line):
                n = 1
                while i < len(lines) and re.match(r'^\s*\d+[.)]\s+', lines[i]):
                    self._render_list_item(f"{n}. {re.sub(r'^\s*\d+[.)]\s+', '', lines[i])}")
                    i += 1
                    n += 1
                self.ln(2)
                continue
            # Empty line
            if not line.strip():
                self.ln(4)
                i += 1
                continue
            # Paragraph
            para_lines = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(("#", "|", "```", "> ", "- ", "* ", "1.")):
                para_lines.append(lines[i])
                i += 1
            self._render_para(" ".join(para_lines))
        return self

    def _render_heading(self, text: str, level: int):
        text = self._clean_md(text)
        sizes = {1: 20, 2: 15, 3: 12, 4: 11}
        size = sizes.get(level, 11)
        self.set_font(self._font_name, "B", size)
        self.set_y(self.get_y() + 3)
        self.multi_cell(self._w, size * 0.45, text, align="L")
        if level <= 2:
            y = self.get_y()
            self.set_draw_color(41, 128, 185)
            w = 60 if level == 1 else 30
            self.line(MARGIN, y + 1, MARGIN + w, y + 1)
            self.ln(5)
        else:
            self.ln(3)

    def _render_para(self, text: str):
        text = self._clean_md(text)
        if not text.strip():
            return
        self.set_font(self._font_name, "", 10)
        self.multi_cell(self._w, 5.5, text, align="L")
        self.ln(2)

    def _render_code(self, code: str):
        self.set_fill_color(248, 248, 248)
        self.set_draw_color(200, 200, 200)
        self.set_font("Courier", "", 8)
        lines = code.split("\n")
        h = len(lines) * 4.5 + 5
        if self.get_y() + h > A4_H - MARGIN:
            self.add_page()
        y0 = self.get_y()
        self.rect(MARGIN, y0, self._w, h, "FD")
        self.set_xy(MARGIN + 2, y0 + 2)
        for ln in lines:
            self.cell(self._w - 4, 4.5, ln[:90], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_y(y0 + h + 3)

    def _render_table(self, rows: list):
        if not rows:
            return
        self.set_font(self._font_name, "", 9)
        col_w = self._w / max(len(rows[0]), 1)
        # Check if table fits on current page
        needed = len(rows) * 6 + 8
        if self.get_y() + needed > A4_H - MARGIN:
            self.add_page()
        for ri, row in enumerate(rows):
            is_header = ri == 0
            if is_header:
                self.set_font(self._font_name, "B", 9)
                self.set_fill_color(234, 242, 248)
            else:
                self.set_font(self._font_name, "", 9)
                self.set_fill_color(255, 255, 255)
            for ci, cell in enumerate(row):
                self.set_draw_color(200, 200, 200)
                self.rect(MARGIN + ci * col_w, self.get_y(), col_w, 6, "DF")
                self.set_xy(MARGIN + ci * col_w + 1, self.get_y() + 0.5)
                text = self._clean_md(cell.strip())[:40]
                self.cell(col_w - 2, 5, text)
            self.ln()

    def _render_quote(self, text: str):
        text = self._clean_md(text)
        self.set_font(self._font_name, "", 10)
        self.set_text_color(80, 80, 80)
        x0 = self.get_x()
        self.set_draw_color(52, 152, 219)
        self.set_line_width(0.6)
        self.line(MARGIN, self.get_y() + 1, MARGIN + 1.5, self.get_y() + 1)
        self.set_x(MARGIN + 4)
        self.multi_cell(self._w - 4, 5.5, text, align="L")
        self.set_text_color(34, 34, 34)
        self.ln(3)

    def _render_hr(self):
        self.set_draw_color(200, 200, 200)
        self.line(MARGIN, self.get_y() + 2, MARGIN + self._w, self.get_y() + 2)
        self.ln(5)

    def _render_list_item(self, text: str):
        text = self._clean_md(text)
        self.set_font(self._font_name, "", 10)
        bullet = text[:text.index(" ") + 1] if " " in text else "- "
        content = text[len(bullet):] if " " in text else text
        self.set_x(MARGIN + 5)
        self.cell(4, 5.5, bullet.strip())
        self.multi_cell(self._w - 9, 5.5, content, align="L")

    def _clean_md(self, text: str) -> str:
        """Strip markdown formatting tokens, keep only readable content."""
        # Bold/italic
        text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)
        text = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)
        # Inline code
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # Links: [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Images: ![alt](url) -> remove
        text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)
        # HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        return text.strip()

    def _parse_table(self, lines, start_idx):
        rows = []
        i = start_idx
        while i < len(lines) and lines[i].strip().startswith("|"):
            row = [c.strip() for c in lines[i].strip().split("|")[1:-1]]
            if not re.match(r'^[\s\-:]+$', "".join(row)):
                rows.append(row)
            i += 1
        return rows, i


def save_pdf_report(content: str, filename_prefix: str = "learning_path") -> str:
    """Convert Markdown report to a PDF with proper Chinese font rendering.

    Returns:
        Absolute path to the generated PDF file.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.pdf"
    filepath = os.path.join(OUTPUT_DIR, filename)

    pdf = _MarkdownPDF()
    pdf.render(content)
    pdf.output(filepath)
    return filepath


def save_markdown_report(content: str, filename_prefix: str = "report") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


def build_report_markdown(
    research_direction: str,
    primary_paper: dict,
    search_results: list,
    draft_report: str,
    draft_references: str,
    review_feedback: dict = None,
) -> str:
    paper_title = primary_paper.get("title", "Unknown Paper")
    lines = []
    lines.append(f"# Paper Analysis: {paper_title}")
    lines.append(f"")
    lines.append(f"> **Research Context:** {research_direction}")
    lines.append(f"> **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    if primary_paper:
        lines.append("## Paper Metadata")
        lines.append(f"- **Title:** {primary_paper.get('title', 'N/A')}")
        lines.append(f"- **Authors:** {primary_paper.get('authors', 'N/A')}")
        lines.append(f"- **Year:** {primary_paper.get('year', 'N/A')}")
        lines.append(f"- **Venue:** {primary_paper.get('venue', 'N/A')}")
        lines.append(f"- **Keywords:** {', '.join(primary_paper.get('keywords', []))}")
        lines.append(f"")
        lines.append(f"### Abstract")
        lines.append(f"{primary_paper.get('abstract', 'N/A')}")
        lines.append("")

    lines.append("## Analysis Review")
    lines.append(draft_report)
    lines.append("")

    lines.append("---")
    lines.append("## References")
    lines.append(draft_references)
    lines.append("")

    if review_feedback:
        lines.append("---")
        lines.append("## Review Feedback")
        lines.append(f"- **Overall Score:** {review_feedback.get('score', 'N/A')}/10")
        for k in ["completeness", "accuracy", "structure", "suggestions"]:
            if review_feedback.get(k):
                lines.append(f"- **{k.capitalize()}:** {review_feedback[k]}")
        lines.append("")

    lines.append("")
    lines.append("---")
    lines.append("*Generated by AI Multi-Agent Paper Analysis System*")
    return "\n".join(lines)
