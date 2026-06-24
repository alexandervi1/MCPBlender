# blender-ai-mcp

`blender-ai-mcp` is a Model Context Protocol server that connects an AI assistant to Blender through a local Blender addon. It lets an assistant create and modify objects, materials, cameras, lights, render settings, animations, UVs, Geometry Nodes, imports, exports, and controlled Python execution from natural-language requests.

The server runs outside Blender and communicates with the addon over a localhost newline-delimited JSON socket. Blender does not need to expose any network service beyond the local machine.

The project also includes professional modeling layers for free-form high-quality assets:

- `modeling_core`: flexible primitives, curves, pipes, booleans, bevels, bounding boxes, snapping, alignment, distribution, component grouping, metadata, object search, and model validation.
- `asset_pipeline`: curated multi-stage asset generation with named components, lowpoly materials, metadata, and quality validation.
- `reference_modeling`: reference images, front/side/top planes, landmarks, scale calibration, orthographic review cameras, and silhouette-bound comparison.
- `hard_surface_modeling`: rounded boxes, tapered cylinders, capsules, panel seams, ring joints, slot cuts, screw arrays, vent grilles, weighted normals, and support-loop bevels.
- `material_pro`: PBR, toon, procedural materials, decals, outlines, edge-wear markers, material assignment, and material variations.
- `quality_validation`: overlap detection, symmetry checks, scale consistency, broad scene quality reports, and improvement suggestions.

## Prerequisites

- Blender 3.6 LTS or newer, including Blender 4.0 and 4.1+
- Python 3.10 or newer
- Claude Desktop or another MCP-compatible client
- Local shell access to install Python dependencies

## Installation

1. Create and activate a virtual environment.

   ```powershell
   cd blender-ai-mcp
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Install the Blender addon from the `blender_addon/` directory.

   In Blender, open `Edit > Preferences > Add-ons > Install...`, select the addon package or `blender_addon/__init__.py`, then enable **AI MCP Bridge**.

3. Start the addon server in Blender.

   Open the 3D Viewport sidebar with `N`, select the **AI MCP** panel, confirm the port is `9876`, and click **Start Server**.

4. Configure Claude Desktop.

   Copy the contents of `mcp_config_example.json` into your Claude Desktop MCP configuration and adjust paths if needed.

5. Restart Claude Desktop and confirm the `blender` MCP server is available.

## Claude Desktop Config

Example configuration:

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

If you use a project virtual environment, set `command` to the absolute path of that environment's Python executable.

## Quick Start

1. Launch Blender.
2. Start the **AI MCP Bridge** addon server.
3. Open Claude Desktop.
4. Ask Claude to inspect the scene:

   ```text
   List every object in my Blender scene and summarize the active camera and render engine.
   ```

5. Create a first object:

   ```text
   Create a matte red cube named HeroCube at the origin, add a bevel modifier, and place a camera looking at it.
   ```

## Example Prompts

1. Create a low-poly island with a plane ocean, three rocks, and a warm sunset lighting setup.
2. Build a product turntable scene for a glass perfume bottle with realistic materials and three-point lighting.
3. Add a camera named CloseupCam, aim it at the active object, and set it as the render camera.
4. Create a metallic blue cylinder, bevel the top edges, and assign a rough brushed-metal material.
5. Make a simple solar system animation with orbiting planets over 250 frames.
6. Import `assets/chair.glb`, scale it to real-world units, and place it in a collection named Furniture.
7. Create a Geometry Nodes scatter setup that places small stones across a ground plane.
8. Set the render engine to Cycles, resolution to 1920x1080, 128 samples, and Filmic color management.
9. Unwrap the selected mesh with smart UV projection and export the UV layout as a PNG.
10. Clear the scene except cameras and lights, then create a studio cyclorama with soft area lighting.

## How It Works

- The MCP client launches the Python MCP server.
- The MCP server validates tool inputs with Pydantic models.
- The bridge sends newline-delimited JSON commands to the Blender addon on `localhost:9876`.
- The addon executes Blender Python operations on Blender's main thread and returns structured JSON responses.
- Every tool returns either a success envelope or a structured error:

```json
{
  "success": false,
  "error": "ObjectNotFound",
  "message": "Object 'Cube' does not exist",
  "code": 404
}
```

## Configuration

Environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `BLENDER_MCP_HOST` | `localhost` | Hostname used by the MCP server to reach Blender. |
| `BLENDER_MCP_PORT` | `9876` | Local socket port exposed by the Blender addon. |

Logs are written to `~/.blender-ai-mcp/logs/`.

## Safety Notes

The `execute_python` and `evaluate_expression` tools are intended for trusted local workflows. They must use strict validation, an import whitelist, and structured error handling. Do not expose the Blender addon socket to a public network.

## More Documentation

- [AI_README.md](AI_README.md): first-use operating guide for an AI assistant using this MCP.
- [SETUP.md](SETUP.md): detailed Windows, macOS, and Linux setup.
- [TOOLS.md](TOOLS.md): complete MCP tool reference.
