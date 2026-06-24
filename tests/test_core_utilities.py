"""Tests for server utilities, registry, and MCP registration glue."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import pytest
from pydantic import Field

from conftest import FakeBlenderBridge, assert_error, assert_success
from server import main
from server.bridge import BridgeConfig, BlenderBridge
from server.tools import ToolRegistry, build_registry, load_default_registry
from server.tools.common import EmptyParams, ToolModel, build_tools, export_tools, register_toolset
from server.utils.serializers import to_json_compatible, to_jsonable
from server.utils.validators import (
    StrictBaseModel,
    StructuredError,
    ensure_parent_dir,
    error_response,
    json_schema_for_model,
    success_response,
    validate_model,
    validate_params,
)


class SampleModel(StrictBaseModel):
    """Small validation model for utility tests."""

    name: str = Field(..., min_length=1)


def test_validator_helpers_return_project_envelopes(tmp_path: Path) -> None:
    """Validation helpers produce predictable data and errors."""
    instance, error = validate_model(SampleModel, {"name": "Cube"})
    assert error is None
    assert instance.name == "Cube"

    instance, error = validate_model(SampleModel, {"name": ""})
    assert instance is None
    assert error["error"] == "InvalidParams"

    assert validate_params({"name": "Cube"}, SampleModel)["name"] == "Cube"
    assert validate_params({"raw": True}, None) == {"raw": True}
    with pytest.raises(ValueError):
        validate_params({"name": ""}, SampleModel)

    assert json_schema_for_model(None)["additionalProperties"] is True
    assert json_schema_for_model(object)["additionalProperties"] is True
    assert json_schema_for_model(SampleModel)["type"] == "object"
    assert success_response({"ok": True})["success"] is True
    assert error_response(StructuredError("Boom", "Failed", 418))["code"] == 418
    assert error_response({"type": "Mapped", "message": "Nope"}, code=400)["error"] == "Mapped"
    assert error_response("Plain", "Message", 499)["code"] == 499

    target = ensure_parent_dir(tmp_path / "nested" / "file.txt")
    assert target.parent.exists()


def test_serializer_handles_common_python_and_blender_like_values() -> None:
    """Serializer converts complex objects into JSON-compatible values."""

    class Status(Enum):
        READY = "ready"

    @dataclass
    class Item:
        path: Path
        status: Status

    class TupleLike:
        def to_tuple(self) -> tuple[int, int]:
            return (1, 2)

    class BadTupleLike:
        def to_tuple(self) -> tuple[int, int]:
            raise RuntimeError("no tuple")

    class Named:
        name = "NamedObject"

    circular: list[Any] = []
    circular.append(circular)

    assert to_jsonable(Item(Path("asset.blend"), Status.READY)) == {"path": "asset.blend", "status": "ready"}
    assert to_jsonable({"tuple": TupleLike(), "named": Named()}) == {"tuple": [1, 2], "named": "NamedObject"}
    assert "BadTupleLike" in to_jsonable(BadTupleLike())
    assert to_jsonable(circular) == ["<circular>"]
    assert to_json_compatible({"deep": {"value": object()}}, max_depth=1)["deep"].startswith("{")


@pytest.mark.asyncio
async def test_tool_registry_call_and_error_paths() -> None:
    """Registry can call tools through an injected bridge and report missing setup."""
    registry = build_registry(bridge=FakeBlenderBridge(), categories=["objects"], strict=True)
    assert registry.all()
    result = await registry.call("list_objects", {})
    assert_success(result)

    assert_error(await registry.call("missing_tool", {}), "ToolNotFound")
    no_bridge = ToolRegistry()
    no_bridge.register_tool("list_objects", "List", {"type": "object"}, registry["list_objects"].handler)
    assert_error(await no_bridge.call("list_objects", {}), "BridgeUnavailable")
    assert load_default_registry(categories=[]).import_issues == []


def test_tool_registry_records_import_issues() -> None:
    """Broken optional categories are recorded unless strict mode is requested."""
    registry = build_registry(categories=["does_not_exist"], strict=False)
    assert registry.import_issues
    with pytest.raises(ModuleNotFoundError):
        build_registry(categories=["does_not_exist"], strict=True)


def test_bridge_config_from_env_validates_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bridge config validates environment values."""
    monkeypatch.setenv("BLENDER_MCP_HOST", "")
    monkeypatch.setenv("BLENDER_MCP_PORT", "9877")
    assert BridgeConfig.from_env().host == "localhost"
    assert BridgeConfig.from_env().port == 9877

    monkeypatch.setenv("BLENDER_MCP_PORT", "not-int")
    with pytest.raises(ValueError, match="integer"):
        BridgeConfig.from_env()

    monkeypatch.setenv("BLENDER_MCP_PORT", "70000")
    with pytest.raises(ValueError, match="between"):
        BridgeConfig.from_env()


@pytest.mark.asyncio
async def test_bridge_disconnect_ignores_writer_close_errors() -> None:
    """Disconnect clears state even if a writer raises while closing."""

    class BadWriter:
        def is_closing(self) -> bool:
            return False

        def close(self) -> None:
            return None

        async def wait_closed(self) -> None:
            raise RuntimeError("close failed")

    bridge = BlenderBridge()
    bridge._writer = BadWriter()  # type: ignore[assignment]
    await bridge.disconnect()
    assert bridge.connected is False


@pytest.mark.asyncio
async def test_common_toolset_helpers() -> None:
    """Common helper functions support generated tool modules."""
    tools = build_tools([("ping", "Ping tool.", EmptyParams)])
    namespace: dict[str, Any] = {}
    export_tools(namespace, tools)

    registry: dict[str, Any] = {}
    register_toolset(registry, tools)
    assert "ping" in registry

    response = await namespace["ping"](bridge=FakeBlenderBridge(), params={})
    assert_success(response)
    invalid = await namespace["ping"](bridge=FakeBlenderBridge(), params={"extra": True})
    assert_error(invalid, "InvalidParams")

    with pytest.raises(TypeError):
        register_toolset(object(), tools)


class FakeMCP:
    """Capture FastMCP add_tool calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def add_tool(self, fn: Any, name: str, description: str) -> None:
        self.calls.append({"fn": fn, "name": name, "description": description})


@pytest.mark.asyncio
async def test_main_registers_fastmcp_tool_and_logging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP registration wraps tool calls and configures logging."""
    monkeypatch.setattr(main, "LOG_DIR", tmp_path)
    logger = main.configure_logging()
    assert isinstance(logger, logging.Logger)

    registry = build_registry(bridge=FakeBlenderBridge(), categories=["objects"], strict=True)
    fake_mcp = FakeMCP()
    main._register_fastmcp_tool(fake_mcp, registry["list_objects"], FakeBlenderBridge(), logger)

    assert fake_mcp.calls[0]["name"] == "list_objects"
    payload = await fake_mcp.calls[0]["fn"]()
    assert '"success": true' in payload.lower()
