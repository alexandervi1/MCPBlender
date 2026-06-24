"""MCP server entry point for Blender AI workflows."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .bridge import BlenderBridge
from .tools import RegisteredTool, build_registry

LOG_DIR = Path.home() / ".blender-ai-mcp" / "logs"


def configure_logging() -> logging.Logger:
    """Configure console and file logging."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("blender-ai-mcp")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    file_handler = logging.FileHandler(
        LOG_DIR / f"mcp-{datetime.now().strftime('%Y%m%d')}.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(stream)
    logger.addHandler(file_handler)
    return logger


async def _run_with_fastmcp() -> None:
    """Run the server with the official MCP SDK."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install dependencies with `pip install -e .` before running MCP.") from exc

    logger = configure_logging()
    bridge = BlenderBridge()
    registry = build_registry()
    mcp = FastMCP("blender-ai-mcp")

    for spec in registry.values():
        _register_fastmcp_tool(mcp, spec, bridge, logger)

    logger.info("Registered %s Blender MCP tools", len(registry))
    await mcp.run_stdio_async()


def _register_fastmcp_tool(
    mcp: Any,
    spec: RegisteredTool,
    bridge: BlenderBridge,
    logger: logging.Logger,
) -> None:
    """Register one tool with FastMCP."""

    async def handler(**arguments: Any) -> str:
        params = dict(arguments)
        logger.info("tool=%s params=%s", spec.name, json.dumps(params, default=str))
        response = await spec.handler(bridge=bridge, params=params)
        if response.get("success") is False:
            logger.error("tool=%s error=%s", spec.name, response)
        return json.dumps(response, ensure_ascii=False, default=str)

    handler.__name__ = spec.name
    handler.__doc__ = f"{spec.description}\n\nInput schema: {json.dumps(spec.input_schema, default=str)}"

    try:
        mcp.add_tool(
            handler,
            name=spec.name,
            description=spec.description,
        )
    except TypeError:
        mcp.tool(name=spec.name, description=spec.description)(handler)


def main() -> None:
    """Run the MCP server over stdio."""
    asyncio.run(_run_with_fastmcp())


if __name__ == "__main__":
    main()
