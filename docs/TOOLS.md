# Tool Reference

All tools return one of these envelopes.

Success:

```json
{
  "success": true,
  "result": {},
  "error": null
}
```

Error:

```json
{
  "success": false,
  "error": "ObjectNotFound",
  "message": "Object 'Cube' does not exist",
  "code": 404
}
```

Tool inputs are validated with Pydantic v2 before commands are sent to Blender. Vector fields use `[x, y, z]` unless noted. Color fields accept hex strings such as `"#ffcc33"` or RGBA arrays such as `[1.0, 0.8, 0.2, 1.0]`.

## Asset Pipeline

These tools generate complete assets through curated, repeatable stages instead of issuing one primitive command at a time. They are the first layer for Tripo-style workflows: preset-driven generation, component metadata, materials, and automatic quality checks.

| Tool | Parameters | Result |
| --- | --- | --- |
| `create_lowpoly_asset` | `asset_type`, optional `name`, `collection`, `scale`, `quality_target`, `container_rows`, `container_tiers`, `include_crane`, `include_metadata`, `replace_existing` | Complete lowpoly asset, created objects, parent, pipeline stages, and quality report. |

Supported `create_lowpoly_asset.asset_type` values:

```text
cargo_ship, industrial_cargo_ship
```

## Modeling Core

These tools are the recommended low-level layer for free-form modeling. Use them when the user asks for an object that is not covered by a predefined workflow.

| Tool | Parameters | Result |
| --- | --- | --- |
| `create_primitive` | `type`, optional `name`, `location`, `rotation`, `size`, `radius`, `depth`, `bevel`, `segments`, `metadata` | Created primitive, bounds, and metadata. |
| `create_curve_path` | `name`, `points`, optional `bevel_depth`, `cyclic`, `metadata` | Editable curve path. |
| `create_pipe_along_path` | `name`, `points`, `radius`, optional `fill_caps`, `material_name`, `metadata` | Curve-based pipe/tube. |
| `boolean_operation` | `target`, `cutter`, optional `operation`, `apply`, `keep_cutter`, `modifier_name` | Boolean modifier result. |
| `bevel_edges` | `object_name`, `width`, optional `segments`, `affect`, `angle_limit`, `apply` | Bevel modifier result. |
| `set_origin` | `object_name`, optional `mode`, `location` | Updated origin/pivot. |
| `get_bounding_box` | `objects`, optional `include_children` | Per-object and combined bounds. |
| `snap_to_ground` | `objects`, optional `ground_z`, `use_origin` | Objects moved to ground plane. |
| `align_objects` | `objects`, `axis`, optional `mode`, `target` | Aligned object positions. |
| `distribute_objects` | `objects`, `axis`, `spacing` or `start`/`end` | Evenly distributed objects. |
| `duplicate_along_axis` | `object_name`, `count`, `offset`, optional `name_prefix`, `linked` | Created duplicate names. |
| `create_component_group` | `name`, optional `children`, `collection`, `metadata` | Empty parent group with attached children. |
| `set_object_metadata` | `objects`, `metadata`, optional `namespace`, `merge` | Stored semantic metadata. |
| `find_objects` | Optional name/type/material/metadata/bounds filters | Matching objects. |
| `validate_model` | Optional `objects`, overlap/floating/material checks | Quality issues and validity flag. |

Supported `create_primitive.type` values:

```text
cube, box, beveled_box, plane, cylinder, cone, sphere, uv_sphere, icosphere,
torus, wedge, capsule, pipe, column, panel, slab
```

Example:

```json
{
  "tool": "create_primitive",
  "params": {
    "type": "beveled_box",
    "name": "SciFi_Crate.Body",
    "location": [0, 0, 0.6],
    "size": [2.0, 1.2, 1.2],
    "bevel": 0.06,
    "metadata": {
      "asset": "SciFi_Crate",
      "role": "body",
      "editable": true
    }
  }
}
```

Example validation pass:

```json
{
  "tool": "validate_model",
  "params": {
    "objects": ["SciFi_Crate.Body"],
    "check_overlaps": true,
    "check_floating": true,
    "check_missing_materials": true
  }
}
```

## Reference Modeling

Use this layer when accuracy matters. It lets the AI work against images, landmarks, orthographic views, and silhouette bounds instead of guessing proportions.

| Tool | Parameters | Result |
| --- | --- | --- |
| `import_reference_image` | `image_path`, optional `name`, `view`, `location`, `scale`, `opacity`, `locked` | Reference image plane. |
| `setup_reference_planes` | optional `front`, `side`, `top`, `scale`, `opacity`, `collection` | Front/side/top reference setup. |
| `lock_reference` | `objects`, optional `locked`, `hide_select` | Locked reference state. |
| `set_landmark` | `name`, `location`, optional `target_object`, `category`, `metadata` | Stored landmark empty. |
| `get_landmarks` | optional `names`, `category`, `target_object` | Landmark list. |
| `measure_between_landmarks` | `a`, `b` | Distance and vector. |
| `align_object_to_landmarks` | `object_name`, `source_landmark`, `target_landmark`, optional `scale_to_distance` | Object moved/scaled by landmarks. |
| `calibrate_reference_scale` | `landmark_a`, `landmark_b`, `real_distance`, optional `objects` | Reference scale factor. |
| `render_orthographic_view` | `view`, optional `camera_name`, `output_path`, `resolution`, `ortho_scale`, `render` | Review camera/render output. |
| `compare_silhouette_bounds` | `objects`, `expected_min`, `expected_max`, optional `tolerance` | Bounds match score. |

## Hard-Surface Modeling

Use these for robots, vehicles, props, weapons, machines, devices, furniture, and architectural details.

| Tool | Parameters | Result |
| --- | --- | --- |
| `create_rounded_box` | `name`, optional `location`, `size`, `bevel`, `segments`, `material_name`, `metadata` | Rounded box object. |
| `create_tapered_cylinder` | `name`, `radius_bottom`, `radius_top`, `depth`, optional `location`, `vertices`, `bevel`, `material_name` | Tapered cylinder. |
| `create_capsule_segment` | `name`, `radius`, `length`, optional `axis`, `location`, `material_name` | Capsule parts. |
| `create_panel_seam` | `name`, `location`, `size`, optional `target_name`, `orientation`, `material_name` | Panel seam strip. |
| `create_ring_joint` | `name`, `location`, `major_radius`, `minor_radius`, optional `orientation`, `material_name` | Ring/torus joint. |
| `create_slot_cut` | `target`, `location`, `size`, optional `name`, `apply`, `keep_cutter` | Boolean slot cut. |
| `add_screw_array` | `points`, optional `name_prefix`, `radius`, `depth`, `material_name` | Screw/bolt head objects. |
| `add_vent_grille` | `name`, `location`, `slat_count`, `slat_size`, `spacing`, optional `axis`, `material_name` | Vent slats. |
| `apply_weighted_normals` | `objects`, optional `keep_sharp`, `weight` | Weighted normals modifiers. |
| `add_support_loops` | `object_name`, `width`, optional `segments`, `apply` | Support-loop style bevel. |

## Material Pro

Use this layer for stronger look development than flat colors.

| Tool | Parameters | Result |
| --- | --- | --- |
| `create_pbr_material` | `name`, optional `base_color`, `metallic`, `roughness`, `specular`, `alpha`, `texture_paths` | Principled PBR material. |
| `create_toon_material` | `name`, `base_color`, optional `shadow_color`, `levels`, `roughness` | Toon material. |
| `create_procedural_material` | `name`, `base_color`, `secondary_color`, optional `pattern`, `scale`, `strength` | Noise/procedural material. |
| `add_edge_wear` | `material_name`, optional `amount`, `color` | Edge-wear metadata/node marker. |
| `assign_material_by_name` | `objects`, `material_name` | Material assignment. |
| `create_decal` | `name`, optional `target_object`, `image_path`, `text`, `location`, `size`, `color` | Decal plane or text. |
| `add_outline_modifier` | `objects`, optional `thickness`, `edge_color` | Toon outline helper. |
| `apply_material_variation` | `objects`, `source_material`, optional `variation_prefix`, `hue_shift`, `roughness_jitter` | Material variants. |

## Quality Validation

Use these tools after blockout, after detailing, and before final render/export.

| Tool | Parameters | Result |
| --- | --- | --- |
| `validate_scene_quality` | optional `objects`, `checks`, `ground_z`, `tolerance`, `max_vertices` | Quality issue list. |
| `detect_overlaps` | optional `objects`, `ignore_touching`, `tolerance`, `limit` | Bounds overlaps. |
| `validate_symmetry` | `left_objects`, `right_objects`, optional `axis`, `tolerance` | Symmetry score/issues. |
| `check_scale_consistency` | `objects`, `min_dimensions` and/or `max_dimensions` | Scale issues. |
| `generate_quality_report` | optional `objects`, `include_counts`, `include_materials`, `include_collections`, `include_issues` | Scene report. |
| `suggest_model_improvements` | optional `objects`, `target_quality` | Suggested next actions. |

## Objects

| Tool | Parameters | Result |
| --- | --- | --- |
| `create_object` | `object_type`, optional `name`, `location`, `rotation`, `scale` | Created object summary with name, Blender type, transform, dimensions. |
| `delete_object` | `name` or `names`, optional `selection` | Deleted object names. |
| `duplicate_object` | `name`, optional `new_name`, `offset` | New duplicate object summary. |
| `move_object` | `name`, `location`, optional `relative` | Updated location. |
| `rotate_object` | `name`, `rotation`, optional `mode`, `relative` | Updated rotation. |
| `scale_object` | `name`, `scale`, optional `relative` | Updated scale. |
| `rename_object` | `name`, `new_name` | Old and new names. |
| `list_objects` | Optional filters such as `type`, `visible_only` | Objects with type, location, visibility, collection. |
| `get_object_info` | `name` | Vertices, faces, modifiers, materials, dimensions, transform. |
| `select_object` | `name` or `names`, optional `selected`, `active` | Selection state. |
| `join_objects` | `names`, optional `new_name` | Joined object summary. |
| `separate_object` | `name`, `method` (`loose_parts`, `material`, `selection`) | Created object names. |
| `set_object_visibility` | `name`, optional `viewport`, `render` | Visibility state. |
| `parent_object` | `child`, `parent`, optional `keep_transform` | Parent relationship summary. |
| `apply_transform` | `name`, booleans `location`, `rotation`, `scale` | Applied transform flags. |

Supported `create_object.object_type` values: `cube`, `sphere`, `cylinder`, `cone`, `torus`, `plane`, `monkey`, `icosphere`, `uv_sphere`.

Example:

```json
{
  "tool": "create_object",
  "params": {
    "object_type": "cube",
    "name": "HeroCube",
    "location": [0, 0, 1],
    "rotation": [0, 0, 0],
    "scale": [2, 2, 2]
  }
}
```

## Mesh Editing

| Tool | Parameters | Result |
| --- | --- | --- |
| `enter_edit_mode` | `name` | Active object and mode. |
| `exit_edit_mode` | Optional `name` | Active object and mode. |
| `select_mesh_elements` | `name`, `element_type`, `mode`, optional `indices` | Selection count. |
| `extrude` | `name`, optional `axis`, `distance`, `along_normal` | New element summary. |
| `loop_cut` | `name`, `edge_index`, optional `cuts`, `slide` | Added loop count. |
| `bevel` | `name`, `width`, optional `segments`, `affect` | Modified element count. |
| `subdivide` | `name`, optional `cuts` | Modified face count. |
| `merge_vertices` | `name`, `method`, optional `distance` | Merged vertex count. |
| `set_vertex_position` | `name`, `index`, `position` | Updated vertex coordinates. |
| `knife_cut` | `name`, `points` | Cut summary. |
| `inset_faces` | `name`, `thickness`, optional `depth` | Inset face count. |
| `bridge_edge_loops` | `name`, `loop_a`, `loop_b` | Created face count. |
| `flip_normals` | `name` | Affected face count. |
| `recalculate_normals` | `name`, optional `outside` | Affected face count. |

Example:

```json
{
  "tool": "bevel",
  "params": {
    "name": "HeroCube",
    "width": 0.08,
    "segments": 3,
    "affect": "edges"
  }
}
```

## Materials

| Tool | Parameters | Result |
| --- | --- | --- |
| `create_material` | `material_name`, `base_color`, optional `metallic`, `roughness`, `specular`, `alpha`, `use_nodes` | Material summary. |
| `assign_material` | `object_name`, `material_name`, optional `face_indices` | Assignment summary. |
| `list_materials` | Optional `include_nodes`, `include_unused` | Materials with users and node status. |
| `delete_material` | `material_name` | Deleted material name. |
| `set_material_color` | `material_name`, `color` | Updated material color. |
| `set_material_property` | `material_name`, `property_name`, `value`, optional `node_name` | Updated shader input. |
| `create_emission_material` | `material_name`, `color`, `strength` | Material summary. |
| `create_glass_material` | `material_name`, optional `color`, `ior`, `roughness`, `transmission` | Material summary. |
| `add_texture` | `material_name`, `image_path`, `socket` | Node and link summary. |
| `setup_pbr_material` | `material_name`, optional `diffuse_map`, `normal_map`, `roughness_map`, `metallic_map`, `displacement_map` | Created node tree summary. |
| `enable_nodes` | `material_name`, `enable`, optional `reset_tree` | Node state. |
| `get_material_info` | `material_name`, optional `include_node_links`, `include_users` | Node tree, sockets, links, users. |

Example:

```json
{
  "tool": "create_material",
  "params": {
    "material_name": "BrushedBlueMetal",
    "base_color": "#3366ff",
    "metallic": 1.0,
    "roughness": 0.32,
    "specular": 0.5
  }
}
```

## Scene

| Tool | Parameters | Result |
| --- | --- | --- |
| `get_scene_info` | None | Name, unit scale, frame range, active camera, render engine. |
| `set_scene_property` | `property_path`, `value` | Updated property path and value. |
| `set_unit_system` | `system`, optional `scale` | Unit settings. |
| `set_frame` | Optional `current`, `start`, `end` | Frame settings. |
| `set_frame_range` | `start`, `end` | Frame range. |
| `clear_scene` | Optional `keep_types` | Removed object count. |
| `list_collections` | None | Collections with objects and children. |
| `create_collection` | `name`, optional `parent` | Collection summary. |
| `move_to_collection` | `object_names`, `collection_name` | Moved object names. |
| `set_world_color` | `color` or `hdri_path`, optional `strength` | World lighting summary. |

Example:

```json
{
  "tool": "set_frame_range",
  "params": {
    "start": 1,
    "end": 120
  }
}
```

## Camera

| Tool | Parameters | Result |
| --- | --- | --- |
| `create_camera` | `name`, `type`, `location`, `rotation` | Camera summary. |
| `set_active_camera` | `name` | Active camera name. |
| `set_camera_property` | `name`, `property`, `value` | Updated camera property. |
| `point_camera_at` | `name`, `target_object` or `target_location` | Updated rotation. |
| `camera_from_view` | `name` or optional active viewport context | Camera transform. |
| `add_camera_constraint` | `name`, `constraint_type`, parameters | Constraint summary. |

Example:

```json
{
  "tool": "point_camera_at",
  "params": {
    "name": "ProductCam",
    "target_object": "HeroCube"
  }
}
```

## Lighting

| Tool | Parameters | Result |
| --- | --- | --- |
| `create_light` | `name`, `type`, `location`, optional `energy`, `color` | Light summary. |
| `set_light_property` | `name`, `property`, `value` | Updated light property. |
| `delete_light` | `name` | Deleted light name. |
| `list_lights` | None | Lights with type, energy, color, transform. |
| `create_three_point_lighting` | Optional `target_object`, `scale`, `energy` | Key, fill, and rim light summaries. |
| `create_hdri_lighting` | `image_path`, optional `strength` | World HDRI summary. |

Example:

```json
{
  "tool": "create_light",
  "params": {
    "name": "KeyLight",
    "type": "AREA",
    "location": [3, -4, 5],
    "energy": 600,
    "color": "#fff4dd"
  }
}
```

## Modifiers

| Tool | Parameters | Result |
| --- | --- | --- |
| `add_modifier` | `object_name`, `modifier_type`, optional `name`, `properties` | Modifier summary. |
| `set_modifier_property` | `object_name`, `modifier_name`, `property`, `value` | Updated property. |
| `apply_modifier` | `object_name`, `modifier_name` | Applied modifier name. |
| `remove_modifier` | `object_name`, `modifier_name` | Removed modifier name. |
| `list_modifiers` | `object_name` | Modifier stack. |
| `reorder_modifier` | `object_name`, `modifier_name`, `direction` or `index` | New stack order. |

Common modifier types include `SUBSURF`, `MIRROR`, `ARRAY`, `SOLIDIFY`, `BEVEL`, `BOOLEAN`, `DECIMATE`, `SKIN`, `SCREW`, `WELD`, `REMESH`, `SHRINKWRAP`, `CURVE`, `LATTICE`, `DISPLACE`, and `WAVE`.

Example:

```json
{
  "tool": "add_modifier",
  "params": {
    "object_name": "HeroCube",
    "modifier_type": "BEVEL",
    "name": "SoftEdges",
    "properties": {
      "width": 0.05,
      "segments": 3
    }
  }
}
```

## Animation

| Tool | Parameters | Result |
| --- | --- | --- |
| `insert_keyframe` | `object_name`, `data_path`, `frame`, optional `index` | Inserted keyframe summary. |
| `delete_keyframe` | `object_name`, `data_path`, `frame`, optional `index` | Deleted keyframe summary. |
| `set_interpolation` | `object_name`, `data_path`, `interpolation` | Updated F-curve interpolation. |
| `list_keyframes` | `object_name` | Keyframes grouped by data path. |
| `create_rotation_animation` | `object_name`, `axis`, `start_frame`, `end_frame`, optional `turns` | Animation summary. |
| `create_path_animation` | `object_name`, `path_name`, `start_frame`, `end_frame` | Path constraint and keyframe summary. |
| `set_fps` | `fps` | Render FPS. |
| `bake_animation` | `object_name`, `start_frame`, `end_frame`, optional `visual_keying` | Baked frame count. |

Example:

```json
{
  "tool": "create_rotation_animation",
  "params": {
    "object_name": "TurntableObject",
    "axis": "Z",
    "start_frame": 1,
    "end_frame": 120,
    "turns": 1
  }
}
```

## Rendering

| Tool | Parameters | Result |
| --- | --- | --- |
| `set_render_engine` | `engine` (`CYCLES`, `EEVEE`, `WORKBENCH`) | Engine settings. |
| `set_render_resolution` | `width`, `height`, optional `percentage` | Resolution settings. |
| `set_render_output` | `path`, `file_format`, optional `color_depth` | Output settings. |
| `set_cycles_samples` | `render_samples`, optional `viewport_samples` | Cycles sample settings. |
| `set_eevee_settings` | Optional AO, bloom, shadows, SSR settings | Eevee settings. |
| `render_image` | `path`, optional `camera`, `wait` | Render job or saved file summary. |
| `render_animation` | Optional `start`, `end`, `path`, `wait` | Render job summary. |
| `set_render_camera` | `camera_name` | Active render camera. |
| `add_render_pass` | `pass_name`, optional `enabled` | Render pass settings. |
| `set_color_management` | Optional `display_device`, `view_transform`, `look`, `exposure`, `gamma` | Color management settings. |

Example:

```json
{
  "tool": "set_render_resolution",
  "params": {
    "width": 1920,
    "height": 1080,
    "percentage": 100
  }
}
```

## UV

| Tool | Parameters | Result |
| --- | --- | --- |
| `unwrap_uv` | `object_name`, `method`, optional method settings | UV unwrap summary. |
| `pack_uvs` | `object_name`, optional `margin`, `rotate` | Packed island summary. |
| `scale_uvs` | `object_name`, `scale`, optional `origin` | Updated UV scale. |
| `select_uv_island` | `object_name`, optional `uv_coordinate` or `face_index` | Selected island summary. |
| `export_uv_layout` | `object_name`, `path`, optional `size`, `opacity` | Exported image path. |

Example:

```json
{
  "tool": "unwrap_uv",
  "params": {
    "object_name": "Crate",
    "method": "smart_project",
    "angle_limit": 66
  }
}
```

## Geometry Nodes

| Tool | Parameters | Result |
| --- | --- | --- |
| `add_geometry_nodes_modifier` | `object_name`, optional `modifier_name` | Modifier and node group summary. |
| `create_node` | `object_name`, `modifier_name`, `node_type`, optional `name`, `location` | Node summary. |
| `connect_nodes` | `object_name`, `modifier_name`, `from_node`, `from_socket`, `to_node`, `to_socket` | Link summary. |
| `set_node_input` | `object_name`, `modifier_name`, `node_name`, `input_name`, `value` | Updated socket summary. |
| `set_geonode_input` | `object_name`, `modifier_name`, `input_name`, `value` | Updated group input summary. |
| `list_nodes` | `object_name`, `modifier_name` | Nodes, sockets, and links. |

Example:

```json
{
  "tool": "create_node",
  "params": {
    "object_name": "Ground",
    "modifier_name": "ScatterNodes",
    "node_type": "GeometryNodeDistributePointsOnFaces",
    "name": "Distribute Stones",
    "location": [200, 0]
  }
}
```

## Scripting

| Tool | Parameters | Result |
| --- | --- | --- |
| `execute_python` | `code`, optional `timeout_seconds` | `stdout`, `stderr`, optional result, executed line count. |
| `evaluate_expression` | `expression` | Evaluated JSON-serializable result. |
| `install_addon` | `path`, optional `enable` | Installed addon module and enabled state. |

`execute_python` must sandbox code and restrict imports to `bpy`, `mathutils`, `math`, `bmesh`, `os`, and `json`.

Example:

```json
{
  "tool": "evaluate_expression",
  "params": {
    "expression": "len(bpy.data.objects)"
  }
}
```

## Import And Export

| Tool | Parameters | Result |
| --- | --- | --- |
| `import_file` | `path`, optional `format`, `options` | Imported object names. |
| `export_file` | `path`, optional `format`, `selection_only`, `options` | Exported file path and object count. |
| `import_image_as_plane` | `image_path`, optional `name`, `size`, `location` | Plane and material summary. |
| `link_blend_file` | `blend_path`, `data_type`, `names`, optional `collection` | Linked datablock names. |
| `append_blend_file` | `blend_path`, `data_type`, `names`, optional `collection` | Appended datablock names. |

Supported import and export formats include OBJ, FBX, GLTF/GLB, STL, PLY, ABC, USD, SVG, and DXF when Blender has the corresponding importer or exporter enabled.

Example:

```json
{
  "tool": "export_file",
  "params": {
    "path": "/projects/showcase/model.glb",
    "format": "GLB",
    "selection_only": true,
    "options": {
      "apply_modifiers": true,
      "triangulate": false
    }
  }
}
```

## Error Codes

| Code | Meaning |
| --- | --- |
| `400` | Invalid parameters or validation failure. |
| `404` | Requested object, material, collection, node, or file was not found. |
| `409` | Operation conflicts with the current Blender state. |
| `500` | Blender execution failed. |
| `503` | Blender addon bridge is unavailable. |
