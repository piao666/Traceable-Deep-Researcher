"""Strict per-instance replay. A miss is an error, never a live-provider call."""

from copy import deepcopy
from threading import Lock

from .manifest import content_hash


class FixtureMiss(LookupError):
    pass


class ToolReplay:
    def __init__(self, fixtures: list[dict]):
        self._fixtures = {}
        self._counts = {}
        self._lock = Lock()
        self.calls = 0
        for fixture in fixtures:
            key = self._key(fixture["tool_name"], fixture["arguments"], fixture["context"], fixture["fixture_key"])
            limit = fixture.get("max_calls", 1)
            if type(limit) is not int or limit < 1:
                raise ValueError("max_calls must be a positive integer")
            content_hash(fixture["result"])  # Reject non-JSON and non-finite values early.
            if key in self._fixtures:
                raise ValueError("duplicate fixture key")
            self._fixtures[key] = deepcopy(fixture) | {"max_calls": limit}

    @staticmethod
    def _key(tool_name, arguments, context, fixture_key):
        return content_hash({"tool_name": tool_name, "arguments": arguments,
                             "context": context, "fixture_key": fixture_key})

    def call(self, tool_name: str, arguments: dict, *, context: str, fixture_key: str):
        key = self._key(tool_name, arguments, context, fixture_key)
        with self._lock:
            fixture = self._fixtures.get(key)
            count = self._counts.get(key, 0)
            if fixture is None or count >= fixture["max_calls"]:
                raise FixtureMiss(f"fixture unavailable: {tool_name}/{context}/{fixture_key}")
            self._counts[key] = count + 1
            self.calls += 1
            return deepcopy(fixture["result"])
