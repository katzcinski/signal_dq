# Anomaly-Miner / Proposal generator (WS5-2)
# [PII-GATE] only aggregate statistics are processed — no raw row reads
from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..store.sqlite_store import ResultStore

WARMUP_MIN_SAMPLES = 10
FULL_CONFIDENCE_SAMPLES = 30


def proposal_id(product: str, check_name: str, proposed_expect: str) -> str:
    """W-3: deterministische ID aus product × check × proposed_expect.

    Ein Re-Mining derselben Basis liefert dieselbe ID — so überleben Steward-
    Entscheidungen (accept/reject/snooze) Neustarts und Accept/Reject laufen
    nicht mehr auf 404, wenn zwischen Listing und Klick neu gemint wird. Ändert
    sich der Vorschlag inhaltlich, ist es bewusst ein anderer Proposal."""
    raw = f"{product}\x1f{check_name}\x1f{proposed_expect}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@dataclass
class Proposal:
    id: str
    product: str
    check_name: str
    current_expect: str
    proposed_expect: str
    rationale: str
    confidence: float
    stats: dict[str, Any] = field(default_factory=dict)
    status: str = "open"
    created_at: str = ""
    kind: str = "internal_gate"


class ProposalMiner:
    def __init__(self, store: "ResultStore") -> None:
        self._store = store

    def mine(
        self,
        dataset: str,
        current_expects: dict[str, str] | None = None,
        *,
        kind: str = "internal_gate",
    ) -> list[Proposal]:
        """Analyse history and generate proposals for tighter expectations."""
        proposals: list[Proposal] = []
        current_expects = current_expects or {}

        # Collect all check names for this dataset
        all_runs = self._store.get_runs(dataset, limit=200)
        if not all_runs:
            return []

        # Get unique check names from the latest run
        latest = self._store.get_run(all_runs[0]["run_id"])
        if not latest:
            return []

        check_names = [r["check_name"] for r in latest.get("results", [])]

        for check_name in check_names:
            history = self._store.get_check_history(dataset, check_name, limit=50)
            actuals = [
                float(h["actual_value"])
                for h in history
                if h.get("actual_value") is not None
                and _is_numeric(h["actual_value"])
            ]
            if len(actuals) < WARMUP_MIN_SAMPLES:
                continue  # not enough data for proposal

            stats = _compute_stats(actuals)
            confidence = min(len(actuals) / FULL_CONFIDENCE_SAMPLES, 1.0)

            # Propose BETWEEN p01 AND p99
            proposed = f"BETWEEN {stats['p01']:.2f} AND {stats['p99']:.2f}"
            current = current_expects.get(check_name, "")

            if proposed == current:
                continue

            rationale = (
                f"Based on {len(actuals)} runs: "
                f"min={stats['min']:.2f}, max={stats['max']:.2f}, "
                f"mean={stats['mean']:.2f}, stddev={stats['stddev']:.2f}, "
                f"p01={stats['p01']:.2f}, p99={stats['p99']:.2f}"
            )
            proposals.append(
                Proposal(
                    id=proposal_id(dataset, check_name, proposed),
                    product=dataset,
                    check_name=check_name,
                    current_expect=current,
                    proposed_expect=proposed,
                    rationale=rationale,
                    confidence=confidence,
                    stats=stats,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    kind=kind,
                )
            )

        return proposals


def _is_numeric(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _compute_stats(values: list[float]) -> dict[str, float]:
    sorted_v = sorted(values)
    n = len(sorted_v)

    def percentile(p: float) -> float:
        idx = (p / 100) * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        return sorted_v[lo] + (idx - lo) * (sorted_v[hi] - sorted_v[lo])

    mean = statistics.mean(values)
    stddev = statistics.stdev(values) if n > 1 else 0.0

    return {
        "n": n,
        "min": sorted_v[0],
        "max": sorted_v[-1],
        "mean": mean,
        "stddev": stddev,
        "p01": percentile(1),
        "p99": percentile(99),
    }
