"""Tests for material MCP tools."""

from __future__ import annotations

import pytest

from conftest import FakeBlenderBridge, assert_error, assert_success, import_tool_module, invoke_tool


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_color", "expected_color"),
    [
        ("#ffcc33", "#ffcc33"),
        ([0.2, 0.4, 0.8, 1.0], [0.2, 0.4, 0.8, 1.0]),
    ],
)
async def test_create_material_accepts_hex_and_rgba_colors(
    base_color: str | list[float],
    expected_color: str | list[float],
) -> None:
    module = import_tool_module("materials")
    bridge = FakeBlenderBridge(
        responses={
            "create_material": {
                "success": True,
                "result": {
                    "material_name": "StudioBlue",
                    "base_color": expected_color,
                    "metallic": 0.1,
                    "roughness": 0.45,
                },
                "error": None,
            }
        }
    )

    response = await invoke_tool(
        module,
        "create_material",
        {
            "material_name": "StudioBlue",
            "base_color": base_color,
            "metallic": 0.1,
            "roughness": 0.45,
            "specular": 0.5,
        },
        bridge,
    )

    result = assert_success(response)
    assert result["base_color"] == expected_color
    assert bridge.calls[-1].tool == "create_material"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "params"),
    [
        ("assign_material", {"object_name": "Cube", "material_name": "StudioBlue"}),
        ("assign_material", {"object_name": "Cube", "material_name": "StudioBlue", "face_indices": [0, 2, 4]}),
        ("list_materials", {}),
        ("delete_material", {"material_name": "UnusedMaterial"}),
        ("set_material_color", {"material_name": "StudioBlue", "color": "#3366ff"}),
        ("set_material_property", {"material_name": "StudioBlue", "property_name": "Roughness", "value": 0.25}),
        ("create_emission_material", {"material_name": "NeonPink", "color": "#ff33aa", "strength": 4.0}),
        ("create_glass_material", {"material_name": "WindowGlass", "color": [0.8, 0.95, 1.0, 0.35], "ior": 1.45, "roughness": 0.02}),
        ("add_texture", {"material_name": "Painted", "image_path": "/assets/diffuse.png", "socket": "Base Color"}),
        (
            "setup_pbr_material",
            {
                "material_name": "CratedMetal",
                "diffuse_map": "/assets/albedo.png",
                "normal_map": "/assets/normal.png",
                "roughness_map": "/assets/roughness.png",
                "metallic_map": "/assets/metallic.png",
            },
        ),
        (
            "setup_advanced_pbr_material",
            {
                "material_name": "CratedMetal",
                "diffuse_map": "/assets/albedo.png",
                "normal_map": "/assets/normal.png",
                "roughness_map": "/assets/roughness.png",
                "metallic_map": "/assets/metallic.png",
                "normal_strength": 1.2,
                "scale": [2.0, 2.0, 2.0],
                "rotation": [0.0, 0.0, 0.0],
                "translation": [0.0, 0.0, 0.0],
                "blend": 0.35,
                "color_tint": "#ffcc33",
                "metallic": 0.5,
                "roughness": 0.25,
            },
        ),
        ("enable_nodes", {"material_name": "LegacyMaterial", "enable": True}),
        ("get_material_info", {"material_name": "StudioBlue"}),
    ],
)
async def test_material_tools_forward_valid_payloads(tool_name: str, params: dict[str, object]) -> None:
    module = import_tool_module("materials")
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
async def test_assign_material_missing_object_returns_structured_error() -> None:
    module = import_tool_module("materials")
    bridge = FakeBlenderBridge(
        responses={
            "assign_material": {
                "success": False,
                "error": "ObjectNotFound",
                "message": "Object 'MissingObject' does not exist.",
                "code": 404,
            }
        }
    )

    response = await invoke_tool(
        module,
        "assign_material",
        {"object_name": "MissingObject", "material_name": "StudioBlue"},
        bridge,
    )

    assert_error(response, expected_error="ObjectNotFound")


@pytest.mark.asyncio
async def test_invalid_material_color_returns_structured_error_without_bridge_call() -> None:
    module = import_tool_module("materials")
    bridge = FakeBlenderBridge()

    response = await invoke_tool(
        module,
        "create_material",
        {"material_name": "BadColor", "base_color": "not-a-color", "metallic": 0.0, "roughness": 0.5},
        bridge,
    )

    assert_error(response)
    assert bridge.calls == []
