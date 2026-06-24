"""JSON serialization helpers for Blender-facing data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any


def to_jsonable(value: Any, *, max_depth: int = 6) -> Any:
    """Convert common Python and Blender-like values to JSON-compatible data."""

    return _to_jsonable(value, depth=0, max_depth=max_depth, seen=set())


def _to_jsonable(value: Any, *, depth: int, max_depth: int, seen: set[int]) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if depth >= max_depth:
        return repr(value)

    value_id = id(value)
    if value_id in seen:
        return "<circular>"

    if is_dataclass(value):
        seen.add(value_id)
        return _to_jsonable(asdict(value), depth=depth + 1, max_depth=max_depth, seen=seen)
    if hasattr(value, "model_dump"):
        seen.add(value_id)
        return _to_jsonable(value.model_dump(), depth=depth + 1, max_depth=max_depth, seen=seen)
    if isinstance(value, Mapping):
        seen.add(value_id)
        return {
            str(key): _to_jsonable(item, depth=depth + 1, max_depth=max_depth, seen=seen)
            for key, item in value.items()
        }
    if hasattr(value, "to_tuple"):
        try:
            return [
                _to_jsonable(item, depth=depth + 1, max_depth=max_depth, seen=seen)
                for item in value.to_tuple()
            ]
        except Exception:  # noqa: BLE001 - best-effort serializer
            pass
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        seen.add(value_id)
        return [_to_jsonable(item, depth=depth + 1, max_depth=max_depth, seen=seen) for item in value]
    if hasattr(value, "name"):
        return str(getattr(value, "name"))
    return str(value)


to_json_compatible = to_jsonable
