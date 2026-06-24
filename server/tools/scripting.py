"""Sandboxed scripting MCP tools for Blender."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .objects import ToolDefinition, _dispatch, _register_tool

ALLOWED_IMPORTS = {"bpy", "mathutils", "math", "bmesh", "os", "json"}
BLOCKED_CALLS = {"eval", "exec", "compile", "__import__", "open", "input", "breakpoint"}
BLOCKED_ATTR_PREFIXES = ("__",)


class StrictModel(BaseModel):
    """Base model for strict scripting tool parameters."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def _validate_python_source(source: str, *, expression: bool) -> str:
    """Perform static safety checks before forwarding Python to Blender."""

    try:
        tree = ast.parse(source, mode="eval" if expression else "exec")
    except SyntaxError as exc:
        raise ValueError(f"Invalid Python syntax: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] not in ALLOWED_IMPORTS:
                    raise ValueError(f"Import is not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".", 1)[0]
            if module not in ALLOWED_IMPORTS:
                raise ValueError(f"Import is not allowed: {node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in BLOCKED_CALLS:
                raise ValueError(f"Call is not allowed: {func.id}")
            if isinstance(func, ast.Attribute) and func.attr.startswith(BLOCKED_ATTR_PREFIXES):
                raise ValueError("Dunder attribute calls are not allowed.")
        elif isinstance(node, ast.Attribute) and node.attr.startswith(BLOCKED_ATTR_PREFIXES):
            raise ValueError("Dunder attribute access is not allowed.")
        elif isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("Dunder names are not allowed.")
    return source


class ExecutePythonParams(StrictModel):
    """Input model for ``execute_python``."""

    code: str = Field(..., min_length=1, max_length=20000, description="Python code executed in Blender.")
    timeout_seconds: float = Field(10.0, gt=0.0, le=120.0, description="Execution timeout.")
    allowed_imports: list[str] = Field(
        default_factory=lambda: sorted(ALLOWED_IMPORTS),
        description="Import whitelist requested for the Blender-side sandbox.",
    )
    return_last_expression: bool = Field(True, description="Return the last expression value when possible.")

    @field_validator("code")
    @classmethod
    def _code_safe(cls, value: str) -> str:
        return _validate_python_source(value, expression=False)

    @field_validator("allowed_imports")
    @classmethod
    def _imports_allowed(cls, value: list[str]) -> list[str]:
        unknown = {item.split(".", 1)[0] for item in value} - ALLOWED_IMPORTS
        if unknown:
            raise ValueError(f"Unsupported imports requested: {sorted(unknown)}")
        return value


class EvaluateExpressionParams(StrictModel):
    """Input model for ``evaluate_expression``."""

    expression: str = Field(..., min_length=1, max_length=5000, description="Python expression to evaluate.")
    timeout_seconds: float = Field(5.0, gt=0.0, le=60.0, description="Evaluation timeout.")

    @field_validator("expression")
    @classmethod
    def _expression_safe(cls, value: str) -> str:
        return _validate_python_source(value, expression=True)


class InstallAddonParams(StrictModel):
    """Input model for ``install_addon``."""

    path: str = Field(..., min_length=1, description="Addon .zip or .py path.")
    enable: bool = Field(True, description="Enable addon after installation.")
    overwrite: bool = Field(True, description="Overwrite existing addon files when supported.")
    module_name: str | None = Field(None, description="Addon module name for enabling.")
    source_type: Literal["zip", "py", "auto"] = Field("auto", description="Addon source type.")


async def execute_python(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Execute validated Python code in Blender's sandboxed executor."""

    return await _dispatch(bridge, "execute_python", ExecutePythonParams, params)


async def evaluate_expression(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Evaluate a validated Python expression in Blender."""

    return await _dispatch(bridge, "evaluate_expression", EvaluateExpressionParams, params)


async def install_addon(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Install and optionally enable a Blender addon."""

    return await _dispatch(bridge, "install_addon", InstallAddonParams, params)


TOOLS: dict[str, ToolDefinition] = {
    "execute_python": ToolDefinition("execute_python", "Execute sandboxed Blender Python code.", ExecutePythonParams, execute_python),
    "evaluate_expression": ToolDefinition("evaluate_expression", "Evaluate a sandboxed Blender Python expression.", EvaluateExpressionParams, evaluate_expression),
    "install_addon": ToolDefinition("install_addon", "Install and enable a Blender addon.", InstallAddonParams, install_addon),
}


def register_tools(registry: Any) -> Any:
    """Register all scripting tools with a registry."""

    for spec in TOOLS.values():
        _register_tool(registry, spec)
    return registry


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
