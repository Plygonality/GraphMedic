"""Numeric helpers. Graph JSON is data: nothing in here executes it."""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any

NON_FINITE_STRINGS = {"nan": "NaN", "+infinity": "Infinity", "infinity": "Infinity", "-infinity": "-Infinity"}


def json_ready(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def non_finite_token(value: Any) -> str | None:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, str):
        return NON_FINITE_STRINGS.get(value.strip().lower())
    return None


def walk_numbers(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    if isinstance(value, bool):
        return
    if is_number(value) or (isinstance(value, str) and non_finite_token(value)):
        yield path, value
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk_numbers(item, path + (str(key),))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_numbers(item, path + (str(index),))


def as_optional_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def exactly_zero(value: Any) -> bool:
    return is_number(value) and float(value) == 0.0


def exactly_equal(value: Any, target: int | float) -> bool:
    return is_number(value) and float(value) == float(target)
