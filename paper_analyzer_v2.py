"""
Paper Analyzer v2 (4-source edition)
Sources:
- OpenAlex
- Semantic Scholar
- Google Scholar
- Crossref

pip install requests scholarly habanero
"""

import requests
import statistics
from scholarly import scholarly
from habanero import Crossref
from difflib import SequenceMatcher
from datetime import datetime


class PaperAnalyzer:

    def __init__(self, title):
        self.input_title = title

        self.paper_info = {
            "title": "",
            "authors": "",
            "year": "",
            "doi": "",
            "citations": {
                "google_scholar": None,
                "semantic_scholar": None,
                "openalex": None,
                "crossref": None
            },
            "details": {
                "openalex_references": 0,
                "openalex_fwci": 0,
                "semantic_references": 0,
                "semantic_influential": 0,
                "crossref_references": 0
            },
            "trusted_citations": None
        }

    def similarity(self, a, b):
        return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

    def search_openalex_title(self):
        print("\n[1] OpenAlex标题搜索...")

        url = f"https://api.openalex.org/works?search={self.input_title}"

        data = requests.get(url, timeout=30).json()
        results = data.get("results", [])

        if not results:
            return False

        candidates = []

        for paper in results[:20]:
            score = self.similarity(
                self.input_title,
                paper.get("title", "")
            )
            candidates.append((score, paper))

        candidates.sort(reverse=True, key=lambda x: x[0])

        print("\n========== Top3候选 ==========")

        for i, (score, paper) in enumerate(candidates[:3], start=1):
            print(f"\n[{i}]")
            print("标题:", paper.get("title"))
            print("相似度:", round(score, 4))
            print("DOI:", paper.get("doi"))
            print("被引用:", paper.get("cited_by_count", 0))

        best_score, best_paper = candidates[0]

        if best_score < 0.85:
            return False

        self.paper_info["title"] = best_paper.get("title", "")
        self.paper_info["year"] = best_paper.get("publication_year", "")

        doi = best_paper.get("doi")
        if doi:
            doi = doi.replace("https://doi.org/", "")
            self.paper_info["doi"] = doi

        self.paper_info["citations"]["openalex"] = \
            best_paper.get("cited_by_count", 0)

        self.paper_info["details"]["openalex_references"] = \
            best_paper.get("referenced_works_count", 0)

        self.paper_info["details"]["openalex_fwci"] = \
            best_paper.get("fwci", 0)

        return True

    def verify_doi(self):
        doi = self.paper_info["doi"]

        if not doi:
            return False

        print("\n[2] DOI验证...")

        url = f"https://api.openalex.org/works?filter=doi:{doi}"

        data = requests.get(url, timeout=30).json()

        results = data.get("results", [])

        if not results:
            return False

        paper = results[0]

        score = self.similarity(
            self.input_title,
            paper["title"]
        )

        print("验证标题:", paper["title"])
        print("相似度:", round(score, 4))

        return score > 0.90

    def get_semantic_scholar(self):
        doi = self.paper_info["doi"]
        if not doi:
            return

        print("\n[3] Semantic Scholar...")

        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
        )

        params = {
            "fields":
            "title,citationCount,referenceCount,influentialCitationCount"
        }

        try:
            data = requests.get(
                url,
                params=params,
                timeout=30
            ).json()

            self.paper_info["citations"]["semantic_scholar"] = \
                data.get("citationCount", 0)

            self.paper_info["details"]["semantic_references"] = \
                data.get("referenceCount", 0)

            self.paper_info["details"]["semantic_influential"] = \
                data.get("influentialCitationCount", 0)

            print("被引用:", data.get("citationCount", 0))

        except Exception as e:
            print(e)

    def get_google_scholar(self):
        print("\n[4] Google Scholar...")

        try:
            search = scholarly.search_pubs(self.input_title)
            paper = next(search)

            score = self.similarity(
                self.input_title,
                paper["bib"]["title"]
            )

            print("匹配标题:", paper["bib"]["title"])
            print("相似度:", round(score, 4))

            if score < 0.85:
                return

            self.paper_info["citations"]["google_scholar"] = \
                paper.get("num_citations", 0)

            self.paper_info["authors"] = ", ".join(
                paper["bib"].get("author", [])
            )

            print("被引用:", paper.get("num_citations", 0))

        except Exception as e:
            print(e)

    def get_crossref(self):
        doi = self.paper_info["doi"]

        if not doi:
            return

        print("\n[5] Crossref...")

        try:
            cr = Crossref()
            work = cr.works(ids=doi)

            msg = work["message"]

            self.paper_info["citations"]["crossref"] = \
                msg.get("is-referenced-by-count", 0)

            self.paper_info["details"]["crossref_references"] = \
                msg.get("reference-count", 0)

            print(
                "被引用:",
                self.paper_info["citations"]["crossref"]
            )

        except Exception as e:
            print(e)

    def calculate_trusted_citations(self):

        values = [
            v for v in self.paper_info["citations"].values()
            if v is not None
        ]

        if not values:
            return 0

        if len(values) == 1:
            return values[0]

        median = statistics.median(values)

        filtered = []

        for v in values:

            if median == 0:
                filtered.append(v)

            elif v <= median * 5:
                filtered.append(v)

        trusted = round(sum(filtered) / len(filtered))

        self.paper_info["trusted_citations"] = trusted

        return trusted

    def sync_status(self):

        vals = [
            v for v in self.paper_info["citations"].values()
            if v is not None
        ]

        if len(vals) < 2:
            return "未知"

        mx = max(vals)
        mn = min(vals)

        if mn == 0 and mx <= 2:
            return "部分数据库尚未同步"

        if mn > 0 and mx / mn > 10:
            return "可能存在错误匹配"

        return "同步正常"

    def print_report(self):

        trusted = self.calculate_trusted_citations()

        print("\n" + "=" * 50)
        print("综合结果")
        print("=" * 50)

        for k, v in self.paper_info["citations"].items():
            print(f"{k:20}: {v}")

        print("\n可信引用数:", trusted)
        print("同步状态:", self.sync_status())

        print("\nOpenAlex参考文献:",
              self.paper_info["details"]["openalex_references"])

        print("OpenAlex FWCI:",
              self.paper_info["details"]["openalex_fwci"])

        print("Semantic参考文献:",
              self.paper_info["details"]["semantic_references"])

        print("Semantic影响力引用:",
              self.paper_info["details"]["semantic_influential"])

        print("Crossref参考文献:",
              self.paper_info["details"]["crossref_references"])

    def save_markdown(self):

        md = f"""# Paper Analysis Report

Generated: {datetime.now()}

## Title
{self.paper_info['title']}

## DOI
{self.paper_info['doi']}

## Authors
{self.paper_info['authors']}

## Year
{self.paper_info['year']}

## Citations

| Source | Citations |
|----------|----------|
| Google Scholar | {self.paper_info['citations']['google_scholar']} |
| Semantic Scholar | {self.paper_info['citations']['semantic_scholar']} |
| OpenAlex | {self.paper_info['citations']['openalex']} |
| Crossref | {self.paper_info['citations']['crossref']} |

## Trusted Citations

{self.paper_info['trusted_citations']}

## Details

- OpenAlex References: {self.paper_info['details']['openalex_references']}
- OpenAlex FWCI: {self.paper_info['details']['openalex_fwci']}
- Semantic References: {self.paper_info['details']['semantic_references']}
- Semantic Influential: {self.paper_info['details']['semantic_influential']}
- Crossref References: {self.paper_info['details']['crossref_references']}
"""

        with open("paper_report.md", "w", encoding="utf-8") as f:
            f.write(md)

    def run(self):

        if not self.search_openalex_title():
            print("OpenAlex匹配失败")
            return

        if not self.verify_doi():
            print("DOI验证失败")
            return

        self.get_semantic_scholar()
        self.get_google_scholar()
        self.get_crossref()

        self.print_report()
        self.save_markdown()

        print("\n报告已保存: paper_report.md")


if __name__ == "__main__":
    title = input("请输入论文标题:\\n").strip()
    analyzer = PaperAnalyzer(title)
    analyzer.run()
