"""Async socket bridge from the MCP server to the Blender addon."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9876
DEFAULT_TIMEOUT = 120.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 0.25

Connector = Callable[[str, int], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]
SleepFunc = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class BridgeConfig:
    """Connection settings for the Blender addon."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    timeout: float = DEFAULT_TIMEOUT
    retries: int = DEFAULT_RETRIES
    backoff: float = DEFAULT_BACKOFF

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        """Build config from ``BLENDER_MCP_HOST`` and ``BLENDER_MCP_PORT``."""

        raw_port = os.getenv("BLENDER_MCP_PORT", str(DEFAULT_PORT))
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ValueError("BLENDER_MCP_PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ValueError("BLENDER_MCP_PORT must be between 1 and 65535")
        return cls(host=os.getenv("BLENDER_MCP_HOST", DEFAULT_HOST) or DEFAULT_HOST, port=port)


class BridgeError(RuntimeError):
    """Base exception for bridge failures."""


class BridgeProtocolError(BridgeError):
    """Raised when Blender sends malformed data."""


class BridgeTimeoutError(BridgeError):
    """Raised when Blender does not respond before timeout."""


class BlenderBridge:
    """Newline-delimited JSON client for the Blender addon socket server."""

    def __init__(
        self,
        config: BridgeConfig | None = None,
        host: str | None = None,
        port: int | None = None,
        timeout: float | None = None,
        timeout_seconds: float | None = None,
        retries: int | None = None,
        max_retries: int | None = None,
        backoff: float | None = None,
        connector: Connector | None = None,
        sleep: SleepFunc | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        base = config or BridgeConfig.from_env()
        self.config = BridgeConfig(
            host=host or base.host,
            port=port if port is not None else base.port,
            timeout=timeout if timeout is not None else timeout_seconds or base.timeout,
            retries=max_retries if max_retries is not None else retries or base.retries,
            backoff=backoff if backoff is not None else base.backoff,
        )
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connector = connector or asyncio.open_connection
        self._sleep = sleep or asyncio.sleep
        self._logger = logger or logging.getLogger(__name__)
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        """Return whether an open writer is available."""

        return self._writer is not None and not self._writer.is_closing()

    @property
    def is_connected(self) -> bool:
        """Alias used by some integrations."""

        return self.connected

    async def connect(self) -> None:
        """Connect to Blender with exponential backoff."""

        if self.connected:
            return
        delay = self.config.backoff
        last_error: BaseException | None = None
        for attempt in range(1, max(1, self.config.retries) + 1):
            try:
                self._logger.info(
                    "Connecting to Blender bridge at %s:%s (attempt %s/%s)",
                    self.config.host,
                    self.config.port,
                    attempt,
                    self.config.retries,
                )
                self._reader, self._writer = await self._connector(
                    self.config.host,
                    self.config.port,
                )
                return
            except (OSError, asyncio.TimeoutError) as exc:
                last_error = exc
                if attempt >= self.config.retries:
                    break
                await self._sleep(delay)
                delay *= 2
        raise ConnectionError(
            f"Could not connect to Blender addon at {self.config.host}:{self.config.port}"
        ) from last_error

    async def disconnect(self) -> None:
        """Close the socket connection."""

        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is None:
            return
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError, RuntimeError):
            self._logger.debug("Ignoring bridge close error", exc_info=True)

    close = disconnect
    aclose = disconnect

    async def send_request(
        self,
        tool_name: str,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send one raw request and return Blender's decoded response."""

        if not tool_name:
            raise BridgeProtocolError("Tool name must be a non-empty string")
        await self.connect()
        assert self._reader is not None
        assert self._writer is not None

        request_id = str(uuid.uuid4())
        request = {"id": request_id, "tool": tool_name, "params": dict(params or {})}
        self._writer.write(json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n")
        await self._writer.drain()

        try:
            line = await asyncio.wait_for(self._reader.readline(), timeout=self.config.timeout)
        except asyncio.TimeoutError as exc:
            await self.disconnect()
            raise BridgeTimeoutError(
                f"Tool '{tool_name}' did not respond within {self.config.timeout:.0f}s."
            ) from exc
        if not line:
            await self.disconnect()
            raise ConnectionError("Blender closed the socket connection.")

        try:
            response = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise BridgeProtocolError("Blender returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise BridgeProtocolError("Blender response must be a JSON object")
        if response.get("id") != request_id:
            raise BridgeProtocolError("Blender response id did not match the request id")
        return response

    async def call_tool(self, tool_name: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Send one tool request and always return a structured response."""

        async with self._lock:
            try:
                response = await self.send_request(tool_name, params)
            except BridgeTimeoutError as exc:
                return {"success": False, "error": "BlenderTimeout", "message": str(exc), "code": 504}
            except BridgeProtocolError as exc:
                return {"success": False, "error": "BlenderProtocolError", "message": str(exc), "code": 502}
            except Exception as exc:  # noqa: BLE001 - socket boundary
                return {
                    "success": False,
                    "error": "BlenderConnectionError",
                    "message": str(exc),
                    "code": 503,
                }

        if response.get("success") is False and isinstance(response.get("error"), dict):
            error = response["error"]
            return {
                "success": False,
                "error": str(error.get("type") or error.get("error") or "BlenderError"),
                "message": str(error.get("message") or "Blender command failed."),
                "code": int(error.get("code") or 500),
            }
        return response

    async def execute_tool(self, tool_name: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Compatibility alias used by tests and integrations."""

        return await self.call_tool(tool_name, params)

    async def send_command(
        self,
        tool_name: str | Mapping[str, Any],
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compatibility alias accepting either a tool name or command dict."""

        if isinstance(tool_name, Mapping):
            return await self.call_tool(str(tool_name["tool"]), tool_name.get("params") or {})
        return await self.call_tool(tool_name, params)

    request = execute_tool
    call = execute_tool
    execute = execute_tool


BlenderSocketBridge = BlenderBridge
AsyncBlenderBridge = BlenderBridge
