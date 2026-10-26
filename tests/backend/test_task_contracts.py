"""Version one wire contracts validate independently of the web application."""

from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError


def models():
    return importlib.import_module("backend.server.tasks.models")


def event_data(**changes):
    return {"research_id": "r1", "attempt_id": "a1", "seq": 1,
            "type": "task.created", "created_at": "2026-10-24T08:00:00Z", **changes}


def test_frozen_fixture_roundtrips_and_schema_is_versioned():
    module = models()
    fixture = json.loads((Path(__file__).parents[1] / "fixtures/research-contract.v1.json").read_text(encoding="utf-8"))
    for key, model in (("request", module.ResearchTaskRequest),
                       ("event", module.TaskEvent), ("subscribe", module.SubscribeCommand)):
        parsed = model.model_validate(fixture[key])
        assert model.model_validate_json(parsed.model_dump_json()) == parsed
    assert module.TaskEvent.model_json_schema()["properties"]["version"]["const"] == 1


@pytest.mark.parametrize("changes", [
    {"version": 2}, {"version": True}, {"version": "1"},
    {"seq": 0}, {"seq": -1}, {"seq": True}, {"seq": 1.5},
    {"created_at": "2026-10-24T08:00:00"}, {"created_at": datetime(2026, 10, 24)},
    {"research_id": " "}, {"attempt_id": ""}, {"type": " "}, {"unknown": 1},
])
def test_event_rejects_invalid_envelopes(changes):
    with pytest.raises(ValidationError):
        models().TaskEvent(**event_data(**changes))


def test_event_normalizes_aware_time_to_utc_and_is_frozen():
    module = models()
    event = module.TaskEvent(**event_data(created_at="2026-10-24T16:00:00+08:00"))
    assert event.created_at == datetime(2026, 10, 24, 8, tzinfo=timezone.utc)
    assert event.created_at.utcoffset() == timedelta(0)
    assert module.TaskEvent(research_id="r1", seq=1, type="task.created").created_at.tzinfo is not None
    with pytest.raises(ValidationError):
        event.seq = 2


@pytest.mark.parametrize("changes", [
    {"task": ""}, {"task": " \n "}, {"report_type": "invented"},
    {"report_source": "invented"}, {"tone": "invented"}, {"unknown": 1},
    {"budget": {"max_tool_calls": 0}}, {"budget": {"max_seconds": -1}},
    {"budget": {"max_cost_usd": 0}}, {"budget": {"max_tokens": 0}},
    {"budget": {"max_seconds": float("inf")}}, {"budget": {"secret": "no"}},
    {"budget": {"max_seconds": True}}, {"budget": {"max_cost_usd": True}},
    {"mcp_configs": [{"env": {"API_KEY": "no"}}]},
    {"mcp_config_refs": [{"env": {"API_KEY": "no"}}]},
    {"mcp_config_refs": [""]}, {"source_policy": {"allowed_kinds": ["invented"]}},
    {"source_policy": {"allowed_kinds": []}},
    {"source_policy": {"network_allowed": False, "unknown": 1}},
])
def test_request_rejects_invalid_values_and_inline_credentials(changes):
    with pytest.raises(ValidationError):
        models().ResearchTaskRequest(**{"task": "Compare local designs", **changes})


def test_request_preserves_supported_modes_and_independent_defaults():
    module = models()
    from traceable_deep_researcher.utils.enum import ReportSource, ReportType, Tone
    for report_type in [item.value for item in ReportType] + ["multi_agents"]:
        assert module.ResearchTaskRequest(task="x", report_type=report_type).report_type == report_type
    for source in ReportSource:
        assert module.ResearchTaskRequest(task="x", report_source=source.value).report_source == source
    for tone in Tone:
        assert module.ResearchTaskRequest(task="x", tone=tone.name).tone.value == tone.name
    first, second = module.ResearchTaskRequest(task="first"), module.ResearchTaskRequest(task="second")
    first.source_urls.append("https://example.test")
    first.mcp_config_refs.append("search-local")
    first.source_policy.allowed_kinds.append(ReportSource.Local)
    assert second.source_urls == []
    assert second.mcp_config_refs == []
    assert second.source_policy.allowed_kinds == [ReportSource.Web]


@pytest.mark.parametrize("changes", [{"after_seq": -1}, {"after_seq": True},
                                    {"version": 2}, {"version": True},
                                    {"type": "start"}, {"research_id": " "}, {"extra": 1}])
def test_subscribe_rejects_invalid_commands(changes):
    with pytest.raises(ValidationError):
        models().SubscribeCommand(**{"research_id": "r1", "after_seq": 0, **changes})


def test_subscribe_accepts_zero_and_status_domains_are_separate():
    module = models()
    assert module.SubscribeCommand(research_id="r1", after_seq=0).after_seq == 0
    assert {item.value for item in module.TaskStatus} == {
        "queued", "running", "waiting_for_review", "succeeded", "failed",
        "cancelled", "cancel_requested", "interrupted"}
    assert {item.value for item in module.ReviewStatus} == {
        "not_requested", "pending", "approved", "needs_revision", "needs_review", "rejected"}
    assert {item.value for item in module.ExportStatus} == {"queued", "running", "succeeded", "failed"}
