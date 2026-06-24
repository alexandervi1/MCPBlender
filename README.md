# blender-ai-mcp

`blender-ai-mcp` is a local Model Context Protocol server and Blender addon bridge for AI-assisted 3D modeling workflows.

The MCP server runs outside Blender and communicates with the Blender addon over a localhost newline-delimited JSON socket. It exposes tools for scene inspection, object creation, materials, cameras, lighting, rendering, animation, import/export, quality checks, and controlled Blender Python execution.

## Features

- Local MCP server for Claude Desktop or another MCP-compatible client.
- Blender addon bridge over `localhost:9876`.
- Tools for objects, materials, cameras, lights, rendering, animation, UVs, Geometry Nodes, imports, exports, and scripted Blender operations.
- Higher-level modeling helpers for hard-surface assets, reference-guided modeling, quality validation, and low-poly asset pipelines.

## Requirements

- Blender 3.6 LTS or newer.
- Python 3.10 or newer.
- Claude Desktop or another MCP-compatible client.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Install and enable the Blender addon from `blender_addon/`, then start the **AI MCP Bridge** server from Blender's 3D Viewport sidebar.

## MCP Configuration

Use `mcp_config_example.json` as a starting point:

```json
{
  "mcpServers": {
    "blender": {
      "command": "python",
      "args": ["-m", "blender_ai_mcp.server.main"],
      "env": {
        "BLENDER_MCP_PORT": "9876",
        "BLENDER_MCP_HOST": "localhost"
      }
    }
  }
}
```

If you use a virtual environment, set `command` to that environment's Python executable.

## Development

```powershell
pip install -e ".[dev]"
pytest
ruff check .
```

More documentation is available in `docs/`:

- `docs/SETUP.md`
- `docs/TOOLS.md`
- `docs/AI_README.md`

## Safety

The `execute_python` and expression-evaluation tools are intended for trusted local workflows. Do not expose the Blender addon socket to a public network.
