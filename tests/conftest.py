"""Shared pytest helpers for blender-ai-mcp.

The tests intentionally avoid importing Blender or ``bpy``. Tool modules are
tested through a fake bridge that behaves like the Blender addon socket layer.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
import uuid
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent

for path in (PROJECT_ROOT, WORKSPACE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def import_any(*module_names: str) -> Any:
    """Import the first available module from a list of supported layouts."""
    errors: list[str] = []
    for module_name in module_names:
        try:
            return import_module(module_name)
        except ModuleNotFoundError as exc:
            errors.append(f"{module_name}: {exc}")
    pytest.fail("Could not import any expected module:\n" + "\n".join(errors))


def import_tool_module(name: str) -> Any:
    """Import a server tool module regardless of the final package layout."""
    return import_any(
        f"blender_ai_mcp.server.tools.{name}",
        f"server.tools.{name}",
    )


def import_bridge_module() -> Any:
    """Import the bridge module regardless of the final package layout."""
    return import_any("blender_ai_mcp.server.bridge", "server.bridge")


@dataclass
class BridgeCall:
    """A recorded fake bridge call."""

    tool: str
    params: dict[str, Any]


@dataclass
class FakeBlenderBridge:
    """In-memory stand-in for the Blender socket bridge used by tool tests."""

    responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[BridgeCall] = field(default_factory=list)
    connected: bool = True

    async def _record(self, tool: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.connected:
            return {
                "success": False,
                "error": "BlenderDisconnected",
                "message": "The fake Blender bridge is disconnected.",
                "code": 503,
            }

        payload = params or {}
        self.calls.append(BridgeCall(tool=tool, params=payload))
        return self.responses.get(
            tool,
            {
                "success": True,
                "result": {"tool": tool, "params": payload},
                "error": None,
            },
        )

    async def execute_tool(self, tool: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._record(tool, params)

    async def send_command(self, tool: str | dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
        if isinstance(tool, dict):
            command = tool
            return await self._record(str(command["tool"]), command.get("params", {}))
        return await self._record(tool, params)

    async def request(self, tool: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._record(tool, params)

    async def call(self, tool: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._record(tool, params)

    async def execute(self, tool: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._record(tool, params)

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def disconnect(self) -> None:
        self.connected = False


async def invoke_tool(
    module: Any,
    tool_name: str,
    params: dict[str, Any] | None = None,
    bridge: FakeBlenderBridge | None = None,
) -> Any:
    """Invoke a tool function while supporting common bridge injection styles."""
    params = params or {}
    bridge = bridge or FakeBlenderBridge()
    function = getattr(module, tool_name, None)
    assert callable(function), f"{module.__name__}.{tool_name} must be callable"

    attempts = [
        lambda: function(bridge=bridge, **params),
        lambda: function(client=bridge, **params),
        lambda: function(blender=bridge, **params),
        lambda: function(bridge, **params),
        lambda: function(params=params, bridge=bridge),
        lambda: function(bridge=bridge, params=params),
        lambda: function(bridge, params),
        lambda: function(params),
        lambda: function(**params),
    ]

    errors: list[str] = []
    for attempt in attempts:
        try:
            value = attempt()
        except TypeError as exc:
            errors.append(str(exc))
            continue

        if inspect.isawaitable(value):
            return await value
        return value

    pytest.fail(
        f"Could not invoke {module.__name__}.{tool_name} with supported signatures:\n"
        + "\n".join(errors)
    )


def assert_success(response: Any) -> dict[str, Any]:
    """Assert that a tool response uses the project success envelope."""
    assert isinstance(response, dict), "Tool responses must be dictionaries"
    assert response.get("success") is True, response
    assert "result" in response, response
    assert response.get("error") in (None, ""), response
    return response["result"]


def assert_error(response: Any, expected_error: str | None = None) -> dict[str, Any]:
    """Assert that a tool response uses the project structured error envelope."""
    assert isinstance(response, dict), "Errors must be returned as dictionaries"
    assert response.get("success") is False, response
    assert isinstance(response.get("error"), str) and response["error"], response
    assert isinstance(response.get("message"), str) and response["message"], response
    assert isinstance(response.get("code"), int), response
    if expected_error:
        assert response["error"] == expected_error
    return response


async def read_json_line(reader: asyncio.StreamReader) -> dict[str, Any]:
    """Read one newline-delimited JSON message."""
    raw = await asyncio.wait_for(reader.readline(), timeout=1.0)
    assert raw.endswith(b"\n")
    return json.loads(raw.decode("utf-8"))


async def write_json_line(writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
    """Write one newline-delimited JSON message."""
    writer.write(json.dumps(payload).encode("utf-8") + b"\n")
    await writer.drain()


def make_command(tool: str, params: dict[str, Any]) -> dict[str, Any]:
    """Build a command matching the Blender addon socket protocol."""
    return {"id": str(uuid.uuid4()), "tool": tool, "params": params}
