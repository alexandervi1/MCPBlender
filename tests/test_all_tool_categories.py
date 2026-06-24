"""Coverage tests for every MCP tool category."""

from __future__ import annotations

from typing import Any

import pytest

from conftest import FakeBlenderBridge, assert_success, import_tool_module, invoke_tool


TOOL_CASES: dict[str, dict[str, dict[str, Any]]] = {
    "asset_pipeline": {
        "create_lowpoly_asset": {
            "asset_type": "cargo_ship",
            "name": "TestCargoShip",
            "container_rows": 2,
            "container_tiers": 2,
            "quality_target": "clean",
        },
    },
    "modeling_core": {
        "create_primitive": {"type": "beveled_box", "name": "Panel", "size": [2, 1, 0.2], "bevel": 0.03},
        "create_curve_path": {"name": "Cable_Path", "points": [[0, 0, 0], [1, 0, 0], [1, 1, 0]]},
        "create_pipe_along_path": {"name": "Pipe", "points": [[0, 0, 0], [0, 0, 2]], "radius": 0.08},
        "boolean_operation": {"target": "Wall", "cutter": "Window_Cutter", "operation": "DIFFERENCE"},
        "bevel_edges": {"object_name": "Crate", "width": 0.05},
        "set_origin": {"object_name": "Crate", "mode": "GEOMETRY"},
        "get_bounding_box": {"objects": ["Crate"]},
        "snap_to_ground": {"objects": ["Crate"], "ground_z": 0},
        "align_objects": {"objects": ["A", "B"], "axis": "Z", "mode": "MIN"},
        "distribute_objects": {"objects": ["A", "B", "C"], "axis": "X", "spacing": 1.5},
        "duplicate_along_axis": {"object_name": "Fence_Post", "count": 4, "offset": [1.2, 0, 0]},
        "create_component_group": {"name": "Robot", "children": ["Robot.Body"], "metadata": {"role": "asset"}},
        "set_object_metadata": {"objects": ["Robot.Body"], "metadata": {"role": "body"}},
        "find_objects": {"name_contains": "Robot", "limit": 10},
        "validate_model": {"objects": ["Robot.Body"], "check_overlaps": False},
        "setup_subdivision_modeling": {"object_name": "Cube", "levels": 2, "angle_limit": 40.0},
        "remesh_for_sculpting": {"object_name": "Cube", "remesh_type": "VOXEL", "voxel_size": 0.05},
    },
    "reference_modeling": {
        "import_reference_image": {"image_path": "/refs/front.png", "name": "FrontRef", "view": "FRONT"},
        "setup_reference_planes": {"front": "/refs/front.png", "side": "/refs/side.png"},
        "lock_reference": {"objects": ["FrontRef"], "locked": True},
        "set_landmark": {"name": "head_top", "location": [0, 0, 2]},
        "get_landmarks": {"category": "default"},
        "measure_between_landmarks": {"a": "head_top", "b": "feet"},
        "align_object_to_landmarks": {"object_name": "Body", "source_landmark": "feet", "target_landmark": "origin"},
        "calibrate_reference_scale": {"landmark_a": "feet", "landmark_b": "head_top", "real_distance": 1.8},
        "render_orthographic_view": {"view": "FRONT", "render": False},
        "compare_silhouette_bounds": {"objects": ["Body"], "expected_min": [-1, -1, 0], "expected_max": [1, 1, 2]},
    },
    "hard_surface_modeling": {
        "create_rounded_box": {"name": "Crate", "size": [1, 1, 1], "bevel": 0.05},
        "create_tapered_cylinder": {"name": "Nozzle", "radius_bottom": 0.5, "radius_top": 0.25, "depth": 1.5},
        "create_capsule_segment": {"name": "Handle", "radius": 0.1, "length": 1.2},
        "create_panel_seam": {"name": "PanelLine", "location": [0, 0, 0], "size": [1, 0.02, 0.02]},
        "create_ring_joint": {"name": "JointRing", "location": [0, 0, 0], "major_radius": 0.4, "minor_radius": 0.05},
        "create_slot_cut": {"target": "Panel", "location": [0, 0, 0], "size": [0.8, 0.2, 0.1]},
        "add_screw_array": {"points": [[0, 0, 0], [1, 0, 0]], "radius": 0.05},
        "add_vent_grille": {"name": "Vent", "location": [0, 0, 0], "slat_count": 4, "slat_size": [0.5, 0.04, 0.03], "spacing": 0.12},
        "apply_weighted_normals": {"objects": ["Panel"]},
        "add_support_loops": {"object_name": "Panel", "width": 0.02},
    },
    "material_pro": {
        "create_pbr_material": {"name": "PaintedMetal", "base_color": "#336699", "metallic": 0.3},
        "create_toon_material": {"name": "ToonBlue", "base_color": "#3366ff"},
        "create_procedural_material": {"name": "Concrete", "base_color": "#777777", "secondary_color": "#333333"},
        "add_edge_wear": {"material_name": "PaintedMetal", "amount": 0.2},
        "assign_material_by_name": {"objects": ["Panel"], "material_name": "PaintedMetal"},
        "create_decal": {"name": "LogoDecal", "text": "MCP", "location": [0, 0, 1]},
        "add_outline_modifier": {"objects": ["Character"], "thickness": 0.03},
        "apply_material_variation": {"objects": ["PanelA", "PanelB"], "source_material": "PaintedMetal"},
    },
    "quality_validation": {
        "validate_scene_quality": {"objects": ["Panel"], "checks": ["missing_materials"]},
        "detect_overlaps": {"objects": ["A", "B"], "limit": 10},
        "validate_symmetry": {"left_objects": ["Arm_L"], "right_objects": ["Arm_R"]},
        "check_scale_consistency": {"objects": ["Panel"], "min_dimensions": [0.1, 0.1, 0.1]},
        "generate_quality_report": {"objects": ["Panel"]},
        "suggest_model_improvements": {"objects": ["Panel"], "target_quality": "production"},
        "polish_topology": {"objects": ["Cube"], "merge_distance": 0.0001},
    },
    "camera": {
        "create_camera": {"name": "Camera", "camera_type": "PERSP"},
        "set_active_camera": {"name": "Camera"},
        "set_camera_property": {"name": "Camera", "property_name": "lens", "value": 35},
        "point_camera_at": {"name": "Camera", "target_location": [0, 0, 0]},
        "camera_from_view": {"name": "Camera"},
        "add_camera_constraint": {"name": "Camera", "constraint_type": "TRACK_TO", "target_name": "Cube"},
    },
    "lighting": {
        "create_light": {"name": "Key", "light_type": "AREA", "color": "#ffffff"},
        "set_light_property": {"name": "Key", "property_name": "energy", "value": 500},
        "delete_light": {"name": "Key"},
        "list_lights": {},
        "create_three_point_lighting": {"target_object": "Cube"},
        "create_hdri_lighting": {"hdri_path": "/assets/studio.exr"},
        "setup_studio_backdrop_and_lighting": {"backdrop_name": "Studio_Backdrop", "target_object": "Cube"},
    },
    "modifiers": {
        "add_modifier": {"object_name": "Cube", "modifier_type": "BEVEL", "name": "SoftEdges"},
        "set_modifier_property": {"object_name": "Cube", "modifier_name": "SoftEdges", "property_name": "width", "value": 0.1},
        "apply_modifier": {"object_name": "Cube", "modifier_name": "SoftEdges"},
        "remove_modifier": {"object_name": "Cube", "modifier_name": "SoftEdges"},
        "list_modifiers": {"object_name": "Cube"},
        "reorder_modifier": {"object_name": "Cube", "modifier_name": "SoftEdges", "direction": "UP"},
    },
    "animation": {
        "insert_keyframe": {"object_name": "Cube", "data_path": "location", "frame": 1},
        "delete_keyframe": {"object_name": "Cube", "data_path": "location", "frame": 1},
        "set_interpolation": {"object_name": "Cube", "interpolation": "LINEAR"},
        "list_keyframes": {"object_name": "Cube"},
        "create_rotation_animation": {"object_name": "Cube", "start_frame": 1, "end_frame": 60},
        "create_path_animation": {"object_name": "Cube", "path_name": "Path", "start_frame": 1, "end_frame": 60},
        "set_fps": {"fps": 24},
        "bake_animation": {"start_frame": 1, "end_frame": 60},
    },
    "rendering": {
        "set_render_engine": {"engine": "CYCLES"},
        "set_render_resolution": {"width": 1920, "height": 1080},
        "set_render_output": {"output_path": "/tmp/render.png", "file_format": "PNG"},
        "set_cycles_samples": {"render_samples": 64},
        "set_eevee_settings": {"ambient_occlusion": True},
        "render_image": {"output_path": "/tmp/render.png"},
        "render_animation": {"start_frame": 1, "end_frame": 2},
        "set_render_camera": {"camera_name": "Camera"},
        "add_render_pass": {"pass_name": "Z"},
        "set_color_management": {"view_transform": "Filmic"},
    },
    "uv": {
        "unwrap_uv": {"object_name": "Cube", "method": "SMART"},
        "pack_uvs": {"object_name": "Cube"},
        "scale_uvs": {"object_name": "Cube", "scale": [1.0, 1.0]},
        "select_uv_island": {"object_name": "Cube", "face_index": 0},
        "export_uv_layout": {"object_name": "Cube", "output_path": "/tmp/uv.png"},
    },
    "geometry_nodes": {
        "add_geometry_nodes_modifier": {"object_name": "Cube"},
        "create_node": {"object_name": "Cube", "node_type": "GeometryNodeSetPosition"},
        "connect_nodes": {"object_name": "Cube", "from_node": "A", "from_socket": "Geometry", "to_node": "B", "to_socket": "Geometry"},
        "set_node_input": {"object_name": "Cube", "node_name": "A", "input_socket": "Value", "value": 1},
        "set_geonode_input": {"object_name": "Cube", "input_name": "Scale", "value": 2},
        "list_nodes": {"object_name": "Cube"},
    },
    "scripting": {
        "execute_python": {"code": "import math\nprint(math.pi)"},
        "evaluate_expression": {"expression": "1 + 1"},
        "install_addon": {"path": "/tmp/addon.py"},
    },
    "io": {
        "import_file": {"file_path": "/tmp/model.obj"},
        "export_file": {"file_path": "/tmp/model.obj"},
        "import_image_as_plane": {"image_path": "/tmp/image.png"},
        "link_blend_file": {"blend_path": "/tmp/lib.blend", "data_type": "objects", "names": ["Cube"]},
        "append_blend_file": {"blend_path": "/tmp/lib.blend", "data_type": "objects", "names": ["Cube"]},
    },
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module_name", "tool_name", "params"),
    [
        (module_name, tool_name, params)
        for module_name, tools in TOOL_CASES.items()
        for tool_name, params in tools.items()
    ],
)
async def test_all_tool_categories_forward_valid_payloads(
    module_name: str,
    tool_name: str,
    params: dict[str, Any],
) -> None:
    """Every declared tool validates and forwards one representative payload."""
    module = import_tool_module(module_name)
    bridge = FakeBlenderBridge()

    response = await invoke_tool(module, tool_name, params, bridge)

    assert_success(response)
    assert bridge.calls[-1].tool == tool_name
    assert bridge.calls[-1].params == params


def test_every_category_exports_tool_metadata() -> None:
    """Tool modules expose serializable tool definitions."""
    for module_name, cases in TOOL_CASES.items():
        module = import_tool_module(module_name)
        assert set(cases).issubset(module.TOOLS)
        for tool_name in cases:
            schema = module.TOOLS[tool_name].input_schema
            assert schema["type"] == "object"
