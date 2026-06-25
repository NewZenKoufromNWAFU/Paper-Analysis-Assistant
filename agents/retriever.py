"""Retrieval Agent — lightweight orchestrator (Phase 1).

Executes each strategy sequentially, stops early when enough results
are collected, and provides per-strategy feedback.
"""

import sys
import traceback
from typing import List, Dict, Set

from state import AgentState, SearchPlan, SearchStrategy, PaperResult
from tools.academic_search import search_semantic_scholar, search_arxiv

_SOURCE_FUNCTIONS = {
    "semantic_scholar": search_semantic_scholar,
    "arxiv": search_arxiv,
}

_MIN_ENOUGH_MULTIPLIER = 3  # stop when we have 3× requested papers


def _run_one_strategy(strategy: SearchStrategy) -> List[Dict]:
    results: List[Dict] = []
    query = strategy["query"]
    count = strategy.get("count", 8)
    sources = strategy.get("sources", ["semantic_scholar"])

    for src_name in sources:
        fn = _SOURCE_FUNCTIONS.get(src_name)
        if fn is None:
            continue
        try:
            batch = fn(query, max_results=count)
            for r in batch:
                r.setdefault("source", src_name)
            results.extend(batch)
        except Exception:
            print(f"[Retriever] {src_name} failed for '{query[:50]}':", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
    return results


def _paper_key(paper: Dict) -> str:
    return (paper.get("arxiv_id") or paper.get("paper_id") or paper.get("title", "")).strip().lower()


def _merge_and_deduplicate(all_results: List[Dict], exclude_keys: Set[str]) -> List[PaperResult]:
    seen: Dict[str, PaperResult] = {}
    for r in all_results:
        key = _paper_key(r)
        if not key or key in exclude_keys:
            continue
        if key in seen:
            existing = seen[key]
            if (r.get("citation_count", 0) or 0) > (existing.get("citation_count", 0) or 0):
                seen[key] = {**existing, **r}
        else:
            seen[key] = dict(r)
    return list(seen.values())


def retrieval_agent(state: AgentState) -> AgentState:
    plan: SearchPlan = state.get("search_plan", {})
    strategies: List[SearchStrategy] = plan.get("strategies", [])
    max_results = state.get("max_total_results", 10)
    enough_threshold = max(max_results * _MIN_ENOUGH_MULTIPLIER, 10)

    if not strategies:
        query = state.get("research_keyword", "AI")
        strategies = [{
            "type": "keyword", "query": query,
            "sources": ["semantic_scholar", "arxiv"],
            "count": 10, "reason": "Fallback",
        }]

    exclude_keys: Set[str] = set(
        _paper_key(r) for r in state.get("search_results", [])
    )

    all_results: List[Dict] = []
    total = len(strategies)

    for i, strategy in enumerate(strategies):
        msg = f"[Retriever] {i+1}/{total}: {strategy.get('type','?')} -> '{strategy['query'][:60]}'"
        print(msg, file=sys.stderr)

        batch = _run_one_strategy(strategy)
        all_results.extend(batch)

        merged_so_far = _merge_and_deduplicate(all_results, exclude_keys)
        # Early termination: enough unique papers collected
        if len(merged_so_far) >= enough_threshold and i < total - 1:
            print(f"[Retriever] Enough results ({len(merged_so_far)}), stopping early", file=sys.stderr)
            break

    merged = _merge_and_deduplicate(all_results, exclude_keys)
    merged.sort(key=lambda r: r.get("citation_count", 0) or 0, reverse=True)

    state["search_results"] = merged[:max_results]
    shown = min(len(merged), max_results)
    state["status_message"] = (
        f"[Retriever] {len(merged)} unique → showing top {shown}"
    )
    print(state["status_message"], file=sys.stderr)
    return state
