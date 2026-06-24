"""Tests for object and mesh-editing MCP tools."""

from __future__ import annotations

import pytest

from conftest import FakeBlenderBridge, assert_error, assert_success, import_tool_module, invoke_tool


PRIMITIVES = [
    "cube",
    "sphere",
    "cylinder",
    "cone",
    "torus",
    "plane",
    "monkey",
    "icosphere",
    "uv_sphere",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("object_type", PRIMITIVES)
async def test_create_object_supports_all_requested_primitives(object_type: str) -> None:
    module = import_tool_module("objects")
    bridge = FakeBlenderBridge(
        responses={
            "create_object": {
                "success": True,
                "result": {
                    "name": f"Test_{object_type}",
                    "type": "MESH",
                    "object_type": object_type,
                },
                "error": None,
            }
        }
    )

    response = await invoke_tool(
        module,
        "create_object",
        {
            "object_type": object_type,
            "name": f"Test_{object_type}",
            "location": [1.0, 2.0, 3.0],
            "rotation": [0.0, 0.0, 0.5],
            "scale": [1.0, 1.5, 2.0],
        },
        bridge,
    )

    result = assert_success(response)
    assert result["object_type"] == object_type
    assert bridge.calls[-1].tool == "create_object"
    assert bridge.calls[-1].params["object_type"] == object_type
    assert bridge.calls[-1].params["location"] == [1.0, 2.0, 3.0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "params"),
    [
        ("delete_object", {"name": "Cube"}),
        ("duplicate_object", {"name": "Cube", "new_name": "Cube_Copy", "offset": [1, 0, 0]}),
        ("move_object", {"name": "Cube", "location": [2, 3, 4], "relative": False}),
        ("rotate_object", {"name": "Cube", "rotation": [0, 0, 1.5708], "mode": "euler", "relative": False}),
        ("scale_object", {"name": "Cube", "scale": [2, 2, 2], "relative": False}),
        ("rename_object", {"name": "Cube", "new_name": "HeroCube"}),
        ("list_objects", {}),
        ("get_object_info", {"name": "Cube"}),
        ("select_object", {"name": "Cube", "selected": True, "active": True}),
        ("join_objects", {"names": ["Cube", "Cylinder"], "new_name": "Combined"}),
        ("separate_object", {"name": "Combined", "method": "loose_parts"}),
        ("set_object_visibility", {"name": "Cube", "viewport": True, "render": False}),
        ("parent_object", {"child": "Wheel", "parent": "CarBody", "keep_transform": True}),
        ("apply_transform", {"name": "Cube", "location": True, "rotation": True, "scale": True}),
    ],
)
async def test_object_tools_forward_valid_payloads(tool_name: str, params: dict[str, object]) -> None:
    module = import_tool_module("objects")
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
@pytest.mark.parametrize(
    ("tool_name", "params"),
    [
        ("enter_edit_mode", {"name": "Cube"}),
        ("exit_edit_mode", {}),
        ("select_mesh_elements", {"name": "Cube", "element_type": "face", "mode": "indices", "indices": [0, 1]}),
        ("extrude", {"name": "Cube", "axis": [0, 0, 1], "distance": 1.25}),
        ("loop_cut", {"name": "Cube", "edge_index": 4, "cuts": 2, "slide": 0.0}),
        ("bevel", {"name": "Cube", "width": 0.1, "segments": 3, "affect": "edges"}),
        ("subdivide", {"name": "Cube", "cuts": 2}),
        ("merge_vertices", {"name": "Cube", "method": "by_distance", "distance": 0.001}),
        ("set_vertex_position", {"name": "Cube", "index": 0, "position": [0.0, 0.0, 1.0]}),
        ("knife_cut", {"name": "Cube", "points": [[0, 0, 0], [1, 0, 0]]}),
        ("inset_faces", {"name": "Cube", "thickness": 0.05, "depth": 0.0}),
        ("bridge_edge_loops", {"name": "Cube", "loop_a": [0, 1, 2], "loop_b": [3, 4, 5]}),
        ("flip_normals", {"name": "Cube"}),
        ("recalculate_normals", {"name": "Cube", "outside": True}),
    ],
)
async def test_mesh_editing_tools_forward_valid_payloads(tool_name: str, params: dict[str, object]) -> None:
    module = import_tool_module("objects")
    bridge = FakeBlenderBridge(
        responses={
            tool_name: {
                "success": True,
                "result": {"tool": tool_name, "changed": True},
                "error": None,
            }
        }
    )

    response = await invoke_tool(module, tool_name, params, bridge)

    assert_success(response)
    assert bridge.calls[-1].tool == tool_name
    assert bridge.calls[-1].params == params


@pytest.mark.asyncio
async def test_object_not_found_returns_structured_error() -> None:
    module = import_tool_module("objects")
    bridge = FakeBlenderBridge(
        responses={
            "move_object": {
                "success": False,
                "error": "ObjectNotFound",
                "message": "Object 'MissingCube' does not exist.",
                "code": 404,
            }
        }
    )

    response = await invoke_tool(
        module,
        "move_object",
        {"name": "MissingCube", "location": [0, 0, 0], "relative": False},
        bridge,
    )

    assert_error(response, expected_error="ObjectNotFound")


@pytest.mark.asyncio
async def test_invalid_create_object_params_are_rejected_before_bridge_call() -> None:
    module = import_tool_module("objects")
    bridge = FakeBlenderBridge()

    response = await invoke_tool(
        module,
        "create_object",
        {"object_type": "unsupported_shape", "location": [1, 2]},
        bridge,
    )

    assert_error(response)
    assert bridge.calls == []
