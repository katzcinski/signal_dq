"""Data-Analysis / Profiling für dq_core (framework-free, aggregate-only)."""
from .profiler import build_issues, build_profiling, profile_table
from .pk_detection import analyze_composite_candidates, rank_single_candidates
from .heuristics import (
    classify_view_context,
    enrich_result_with_context,
    score_composite_candidate,
    score_single_candidate,
)

__all__ = [
    "profile_table",
    "build_profiling",
    "build_issues",
    "rank_single_candidates",
    "analyze_composite_candidates",
    "classify_view_context",
    "score_single_candidate",
    "score_composite_candidate",
    "enrich_result_with_context",
]
