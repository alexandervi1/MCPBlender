"""Tests for scene-management MCP tools."""

from __future__ import annotations

import pytest

from conftest import FakeBlenderBridge, assert_error, assert_success, import_tool_module, invoke_tool


@pytest.mark.asyncio
async def test_get_scene_info_returns_core_scene_state() -> None:
    module = import_tool_module("scene")
    bridge = FakeBlenderBridge(
        responses={
            "get_scene_info": {
                "success": True,
                "result": {
                    "name": "Scene",
                    "unit_system": "METRIC",
                    "unit_scale": 1.0,
                    "frame_start": 1,
                    "frame_end": 250,
                    "current_frame": 42,
                    "active_camera": "Camera",
                    "render_engine": "CYCLES",
                },
                "error": None,
            }
        }
    )

    response = await invoke_tool(module, "get_scene_info", {}, bridge)

    result = assert_success(response)
    assert result["name"] == "Scene"
    assert result["active_camera"] == "Camera"
    assert result["render_engine"] == "CYCLES"
    assert bridge.calls[-1].tool == "get_scene_info"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "params"),
    [
        ("set_scene_property", {"property_path": "view_settings.view_transform", "value": "Filmic"}),
        ("set_unit_system", {"system": "METRIC", "scale": 1.0}),
        ("set_frame", {"current": 24}),
        ("set_frame_range", {"start": 1, "end": 120}),
        ("clear_scene", {"keep_types": ["CAMERA", "LIGHT"]}),
        ("list_collections", {}),
        ("create_collection", {"name": "Vehicles"}),
        ("move_to_collection", {"object_names": ["CarBody", "Wheel"], "collection_name": "Vehicles"}),
        ("set_world_color", {"color": [0.02, 0.025, 0.04, 1.0]}),
        ("set_world_color", {"hdri_path": "/assets/studio.exr", "strength": 0.8}),
    ],
)
async def test_scene_tools_forward_valid_payloads(tool_name: str, params: dict[str, object]) -> None:
    module = import_tool_module("scene")
    bridge = FakeBlenderBridge(
        responses={
            tool_name: {
                "success": True,
                "result": {"tool": tool_name, "ok": True},
                "error": None,
            }
        }
    )

    response = await invoke_tool(module, tool_name, params, bridge)

    assert_success(response)
    assert bridge.calls[-1].tool == tool_name
    assert bridge.calls[-1].params == params


@pytest.mark.asyncio
async def test_invalid_frame_range_returns_structured_error_without_bridge_call() -> None:
    module = import_tool_module("scene")
    bridge = FakeBlenderBridge()

    response = await invoke_tool(module, "set_frame_range", {"start": 120, "end": 1}, bridge)

    assert_error(response)
    assert bridge.calls == []
