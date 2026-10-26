"""JSON-aware comparisons for fixed node output constraints."""

import math


def json_values_equal(actual, expected) -> bool:
    """Booleans are distinct from numbers, including within lists and objects."""
    if type(actual) in {int, float} and type(expected) in {int, float}:
        return math.isfinite(actual) and math.isfinite(expected) and actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            json_values_equal(actual[key], expected[key]) for key in actual)
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            json_values_equal(left, right) for left, right in zip(actual, expected))
    return actual == expected
