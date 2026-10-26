"""Aggregate actual scores without hiding failures or missing results."""

from collections import Counter
from collections.abc import Iterable

from .models import EvalResult, ResultStatus


def aggregate_results(results: Iterable[EvalResult]) -> dict:
    values = list(results)
    counts = Counter(r.status.value for r in values)
    scores = [r.score for r in values if r.score is not None]
    return {"total": len(values), "states": {s.value: counts[s.value] for s in ResultStatus},
            "scored_count": len(scores), "mean_score": sum(scores) / len(scores) if scores else None}


def from_legacy_metric(result, *, threshold: float | None = None) -> EvalResult:
    """Bridge existing quality metrics, keeping operational errors unscored."""
    status = getattr(result, "status", None)
    if status is None:
        status = "skipped" if result.skipped else ("not_applicable" if result.score is None else "passed")
    if status == "passed" and threshold is not None and result.score < threshold:
        status = "failed"
    return EvalResult(name=result.name, status=status, score=result.score,
                      reason=result.reason or ("metric has no applicable score" if result.score is None else ""),
                      breakdown=result.breakdown, trace_refs=getattr(result, "trace_refs", []))
