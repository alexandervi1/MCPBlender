"""Tests for the async socket bridge to the Blender addon."""

from __future__ import annotations

import asyncio
import inspect
import socket
from typing import Any

import pytest

from conftest import assert_error, assert_success, import_bridge_module, read_json_line, write_json_line


BRIDGE_CLASS_NAMES = ("BlenderBridge", "BlenderSocketBridge", "AsyncBlenderBridge")
SEND_METHOD_NAMES = ("call_tool", "send_command", "execute_tool", "request", "call", "execute")
DISCONNECT_METHOD_NAMES = ("disconnect", "close", "aclose")


def bridge_class(module: Any) -> type[Any]:
    for name in BRIDGE_CLASS_NAMES:
        candidate = getattr(module, name, None)
        if inspect.isclass(candidate):
            return candidate
    pytest.fail(f"Bridge module must expose one of: {', '.join(BRIDGE_CLASS_NAMES)}")


def instantiate_bridge(module: Any, cls: type[Any], host: str, port: int) -> Any:
    config_cls = getattr(module, "BridgeConfig", None)
    attempts = [
        lambda: cls(config_cls(host=host, port=port, timeout=0.2, retries=1)),
        lambda: cls(config=config_cls(host=host, port=port, timeout=0.2, retries=1)),
        lambda: cls(host=host, port=port, timeout=0.2, retries=1),
        lambda: cls(host=host, port=port, timeout=0.2, max_retries=1),
        lambda: cls(host=host, port=port),
        lambda: cls(port=port, host=host),
        lambda: cls(host, port),
        lambda: cls(port),
    ]
    errors: list[str] = []
    for attempt in attempts:
        try:
            return attempt()
        except (AttributeError, TypeError) as exc:
            errors.append(str(exc))
    pytest.fail("Could not instantiate bridge:\n" + "\n".join(errors))


async def maybe_connect(bridge: Any) -> Any:
    connect = getattr(bridge, "connect", None)
    if not callable(connect):
        return None
    result = connect()
    if inspect.isawaitable(result):
        return await result
    return result


async def disconnect(bridge: Any) -> None:
    for name in DISCONNECT_METHOD_NAMES:
        method = getattr(bridge, name, None)
        if callable(method):
            result = method()
            if inspect.isawaitable(result):
                await result
            return


async def send_bridge_command(bridge: Any, tool: str, params: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    for name in SEND_METHOD_NAMES:
        method = getattr(bridge, name, None)
        if not callable(method):
            continue
        attempts = [
            lambda: method(tool, params),
            lambda: method(tool=tool, params=params),
            lambda: method({"tool": tool, "params": params}),
        ]
        for attempt in attempts:
            try:
                result = attempt()
            except TypeError as exc:
                errors.append(str(exc))
                continue
            if inspect.isawaitable(result):
                return await result
            return result
    pytest.fail("Could not send command through bridge:\n" + "\n".join(errors))


def unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_bridge_round_trips_newline_delimited_json() -> None:
    bridge_module = import_bridge_module()
    received: list[dict[str, Any]] = []

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await read_json_line(reader)
        received.append(request)
        await write_json_line(
            writer,
            {
                "id": request.get("id"),
                "success": True,
                "result": {"echo_tool": request["tool"], "echo_params": request.get("params", {})},
                "error": None,
            },
        )
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    bridge = instantiate_bridge(bridge_module, bridge_class(bridge_module), "127.0.0.1", port)

    try:
        await maybe_connect(bridge)
        response = await send_bridge_command(bridge, "create_object", {"object_type": "cube", "name": "Cube"})
    finally:
        await disconnect(bridge)
        server.close()
        await server.wait_closed()

    result = assert_success(response)
    assert result["echo_tool"] == "create_object"
    assert result["echo_params"]["object_type"] == "cube"
    assert received[0]["tool"] == "create_object"
    assert received[0]["params"]["name"] == "Cube"


@pytest.mark.asyncio
async def test_bridge_connection_failure_is_reported_clearly() -> None:
    bridge_module = import_bridge_module()
    port = unused_tcp_port()
    bridge = instantiate_bridge(bridge_module, bridge_class(bridge_module), "127.0.0.1", port)

    try:
        connect_result = await maybe_connect(bridge)
    except Exception as exc:
        message = str(exc).lower()
        assert "connect" in message or "connection" in message or "refused" in message
    else:
        if isinstance(connect_result, dict):
            assert_error(connect_result)
        elif connect_result is not None:
            assert connect_result is False
    finally:
        await disconnect(bridge)
