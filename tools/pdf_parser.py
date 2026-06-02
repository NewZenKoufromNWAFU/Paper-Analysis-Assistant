"""
PDF parsing tools using PyMuPDF.
Extracts full text and structured paper information.
"""

import fitz  # PyMuPDF
import os
import json
from typing import Optional, Callable


def parse_pdf(file_path: str) -> str:
    """Extract all text from a PDF file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    doc = fitz.open(file_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()
    return full_text


def extract_paper_info(full_text: str, llm_call: Callable, title_hint: str = "") -> dict:
    """Use LLM to extract structured info from PDF text."""
    text_sample = full_text[:12000] if len(full_text) > 12000 else full_text

    prompt = f"""你是一个学术论文信息提取专家。请从以下论文文本中提取关键信息，以JSON格式返回。

{{
  "title": "论文标题",
  "authors": "作者列表",
  "year": "发表年份",
  "abstract": "摘要(中文)",
  "methodology": "研究方法/技术路线",
  "contributions": "主要贡献和创新点",
  "limitations": "局限性",
  "keywords": ["关键词1", "关键词2"]
}}

论文标题提示: {title_hint}

论文文本片段:
---
{text_sample}
---

只返回JSON，不要多余文字。"""

    response = llm_call(prompt)
    return _parse_json_response(response)


def _parse_json_response(response: str) -> dict:
    """Parse JSON from LLM response, handling code blocks."""
    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) > 2:
            text = "\n".join(lines[1:-1])
        elif lines[0].startswith("```"):
            text = lines[0][3:].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {
            "title": "",
            "authors": "",
            "year": "",
            "abstract": "",
            "methodology": "",
            "contributions": "",
            "limitations": "",
            "keywords": [],
            "note": "Failed to parse structured info"
        }

