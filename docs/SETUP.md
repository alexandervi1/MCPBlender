# Setup Guide

This guide covers installing `blender-ai-mcp`, enabling the Blender addon, and connecting an MCP client such as Claude Desktop.

## Common Requirements

- Blender 3.6 LTS or newer
- Python 3.10 or newer
- A local clone or unpacked copy of `blender-ai-mcp`
- Network access to install Python packages
- Claude Desktop or another MCP-compatible client

The Blender addon and MCP server must use the same host and port. The default is `localhost:9876`.

## Windows

1. Open PowerShell in the project directory.

   ```powershell
   cd C:\path\to\blender-ai-mcp
   py -3.10 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. Install the addon in Blender.

   - Open Blender.
   - Go to `Edit > Preferences > Add-ons`.
   - Click `Install...`.
   - Select the addon file or packaged zip from `blender_addon`.
   - Enable **AI MCP Bridge**.

3. Start the addon server.

   - Open the 3D Viewport.
   - Press `N` to open the sidebar.
   - Open the **AI MCP** tab.
   - Set port `9876`.
   - Click **Start Server**.

4. Configure Claude Desktop.

   Claude Desktop configuration is usually stored under:

   ```text
   %APPDATA%\Claude\claude_desktop_config.json
   ```

   Use the absolute path to the virtual environment Python executable if Claude cannot find `python`:

   ```json
   {
     "mcpServers": {
       "blender": {
         "command": "C:\\path\\to\\blender-ai-mcp\\.venv\\Scripts\\python.exe",
         "args": ["-m", "blender_ai_mcp.server.main"],
         "env": {
           "BLENDER_MCP_PORT": "9876",
           "BLENDER_MCP_HOST": "localhost"
         }
       }
     }
   }
   ```

5. Restart Claude Desktop.

## macOS

1. Open Terminal in the project directory.

   ```bash
   cd /path/to/blender-ai-mcp
   python3.10 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. Install and enable the addon in Blender through `Blender > Settings > Add-ons > Install...`.

3. Start the **AI MCP** server from the 3D Viewport sidebar.

4. Configure Claude Desktop.

   Claude Desktop configuration is usually stored under:

   ```text
   ~/Library/Application Support/Claude/claude_desktop_config.json
   ```

   Example using the virtual environment:

   ```json
   {
     "mcpServers": {
       "blender": {
         "command": "/path/to/blender-ai-mcp/.venv/bin/python",
         "args": ["-m", "blender_ai_mcp.server.main"],
         "env": {
           "BLENDER_MCP_PORT": "9876",
           "BLENDER_MCP_HOST": "localhost"
         }
       }
     }
   }
   ```

5. Restart Claude Desktop.

## Linux

1. Open a shell in the project directory.

   ```bash
   cd /path/to/blender-ai-mcp
   python3.10 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. Install and enable the addon in Blender through `Edit > Preferences > Add-ons > Install...`.

3. Start the **AI MCP** server from the 3D Viewport sidebar.

4. Configure your MCP client.

   Claude Desktop configuration path can vary by package, but commonly lives under:

   ```text
   ~/.config/Claude/claude_desktop_config.json
   ```

   Example:

   ```json
   {
     "mcpServers": {
       "blender": {
         "command": "/path/to/blender-ai-mcp/.venv/bin/python",
         "args": ["-m", "blender_ai_mcp.server.main"],
         "env": {
           "BLENDER_MCP_PORT": "9876",
           "BLENDER_MCP_HOST": "localhost"
         }
       }
     }
   }
   ```

5. Restart the MCP client.

## Verifying The Connection

After the addon server and MCP client are running, ask:

```text
Get the Blender scene info and list all objects.
```

Expected behavior:

- The MCP server starts without import errors.
- Blender's **AI MCP** panel shows a connected command or recent log entry.
- The assistant returns scene name, frame range, active camera, render engine, and objects.

## Troubleshooting

### Claude cannot start the server

- Use an absolute path to the virtual environment Python executable.
- Confirm `pip install -r requirements.txt` completed successfully.
- Run the server manually:

  ```bash
  python -m blender_ai_mcp.server.main
  ```

### The server starts but cannot connect to Blender

- Confirm Blender is open.
- Confirm the addon is enabled.
- Confirm the addon server is running.
- Confirm both sides use the same host and port.
- Check for another application already using port `9876`.

### Commands time out

- Long render or import operations can take time inside Blender.
- Check the addon log panel for the last command.
- Check `~/.blender-ai-mcp/logs/` for server-side errors.

### Python version mismatch

Use Python 3.10 or newer for the MCP server. Blender's embedded Python is used only inside Blender by the addon.

## Running Tests

The pytest suite mocks the Blender socket bridge, so Blender is not required for tests.

```bash
pytest tests
```

The bridge tests start a temporary local asyncio server and validate newline-delimited JSON behavior.
