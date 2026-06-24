"""LangGraph orchestration - connects all 5 agents into a workflow."""
from typing import Literal
from langgraph.graph import StateGraph, END
from state import AgentState
from agents.planner import planner_agent
from agents.search import search_agent
from agents.reader import reader_agent
from agents.writer import writer_agent
from agents.reviewer import reviewer_agent


def should_continue(state: AgentState) -> Literal["writer", "finalize"]:
    """Decide whether to revise or finalize based on reviewer feedback."""
    feedback = state.get("review_feedback", {})
    if feedback.get("needs_revision", False):
        state["revision_round"] = state.get("revision_round", 0) + 1
        return "writer"
    return "finalize"


def finalize_report(state: AgentState) -> AgentState:
    """Finalize the report into state."""
    state["final_report"] = state.get("draft_report", "")
    state["final_references"] = state.get("draft_references", "")
    state["status_message"] = "[Finalize] Report finalized successfully!"
    return state


def build_graph() -> StateGraph:
    """Build and return the compiled LangGraph workflow."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("planner", planner_agent)
    workflow.add_node("search", search_agent)
    workflow.add_node("reader", reader_agent)
    workflow.add_node("writer", writer_agent)
    workflow.add_node("reviewer", reviewer_agent)
    workflow.add_node("finalize", finalize_report)

    # Define edges
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "search")
    workflow.add_edge("search", "reader")
    workflow.add_edge("reader", "writer")
    workflow.add_edge("writer", "reviewer")

    # Conditional edge: reviewer -> writer (revise) or finalize
    workflow.add_conditional_edges(
        "reviewer",
        should_continue,
        {"writer": "writer", "finalize": "finalize"}
    )

    workflow.add_edge("finalize", END)

    return workflow.compile()


# Singleton compiled graph
_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
