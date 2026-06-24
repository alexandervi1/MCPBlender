"""Tool registry for blender-ai-mcp."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import Any

CATEGORY_MODULES = [
    "objects",
    "asset_pipeline",
    "modeling_core",
    "reference_modeling",
    "hard_surface_modeling",
    "material_pro",
    "quality_validation",
    "materials",
    "scene",
    "camera",
    "lighting",
    "modifiers",
    "animation",
    "rendering",
    "uv",
    "geometry_nodes",
    "scripting",
    "io",
]


@dataclass(frozen=True)
class RegisteredTool:
    """Normalized tool definition used by the MCP server."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ImportIssue:
    """Import or registration issue for an optional category module."""

    module: str
    error: str


ToolSpec = RegisteredTool


class ToolRegistry(dict[str, RegisteredTool]):
    """Mutable registry accepted by category modules."""

    def __init__(
        self,
        *args: Any,
        bridge: Any | None = None,
        logger: logging.Logger | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.bridge = bridge
        self.logger = logger or logging.getLogger(__name__)
        self.import_issues: list[ImportIssue] = []

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Mapping[str, Any] | None,
        handler: Callable[..., Awaitable[dict[str, Any]]],
    ) -> None:
        """Register one tool."""

        self[name] = RegisteredTool(name, description, dict(input_schema or {"type": "object"}), handler)

    add_tool = register_tool
    register = register_tool

    def all(self) -> list[RegisteredTool]:
        """Return all registered tools."""

        return list(self.values())

    async def call(self, name: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Call a registered tool with this registry's bridge."""

        if name not in self:
            return {
                "success": False,
                "error": "ToolNotFound",
                "message": f"Tool '{name}' is not registered.",
                "code": 404,
            }
        if self.bridge is None:
            return {
                "success": False,
                "error": "BridgeUnavailable",
                "message": "No Blender bridge has been configured for the tool registry.",
                "code": 503,
            }
        result = self[name].handler(bridge=self.bridge, params=dict(params or {}))
        if inspect.isawaitable(result):
            result = await result
        return result


def build_registry(
    *,
    bridge: Any | None = None,
    logger: logging.Logger | None = None,
    categories: Iterable[str] = CATEGORY_MODULES,
    strict: bool = False,
) -> ToolRegistry:
    """Load all available tool categories.

    Missing or broken category modules are recorded on ``registry.import_issues``.
    Set ``strict=True`` in tests or release checks to fail fast.
    """

    registry = ToolRegistry(bridge=bridge, logger=logger)
    for module_name in categories:
        qualified = f"server.tools.{module_name}"
        try:
            module = import_module(qualified)
            register_tools = getattr(module, "register_tools")
            register_tools(registry)
        except Exception as exc:  # noqa: BLE001 - category modules are optional at core import time
            if strict:
                raise
            issue = ImportIssue(module=qualified, error=str(exc))
            registry.import_issues.append(issue)
            registry.logger.debug("Tool module unavailable: %s: %s", qualified, exc)
    return registry


def load_default_registry(**kwargs: Any) -> ToolRegistry:
    """Compatibility alias for callers that prefer explicit naming."""

    return build_registry(**kwargs)


__all__ = [
    "CATEGORY_MODULES",
    "ImportIssue",
    "RegisteredTool",
    "ToolRegistry",
    "ToolSpec",
    "build_registry",
    "load_default_registry",
]
