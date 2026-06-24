"""Blender addon entry point for the AI MCP Bridge."""

import json
from typing import Any

import bpy
from bpy.props import BoolProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from . import server

bl_info = {
    "name": "AI MCP Bridge",
    "author": "blender-ai-mcp",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > AI MCP",
    "description": "Connects Blender to AI via MCP protocol",
    "category": "Interface",
}


class AIMCPBridgeState(PropertyGroup):
    """UI state for the AI MCP Bridge addon."""

    port: IntProperty(
        name="Port",
        description="Localhost port used by the AI MCP socket server",
        default=server.DEFAULT_PORT,
        min=1024,
        max=65535,
    )
    host: StringProperty(
        name="Host",
        description="Loopback interface used by the AI MCP socket server",
        default=server.DEFAULT_HOST,
    )
    last_result: StringProperty(
        name="Last Result",
        description="Last debug execution result",
        default="",
    )
    auto_start: BoolProperty(
        name="Auto Start",
        description="Start the bridge when the addon is registered",
        default=False,
    )


class AIMCP_OT_start_server(Operator):
    """Start the local AI MCP socket server."""

    bl_idname = "aimcp.start_server"
    bl_label = "Start AI MCP Server"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        state = context.window_manager.ai_mcp_bridge
        started = server.start(port=state.port, host=state.host)
        self.report({"INFO"}, "AI MCP server started" if started else "AI MCP server already running")
        return {"FINISHED"}


class AIMCP_OT_stop_server(Operator):
    """Stop the local AI MCP socket server."""

    bl_idname = "aimcp.stop_server"
    bl_label = "Stop AI MCP Server"
    bl_options = {"REGISTER"}

    def execute(self, _context: bpy.types.Context) -> set[str]:
        stopped = server.stop()
        self.report({"INFO"}, "AI MCP server stopping" if stopped else "AI MCP server was not running")
        return {"FINISHED"}


class AIMCP_OT_execute_last_command(Operator):
    """Execute the last socket command again for debugging."""

    bl_idname = "aimcp.execute_last_command"
    bl_label = "Execute Last Command"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        state = context.window_manager.ai_mcp_bridge
        response = server.execute_last_command()
        state.last_result = _compact_json(response)
        if response.get("success"):
            self.report({"INFO"}, "Last command executed")
        else:
            error = response.get("error") or {}
            self.report({"ERROR"}, error.get("message", "Command failed"))
        return {"FINISHED"}


class AIMCP_PT_panel(Panel):
    """Sidebar panel for AI MCP Bridge controls."""

    bl_label = "AI MCP"
    bl_idname = "AIMCP_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI MCP"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        state = context.window_manager.ai_mcp_bridge
        running = server.is_running()
        host, port = server.address()

        status_row = layout.row(align=True)
        status_row.label(text=f"Status: {'Running' if running else 'Stopped'}", icon="CHECKMARK" if running else "X")
        if running:
            status_row.label(text=f"{host}:{port}")

        layout.prop(state, "host")
        layout.prop(state, "port")

        controls = layout.row(align=True)
        controls.enabled = not running
        controls.operator(AIMCP_OT_start_server.bl_idname, icon="PLAY")
        controls = layout.row(align=True)
        controls.enabled = running
        controls.operator(AIMCP_OT_stop_server.bl_idname, icon="PAUSE")

        layout.separator()
        layout.operator(AIMCP_OT_execute_last_command.bl_idname, icon="CONSOLE")
        if state.last_result:
            box = layout.box()
            box.label(text="Last Result")
            for line in _wrap_text(state.last_result, 80)[:4]:
                box.label(text=line)

        layout.separator()
        layout.label(text="Logs")
        log_box = layout.box()
        logs = server.get_logs()
        if not logs:
            log_box.label(text="No log messages")
        for entry in logs[-20:]:
            log_box.label(text=entry)


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))[:2048]


def _wrap_text(text: str, width: int) -> list[str]:
    return [text[index : index + width] for index in range(0, len(text), width)] or [""]


classes = (
    AIMCPBridgeState,
    AIMCP_OT_start_server,
    AIMCP_OT_stop_server,
    AIMCP_OT_execute_last_command,
    AIMCP_PT_panel,
)


def register() -> None:
    """Register Blender addon classes and properties."""
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.ai_mcp_bridge = PointerProperty(type=AIMCPBridgeState)


def unregister() -> None:
    """Unregister Blender addon classes and stop the socket server."""
    server.stop()
    if hasattr(bpy.types.WindowManager, "ai_mcp_bridge"):
        del bpy.types.WindowManager.ai_mcp_bridge
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
