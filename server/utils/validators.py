"""Validation helpers shared by server components."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    from pydantic import BaseModel, ConfigDict, ValidationError

    PYDANTIC_AVAILABLE = True
except Exception:  # pragma: no cover - import fallback for dependency-free tests
    BaseModel = object  # type: ignore[assignment,misc]
    ConfigDict = None  # type: ignore[assignment]
    ValidationError = ValueError  # type: ignore[assignment]
    PYDANTIC_AVAILABLE = False


@dataclass(slots=True)
class StructuredError:
    """Flat structured error payload used by tools and bridge responses."""

    error: str
    message: str
    code: int = 500
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dictionary."""

        payload = asdict(self)
        if not self.details:
            payload.pop("details", None)
        return payload


if PYDANTIC_AVAILABLE:

    class StrictBaseModel(BaseModel):
        """Base model for strict Pydantic v2 validation."""

        model_config = ConfigDict(extra="forbid", validate_assignment=True)

else:

    class StrictBaseModel:  # type: ignore[no-redef]
        """Fallback model that reports missing Pydantic when used."""

        @classmethod
        def model_validate(cls, *_: Any, **__: Any) -> Any:
            raise RuntimeError("Pydantic v2 is required for validation")

        @classmethod
        def model_json_schema(cls, *_: Any, **__: Any) -> dict[str, Any]:
            return {"type": "object", "additionalProperties": True}


def success_response(result: Any = None) -> dict[str, Any]:
    """Return the project success envelope."""

    return {"success": True, "result": result, "error": None}


def error_response(error: StructuredError | Mapping[str, Any] | str, message: str | None = None, code: int = 500) -> dict[str, Any]:
    """Return the project flat error envelope."""

    if isinstance(error, StructuredError):
        payload = {"success": False, **error.to_dict()}
    elif isinstance(error, Mapping):
        payload = {
            "success": False,
            "error": str(error.get("error") or error.get("type") or "ToolError"),
            "message": str(error.get("message") or "Tool failed."),
            "code": int(error.get("code") or code),
        }
    else:
        payload = {"success": False, "error": str(error), "message": message or str(error), "code": code}
    return payload


def validate_model(model: type[BaseModel], data: dict[str, Any]) -> tuple[BaseModel | None, dict[str, Any] | None]:
    """Validate data and return either the model instance or a structured error."""

    try:
        return model.model_validate(data), None
    except ValidationError as exc:
        return None, {
            "success": False,
            "error": "InvalidParams",
            "message": exc.errors()[0]["msg"] if hasattr(exc, "errors") else str(exc),
            "code": 400,
        }


def validate_params(params: Mapping[str, Any] | None, model: type[Any] | None) -> dict[str, Any]:
    """Validate a params mapping with an optional Pydantic model."""

    raw = dict(params or {})
    if model is None:
        return raw
    instance, error = validate_model(model, raw)
    if error:
        raise ValueError(error["message"])
    if hasattr(instance, "model_dump"):
        return instance.model_dump()
    return raw


def json_schema_for_model(model: type[Any] | None) -> dict[str, Any]:
    """Return a JSON schema for a Pydantic model if possible."""

    if model is None:
        return {"type": "object", "additionalProperties": True}
    if hasattr(model, "model_json_schema"):
        return model.model_json_schema()
    return {"type": "object", "additionalProperties": True}


def ensure_parent_dir(path: str | Path) -> Path:
    """Create the parent directory for a path and return it."""

    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    return target
