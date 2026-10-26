import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from evals.framework.gates import required_metrics_complete
from evals.framework.models import EvalResult
from evals.framework.constraints import json_values_equal
from evals.framework.results import aggregate_results, from_legacy_metric
from evals.quality_eval.base import BaseMetric, EvalSample, MetricResult
from evals.quality_eval.suite import evaluate
from evals.quality_eval.metrics import evaluate_report, is_skipped


@pytest.mark.parametrize("left,right,expected", [
    (True, 1, False), ({"flags": [True]}, {"flags": [1]}, False),
    ({"flags": [False]}, {"flags": [False]}, True), (1, 1.0, True),
])
def test_json_constraint_equality_preserves_types(left, right, expected):
    assert json_values_equal(left, right) is expected


def test_failed_scores_remain_in_denominator_and_errors_are_counted():
    results = [EvalResult(name="m", status="passed", score=1),
               EvalResult(name="m", status="failed", score=0),
               EvalResult(name="m", status="error", reason="broken"),
               EvalResult(name="m", status="skipped", reason="disabled")]
    summary = aggregate_results(results)
    assert summary["scored_count"] == 2
    assert summary["mean_score"] == 0.5
    assert summary["states"]["error"] == summary["states"]["skipped"] == 1


def test_missing_and_skipped_required_results_block_gate():
    assert not required_metrics_complete({}, {"citation"})
    assert not required_metrics_complete({"citation": "skipped"}, {"citation"})
    assert required_metrics_complete({"citation": "failed"}, {"citation"})


def test_no_scores_are_not_a_perfect_result():
    assert aggregate_results([])["mean_score"] is None


def test_metric_exception_is_error_and_legacy_skipped_remains_compatible():
    class BrokenMetric(BaseMetric):
        name, group, aligned_with = "broken", "test", "test"

        async def measure(self, sample, grader_model=None):
            raise RuntimeError("broken judge")

    result = asyncio.run(evaluate(EvalSample(), [BrokenMetric()]))[0]
    assert result.status == "error"
    assert result.skipped  # Legacy callers still receive no score.
    adapted = from_legacy_metric(result)
    assert adapted.status == "error" and adapted.score is None
    assert "broken judge" in adapted.reason
    assert from_legacy_metric(MetricResult("m", "g", "a", skipped=True, reason="disabled")).status == "skipped"


def test_legacy_dict_preserves_error_status(monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("metric failed")

    monkeypatch.setattr("evals.quality_eval.metrics.source_authority", broken)
    outcome = asyncio.run(evaluate_report("report", [], "", "query", None,
                                          run_subtopic=False, run_unsupported=False))["source_authority"]
    assert outcome["status"] == "error"
    assert is_skipped(outcome)  # Old consumers still know this has no numeric score.


@pytest.mark.parametrize("metric_name", ["SubtopicCoverageMetric", "UnsupportedClaimMetric", "SourceAuthorityMetric"])
def test_real_judge_exception_becomes_error_not_skip(metric_name):
    from evals.quality_eval import suite

    grader = AsyncMock()
    grader.ainvoke.side_effect = RuntimeError("judge is unavailable")
    sample = EvalSample(report="r", context="c", sources=["https://obscuresite.io/a"])
    outcome = asyncio.run(suite.evaluate(sample, [getattr(suite, metric_name)()], grader))[0]
    assert outcome.status == "error"
    assert from_legacy_metric(outcome).status == "error"
    assert outcome.score is None


@pytest.mark.parametrize("metric_name,first_response", [
    ("SubtopicCoverageMetric", '["topic"]'),
    ("UnsupportedClaimMetric", '["claim"]'),
])
def test_per_item_judge_failure_is_not_a_quality_score(metric_name, first_response):
    from evals.quality_eval import suite

    grader = AsyncMock()
    grader.ainvoke.side_effect = [SimpleNamespace(content=first_response), RuntimeError("judge failed")]
    outcome = asyncio.run(suite.evaluate(EvalSample(report="r", context="c"), [getattr(suite, metric_name)()], grader))[0]
    assert outcome.status == "error" and outcome.score is None
    assert "judge failed" in str(outcome.breakdown)
