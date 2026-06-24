# blender-ai-mcp

`blender-ai-mcp` is a local Model Context Protocol server plus Blender addon bridge for AI-assisted 3D workflows.

It lets an MCP client inspect the live Blender scene and perform controlled operations on objects, materials, cameras, lights, render settings, animation, UVs, Geometry Nodes, imports, exports, and Python execution.

## What Is Included

- `server/`: Python MCP server and tool registry.
- `blender_addon/`: Blender addon that receives commands from the local bridge.
- `blender_ai_mcp/`: package entry points for MCP clients.
- `docs/`: setup, tool reference, and AI usage notes.

## Requirements

- Blender 3.6 LTS or newer.
- Python 3.10 or newer.
- Claude Desktop or another MCP-compatible client.

## Quick Start

1. Create and activate a virtual environment.

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Install the addon from `blender_addon/`.

   In Blender, open `Edit > Preferences > Add-ons > Install...`, select `blender_addon/__init__.py`, and enable **AI MCP Bridge**.

3. Start the addon server in Blender.

   In the 3D Viewport sidebar, open the **AI MCP** panel, confirm port `9876`, and click **Start Server**.

4. Configure your MCP client using `mcp_config_example.json`.

5. Restart the client and confirm the `blender` server is available.

## MCP Config

Example:

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

If you use a project virtual environment, set `command` to that environment's Python executable.

## Typical Workflow

1. Inspect the live scene with `get_scene_info` and `list_objects`.
2. Create or reuse the target object.
3. Fix the origin if `location` and `bounding_box_center` do not match.
4. Position, align, and duplicate objects using the layout tools.
5. Apply materials and modifiers.
6. Validate overlaps, scale, and scene quality.
7. Render a viewport preview before reporting the task done.

## Validation

Run the test suite after code changes:

```powershell
pytest
```

Useful checks:

- `ruff check .`
- `uv run --extra dev pytest tests`

## Documentation

- [Setup guide](docs/SETUP.md)
- [Tool reference](docs/TOOLS.md)
- [AI usage guide](docs/AI_README.md)

## Safety

The `execute_python` and expression-evaluation tools are for trusted local workflows only. Do not expose the Blender addon socket to a public network.

## License

MIT. See [LICENSE](LICENSE).
