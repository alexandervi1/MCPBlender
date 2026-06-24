"""Async localhost NDJSON socket server for the AI MCP Blender addon."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from collections import deque
from datetime import datetime
from typing import Any

from . import executor

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9876
MAX_LINE_BYTES = 8 * 1024 * 1024

_logs: deque[str] = deque(maxlen=20)
_server: asyncio.AbstractServer | None = None
_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_running = threading.Event()
_last_command: dict[str, Any] | None = None
_host = DEFAULT_HOST
_port = DEFAULT_PORT


def log(message: str) -> None:
    """Record a timestamped addon log entry."""
    stamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{stamp}] {message}"
    _logs.append(entry)
    print(f"AI MCP Bridge {entry}")


def get_logs() -> list[str]:
    """Return the last 20 server log messages."""
    return list(_logs)


def get_last_command() -> dict[str, Any] | None:
    """Return the last decoded command received by the socket server."""
    return dict(_last_command) if isinstance(_last_command, dict) else None


def is_running() -> bool:
    """Return whether the socket server thread is active."""
    return _running.is_set()


def address() -> tuple[str, int]:
    """Return the configured listening address."""
    return _host, _port


async def _write_response(writer: asyncio.StreamWriter, response: dict[str, Any]) -> None:
    payload = json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n"
    writer.write(payload.encode("utf-8"))
    await writer.drain()


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    global _last_command
    peer = writer.get_extra_info("peername")
    log(f"Client connected: {peer}")
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            if len(line) > MAX_LINE_BYTES:
                await _write_response(
                    writer,
                    {
                        "id": None,
                        "success": False,
                        "result": None,
                        "error": {
                            "type": "PayloadTooLarge",
                            "message": "JSON line exceeds maximum payload size.",
                            "code": 413,
                            "details": None,
                        },
                    },
                )
                continue
            try:
                request = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError as exc:
                await _write_response(
                    writer,
                    {
                        "id": None,
                        "success": False,
                        "result": None,
                        "error": {
                            "type": "InvalidJson",
                            "message": str(exc),
                            "code": 400,
                            "details": None,
                        },
                    },
                )
                continue
            _last_command = request if isinstance(request, dict) else None
            if isinstance(request, dict):
                log(f"Command: {request.get('tool', '<missing>')}")
            response = await executor.execute_request(request)
            if not response.get("success"):
                error = response.get("error") or {}
                log(f"Error: {error.get('type', 'Unknown')} - {error.get('message', '')}")
            await _write_response(writer, response)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - keep server alive.
        log(f"Client error: {exc}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        log(f"Client disconnected: {peer}")


async def _serve(host: str, port: int) -> None:
    global _server
    _server = await asyncio.start_server(_handle_client, host=host, port=port)
    sockets = ", ".join(_format_socket(sock) for sock in (_server.sockets or []))
    _running.set()
    log(f"Server listening on {sockets}")
    async with _server:
        await _server.serve_forever()


def _format_socket(sock: socket.socket) -> str:
    host, port, *_ = sock.getsockname()
    return f"{host}:{port}"


def _thread_main(host: str, port: int) -> None:
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(_serve(host, port))
    except asyncio.CancelledError:
        pass
    except OSError as exc:
        log(f"Server failed to start on {host}:{port}: {exc}")
    except Exception as exc:  # noqa: BLE001
        log(f"Server stopped unexpectedly: {exc}")
    finally:
        _running.clear()
        pending = asyncio.all_tasks(_loop)
        for task in pending:
            task.cancel()
        if pending:
            _loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        _loop.close()
        _loop = None
        log("Server stopped")


def start(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> bool:
    """Start the background socket server.

    Args:
        port: TCP port to listen on.
        host: Loopback host to bind.

    Returns:
        True when a new server thread was started, False if already running.
    """
    global _host, _port, _thread
    if is_running() or (_thread and _thread.is_alive()):
        log("Start requested but server is already running")
        return False
    _host = host
    _port = int(port)
    _thread = threading.Thread(target=_thread_main, args=(_host, _port), daemon=True, name="AI-MCP-Server")
    _thread.start()
    return True


def stop() -> bool:
    """Stop the background socket server."""
    global _server
    if not _loop or not (_thread and _thread.is_alive()):
        _running.clear()
        log("Stop requested but server is not running")
        return False

    async def shutdown() -> None:
        global _server
        if _server:
            _server.close()
            await _server.wait_closed()
            _server = None
        for task in asyncio.all_tasks():
            if task is not asyncio.current_task():
                task.cancel()

    asyncio.run_coroutine_threadsafe(shutdown(), _loop)
    return True


def execute_last_command() -> dict[str, Any]:
    """Execute the last command synchronously for UI debugging."""
    request = get_last_command()
    if not request:
        return {
            "id": None,
            "success": False,
            "result": None,
            "error": {
                "type": "NoCommand",
                "message": "No command has been received yet.",
                "code": 404,
                "details": None,
            },
        }
    log(f"Re-executing last command: {request.get('tool', '<missing>')}")
    return executor.dispatch_request(request)
