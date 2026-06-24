"""Cross-category structured error tests."""

from __future__ import annotations

import pytest

from conftest import FakeBlenderBridge, assert_error, import_tool_module, invoke_tool


@pytest.mark.asyncio
async def test_tools_return_structured_error_when_blender_is_disconnected() -> None:
    module = import_tool_module("objects")
    bridge = FakeBlenderBridge(connected=False)

    response = await invoke_tool(module, "list_objects", {}, bridge)

    assert_error(response, expected_error="BlenderDisconnected")


@pytest.mark.asyncio
async def test_addon_execution_errors_are_not_raised_to_pytest() -> None:
    module = import_tool_module("materials")
    bridge = FakeBlenderBridge(
        responses={
            "get_material_info": {
                "success": False,
                "error": "BlenderExecutionError",
                "message": "Node tree could not be inspected.",
                "code": 500,
            }
        }
    )

    response = await invoke_tool(module, "get_material_info", {"material_name": "BrokenMaterial"}, bridge)

    assert_error(response, expected_error="BlenderExecutionError")


@pytest.mark.asyncio
async def test_invalid_collection_name_is_rejected_without_bridge_call() -> None:
    module = import_tool_module("scene")
    bridge = FakeBlenderBridge()

    response = await invoke_tool(module, "create_collection", {"name": ""}, bridge)

    assert_error(response)
    assert bridge.calls == []
