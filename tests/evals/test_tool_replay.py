import pytest

from evals.framework.replay import FixtureMiss, ToolReplay


def fixture():
    return {"tool_name": "search", "arguments": {"b": 2, "a": 1},
            "context": "t1", "fixture_key": "lookup", "result": {"pages": ["text"]}, "max_calls": 1}


def test_matching_uses_canonical_json_and_copies_output():
    replay = ToolReplay([fixture()])
    result = replay.call("search", {"a": 1, "b": 2}, context="t1", fixture_key="lookup")
    result["pages"].append("changed")
    assert replay.calls == 1
    with pytest.raises(FixtureMiss):
        replay.call("search", {"a": 1, "b": 2}, context="t1", fixture_key="lookup")
    assert ToolReplay([fixture()]).call("search", {"b": 2, "a": 1}, context="t1", fixture_key="lookup") == {"pages": ["text"]}


def test_missing_fixture_never_uses_provider():
    with pytest.raises(FixtureMiss, match="fixture"):
        ToolReplay([]).call("search", {}, context="t1", fixture_key="missing")


def test_duplicate_keys_and_non_json_arguments_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        ToolReplay([fixture(), fixture()])
    with pytest.raises(ValueError):
        ToolReplay([]).call("search", {"value": float("nan")}, context="t1", fixture_key="x")
