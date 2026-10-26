import math

import pytest
from pydantic import ValidationError

from evals.framework.models import AgentCase, EvalBudget, EvalResult, TaskCase


def task_data():
    return dict(case_id="t1", dataset_version="1", split="dev", group_id="g1",
                query="Compare the plans", as_of="2026-10-01", source_bundle="b1",
                replay_key="t1", requirements=[{"id": "r1", "text": "Compare costs"}],
                gold_facts=[{"id": "f1", "fact": "A costs 10"}], gold_evidence=["e1"])


def test_task_input_does_not_expose_grading_labels():
    case = TaskCase(**task_data())
    visible = case.agent_input()
    assert visible["query"] == case.query
    assert set(visible) == {"query", "as_of", "report_type", "source_policy", "budget"}
    assert "gold_facts" not in visible and "requirements" not in visible


def test_node_input_is_copied_and_gold_is_private():
    case = AgentCase(case_id="a1", dataset_version="1", split="dev", group_id="g1",
                     node_kind="planner", input_artifact={"query": "q"},
                     replay_key="a1", source_bundle="b1",
                     expected_constraints={"required_keys": ["sections"]}, gold_output_refs=["e1"])
    visible = case.agent_input()
    visible["input_artifact"]["query"] = "changed"
    assert case.input_artifact == {"query": "q"}
    assert "expected_constraints" not in visible and "gold_output_refs" not in visible


@pytest.mark.parametrize("score", [math.nan, math.inf, -0.1, 1.1])
def test_scores_must_be_finite_and_normalized(score):
    with pytest.raises(ValidationError):
        EvalResult(name="m", status="passed", score=score)


@pytest.mark.parametrize("status", ["error", "skipped", "not_applicable"])
def test_unscored_states_cannot_carry_scores(status):
    with pytest.raises(ValidationError):
        EvalResult(name="m", status=status, score=1, reason="unavailable")
    assert EvalResult(name="m", status=status, reason="unavailable").score is None


def test_scored_states_require_score_and_unscored_states_require_reason():
    with pytest.raises(ValidationError):
        EvalResult(name="m", status="passed")
    with pytest.raises(ValidationError):
        EvalResult(name="m", status="error")


def test_empty_query_and_unknown_fields_rejected():
    for update in ({"query": "  "}, {"surprise": True}):
        with pytest.raises(ValidationError):
            TaskCase(**(task_data() | update))


def test_boolean_budgets_and_scores_are_not_numbers():
    with pytest.raises(ValidationError):
        EvalBudget(max_seconds=True)
    with pytest.raises(ValidationError):
        EvalResult(name="m", status="passed", score=True)
