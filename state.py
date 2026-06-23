"""Agent state definitions for the Academic Learning Path System."""

from typing import TypedDict, List, Dict, Optional


class PaperMeta(TypedDict, total=False):
    """Metadata for a downloaded paper."""
    title: str
    authors: str
    year: str
    venue: str
    abstract: str
    url: str
    arxiv_id: str
    citation_count: int
    local_path: str
    page_count: int


class RankedPaper(TypedDict, total=False):
    """A paper with difficulty ranking and learning recommendation."""
    title: str
    authors: str
    year: str
    arxiv_id: str
    local_path: str
    difficulty_score: float
    difficulty_label: str
    reason: str
    learning_goal: str
    prerequisite: str
    estimated_hours: float
    key_sections: str
    algorithm_improvement: str
    benchmark_data: str


class AgentState(TypedDict, total=False):
    # Input
    research_keyword: str
    email_recipient: str

    # Planner output
    search_queries: List[str]

    # Search output
    search_results: List[Dict]

    # Downloader output
    downloaded_papers: List[PaperMeta]

    # Reader output
    paper_analyses: List[Dict]

    # Ranker output
    ranked_papers: List[RankedPaper]

    # Writer output
    learning_path_report: str
    zip_path: str

    # Flow control
    error: Optional[str]
    status_message: str
