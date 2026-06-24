"""
LangGraph state definition for the Multi-Agent Paper Analysis System.
"""

from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langgraph.graph.message import add_messages
import operator


class PaperInfo(TypedDict, total=False):
    """Structured info extracted from a paper."""
    title: str
    authors: str
    year: str
    venue: str
    abstract: str
    methodology: str
    contributions: str
    limitations: str
    keywords: List[str]


class SearchResult(TypedDict, total=False):
    """Result from academic search."""
    title: str
    authors: str
    year: str
    venue: str
    abstract: str
    url: str
    citation_count: int


class ReviewFeedback(TypedDict, total=False):
    """Reviewer's feedback on the generated report."""
    score: float
    completeness: str
    accuracy: str
    structure: str
    suggestions: str
    needs_revision: bool


class AgentState(TypedDict, total=False):
    """Shared state flowing through the LangGraph."""
    # Input
    research_direction: str
    pdf_file_path: Optional[str]
    pdf_text: Optional[str]

    # Planner output
    task_plan: List[Dict[str, str]]
    search_keywords: List[str]

    # Search output
    search_results: List[SearchResult]

    # Reader output
    primary_paper: Optional[PaperInfo]
    related_papers_summary: List[str]

    # Writer output
    draft_report: str
    draft_references: str

    # Reviewer output
    review_feedback: Optional[ReviewFeedback]
    final_report: str
    final_references: str

    # Flow control
    revision_round: int
    error: Optional[str]
    status_message: str

