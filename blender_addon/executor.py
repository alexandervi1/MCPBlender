"""Main-thread command execution for the AI MCP Blender addon."""

from __future__ import annotations

import asyncio
import threading
import traceback
from typing import Any

import bpy

from . import handlers

_MAIN_THREAD_ID = threading.get_ident()


def _error_response(
    request_id: str | None,
    error: str,
    message: str,
    code: int = 500,
    details: Any | None = None,
) -> dict[str, Any]:
    return {
        "id": request_id,
        "success": False,
        "result": None,
        "error": {
            "type": error,
            "message": message,
            "code": code,
            "details": details,
        },
    }


def _success_response(request_id: str | None, result: Any) -> dict[str, Any]:
    return {"id": request_id, "success": True, "result": result, "error": None}


def dispatch_request(request: dict[str, Any]) -> dict[str, Any]:
    """Validate and execute a command request on Blender's main thread.

    Args:
        request: Newline-delimited JSON request decoded into a dictionary.

    Returns:
        Structured response matching the addon socket protocol.
    """
    request_id = request.get("id") if isinstance(request, dict) else None
    try:
        if not isinstance(request, dict):
            raise handlers.CommandError("InvalidRequest", "Request must be a JSON object.", 400)
        tool = request.get("tool")
        if not isinstance(tool, str) or not tool:
            raise handlers.CommandError("InvalidRequest", "Request field 'tool' is required.", 400)
        params = request.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise handlers.CommandError("InvalidParams", "Request field 'params' must be an object.", 400)
        result = handlers.dispatch(tool, params)
        return _success_response(request_id, result)
    except handlers.CommandError as exc:
        return _error_response(request_id, exc.error, exc.message, exc.code, exc.details)
    except Exception as exc:  # noqa: BLE001 - Blender must never crash from remote input.
        return _error_response(
            request_id,
            exc.__class__.__name__,
            str(exc),
            500,
            traceback.format_exc(limit=12),
        )


async def execute_request(request: dict[str, Any], timeout: float = 120.0) -> dict[str, Any]:
    """Execute a request on Blender's main thread from any async thread.

    Args:
        request: Command request dictionary.
        timeout: Maximum seconds to wait for command execution.

    Returns:
        Structured response dictionary.
    """
    if threading.get_ident() == _MAIN_THREAD_ID:
        return dispatch_request(request)

    loop = asyncio.get_running_loop()
    future: asyncio.Future[dict[str, Any]] = loop.create_future()

    def run_on_main_thread() -> None:
        response = dispatch_request(request)
        if not future.done():
            loop.call_soon_threadsafe(future.set_result, response)

    def timer_callback() -> None:
        try:
            run_on_main_thread()
        except Exception as exc:  # noqa: BLE001
            if not future.done():
                loop.call_soon_threadsafe(
                    future.set_result,
                    _error_response(
                        request.get("id"),
                        exc.__class__.__name__,
                        str(exc),
                        500,
                        traceback.format_exc(limit=12),
                    ),
                )
        return None

    bpy.app.timers.register(timer_callback, first_interval=0.0)

    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        return _error_response(
            request.get("id"),
            "Timeout",
            f"Command did not complete within {timeout:.0f} seconds.",
            504,
        )
