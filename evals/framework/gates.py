"""Completeness is separate from passing a quality threshold."""

from collections.abc import Mapping


def required_metrics_complete(states: Mapping[str, str], required: set[str]) -> bool:
    return all(states.get(name) in {"passed", "failed"} for name in required)
