"""Blender command handlers used by the addon socket server."""

from __future__ import annotations

import ast
import contextlib
import importlib
import io
import json
import math
import os
import traceback
from collections.abc import Callable
from typing import Any

import bpy
import bmesh
from mathutils import Vector


class CommandError(Exception):
    """Structured command failure."""

    def __init__(self, error: str, message: str, code: int = 400, details: Any | None = None) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.code = code
        self.details = details


Handler = Callable[[dict[str, Any]], Any]


def dispatch(tool: str, params: dict[str, Any]) -> Any:
    """Dispatch a socket command to a Blender handler."""
    handler = HANDLERS.get(tool)
    if handler is None:
        raise CommandError("UnknownTool", f"Tool '{tool}' is not implemented.", 404)
    return handler(params)


def _object(name: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise CommandError("ObjectNotFound", f"Object '{name}' does not exist.", 404)
    return obj


def _material(name: str) -> bpy.types.Material:
    material = bpy.data.materials.get(name)
    if material is None:
        raise CommandError("MaterialNotFound", f"Material '{name}' does not exist.", 404)
    return material


def _get_fcurves(obj: bpy.types.Object) -> list[bpy.types.FCurve]:
    if not obj.animation_data or not obj.animation_data.action:
        return []
    action = obj.animation_data.action
    if hasattr(action, "is_action_layered") and not action.is_action_legacy:
        fcurves = []
        for layer in action.layers:
            for strip in layer.strips:
                if hasattr(strip, "channelbags"):
                    for cb in strip.channelbags:
                        if hasattr(cb, "fcurves"):
                            fcurves.extend(cb.fcurves)
        return fcurves
    else:
        if hasattr(action, "fcurves"):
            return list(action.fcurves)
    return []


def _vec(value: Any, default: tuple[float, float, float]) -> tuple[float, float, float]:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        val = float(value)
        return (val, val, val)
    try:
        if len(value) == 1:
            val = float(value[0])
            return (val, val, val)
    except Exception:
        pass
    return tuple(float(item) for item in value[:3])


def _color(value: Any) -> tuple[float, float, float, float]:
    if isinstance(value, str):
        hex_value = value.removeprefix("#")
        if len(hex_value) not in {6, 8}:
            raise CommandError("InvalidColor", "Use #RRGGBB or #RRGGBBAA.", 400)
        channels = [int(hex_value[index : index + 2], 16) / 255 for index in range(0, len(hex_value), 2)]
        if len(channels) == 3:
            channels.append(1.0)
        return tuple(channels)  # type: ignore[return-value]
    if len(value) == 3:
        return float(value[0]), float(value[1]), float(value[2]), 1.0
    return tuple(float(item) for item in value[:4])  # type: ignore[return-value]


def _is_close(v1: Any, v2: Any, tol: float = 0.001) -> bool:
    try:
        return all(abs(a - b) < tol for a, b in zip(v1, v2))
    except Exception:
        return False


def _object_summary(obj: bpy.types.Object) -> dict[str, Any]:
    if hasattr(obj, "bound_box") and obj.bound_box:
        center = list(_bounds_for(obj)["center"])
        matches = _is_close(obj.location, center, tol=0.001)
    else:
        center = list(obj.location)
        matches = True

    return {
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "rotation": list(obj.rotation_euler),
        "scale": list(obj.scale),
        "visible": obj.visible_get(),
        "hide_viewport": obj.hide_viewport,
        "hide_render": obj.hide_render,
        "bounding_box_center": center,
        "origin_matches_center": matches,
    }


def _bounds_for(obj: bpy.types.Object) -> dict[str, Any]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_v = Vector((min(point.x for point in corners), min(point.y for point in corners), min(point.z for point in corners)))
    max_v = Vector((max(point.x for point in corners), max(point.y for point in corners), max(point.z for point in corners)))
    center = (min_v + max_v) / 2
    return {
        "name": obj.name,
        "min": list(min_v),
        "max": list(max_v),
        "center": list(center),
        "dimensions": list(max_v - min_v),
    }


def _metadata_key(namespace: str) -> str:
    return f"{namespace}:metadata"


def _read_metadata(obj: bpy.types.Object, namespace: str = "mcp") -> dict[str, Any]:
    raw = obj.get(_metadata_key(namespace))
    if isinstance(raw, str):
        with contextlib.suppress(Exception):
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                return decoded
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _write_metadata(obj: bpy.types.Object, metadata: dict[str, Any], namespace: str = "mcp", merge: bool = True) -> dict[str, Any]:
    current = _read_metadata(obj, namespace) if merge else {}
    current.update(metadata)
    obj[_metadata_key(namespace)] = json.dumps(current, ensure_ascii=False, default=str)
    for key, value in current.items():
        if isinstance(value, str | int | float | bool):
            obj[f"{namespace}:{key}"] = value
    return current


def _ensure_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    return collection


def _link_to_collection(obj: bpy.types.Object, collection_name: str) -> None:
    collection = _ensure_collection(collection_name)
    if obj.name not in {item.name for item in collection.objects}:
        collection.objects.link(obj)


def _assign_material_if_available(obj: bpy.types.Object, material_name: str | None) -> None:
    if material_name:
        obj.data.materials.append(_material(material_name))


def _link_object(obj: bpy.types.Object, collection_name: str | None = None) -> bpy.types.Object:
    """Link an object without relying on a viewport operator context."""
    if collection_name:
        collection = _ensure_collection(collection_name)
    else:
        collection = bpy.context.collection or bpy.context.scene.collection
    if obj.name not in collection.objects:
        collection.objects.link(obj)
    return obj


def _shade_flat(obj: bpy.types.Object) -> None:
    if getattr(obj, "data", None) and hasattr(obj.data, "polygons"):
        for polygon in obj.data.polygons:
            polygon.use_smooth = False


def _material_named(
    name: str,
    color: Any = "#ffffff",
    *,
    metallic: float = 0.0,
    roughness: float = 0.6,
) -> bpy.types.Material:
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = _color(color)
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        values = {
            "Base Color": material.diffuse_color,
            "Metallic": metallic,
            "Roughness": roughness,
            "Specular IOR Level": 0.45,
            "Specular": 0.45,
        }
        for socket, value in values.items():
            if socket in bsdf.inputs:
                bsdf.inputs[socket].default_value = value
    return material


def _box_object(
    name: str,
    size: tuple[float, float, float],
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    material: bpy.types.Material | None = None,
    collection_name: str | None = None,
) -> bpy.types.Object:
    sx, sy, sz = abs(size[0]) / 2, abs(size[1]) / 2, abs(size[2]) / 2
    verts = [
        (-sx, -sy, -sz),
        (sx, -sy, -sz),
        (sx, sy, -sz),
        (-sx, sy, -sz),
        (-sx, -sy, sz),
        (sx, -sy, sz),
        (sx, sy, sz),
        (-sx, sy, sz),
    ]
    faces = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.rotation_euler = rotation
    if material:
        obj.data.materials.append(material)
    _shade_flat(obj)
    return _link_object(obj, collection_name)


def _plane_object(
    name: str,
    size: tuple[float, float, float],
    location: tuple[float, float, float],
    rotation: tuple[float, float, float],
    collection_name: str | None = None,
) -> bpy.types.Object:
    sx, sy = abs(size[0]) / 2, abs(size[1]) / 2
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata([(-sx, -sy, 0.0), (sx, -sy, 0.0), (sx, sy, 0.0), (-sx, sy, 0.0)], [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.rotation_euler = rotation
    return _link_object(obj, collection_name)


def _lowpoly_cylinder_object(
    name: str,
    radius: float,
    depth: float,
    segments: int,
    location: tuple[float, float, float],
    material: bpy.types.Material | None = None,
    collection_name: str | None = None,
) -> bpy.types.Object:
    segments = max(3, int(segments))
    half = depth / 2
    verts = []
    for z in (-half, half):
        for index in range(segments):
            angle = math.tau * index / segments
            verts.append((radius * math.cos(angle), radius * math.sin(angle), z))
    top_center = len(verts)
    verts.append((0.0, 0.0, half))
    bottom_center = len(verts)
    verts.append((0.0, 0.0, -half))
    faces = []
    for index in range(segments):
        next_index = (index + 1) % segments
        faces.append((index, next_index, segments + next_index, segments + index))
        faces.append((top_center, segments + index, segments + next_index))
        faces.append((bottom_center, next_index, index))
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    if material:
        obj.data.materials.append(material)
    _shade_flat(obj)
    return _link_object(obj, collection_name)


def _axis_index(axis: str) -> int:
    return {"X": 0, "Y": 1, "Z": 2}[axis]


def _hex_or_rgba(value: Any) -> tuple[float, float, float, float]:
    return _color(value)


def _landmark_object_name(name: str) -> str:
    return f"Landmark.{name}"


def _landmark_data(obj: bpy.types.Object) -> dict[str, Any]:
    return {
        "name": obj.name.removeprefix("Landmark."),
        "location": list(obj.location),
        "category": obj.get("mcp:landmark_category", "default"),
        "target_object": obj.get("mcp:target_object"),
        "metadata": _read_metadata(obj, "landmark"),
    }


def _get_landmark(name: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(_landmark_object_name(name)) or bpy.data.objects.get(name)
    if obj is None or not obj.get("mcp:is_landmark"):
        raise CommandError("LandmarkNotFound", f"Landmark '{name}' does not exist.", 404)
    return obj


def _create_reference_plane_object(
    image_path: str,
    name: str,
    view: str,
    location: tuple[float, float, float],
    scale: float,
    opacity: float,
) -> bpy.types.Object:
    image = bpy.data.images.load(image_path)
    material = bpy.data.materials.new(f"{name}_Material")
    material.use_nodes = True
    material.blend_method = "BLEND"
    material.diffuse_color = (1, 1, 1, opacity)
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    if bsdf:
        material.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = opacity
    bpy.ops.mesh.primitive_plane_add(size=scale, location=location)
    obj = bpy.context.object
    obj.name = name
    if view == "FRONT":
        obj.rotation_euler = (math.radians(90), 0, 0)
    elif view == "SIDE":
        obj.rotation_euler = (math.radians(90), 0, math.radians(90))
    elif view == "TOP":
        obj.rotation_euler = (0, 0, 0)
    elif view == "BACK":
        obj.rotation_euler = (math.radians(90), 0, math.radians(180))
    obj.data.materials.append(material)
    obj.show_transparent = True
    obj.display_type = "TEXTURED"
    obj["mcp:reference_view"] = view
    obj["mcp:reference_image"] = image_path
    return obj


def create_object(params: dict[str, Any]) -> dict[str, Any]:
    """Create a mesh primitive."""
    object_type = params.get("object_type") or params.get("type", "cube")
    location = _vec(params.get("location"), (0.0, 0.0, 0.0))
    rotation = _vec(params.get("rotation"), (0.0, 0.0, 0.0))
    scale = _vec(params.get("scale"), (1.0, 1.0, 1.0))
    operations = {
        "cube": bpy.ops.mesh.primitive_cube_add,
        "sphere": bpy.ops.mesh.primitive_uv_sphere_add,
        "uv_sphere": bpy.ops.mesh.primitive_uv_sphere_add,
        "icosphere": bpy.ops.mesh.primitive_ico_sphere_add,
        "cylinder": bpy.ops.mesh.primitive_cylinder_add,
        "cone": bpy.ops.mesh.primitive_cone_add,
        "torus": bpy.ops.mesh.primitive_torus_add,
        "plane": bpy.ops.mesh.primitive_plane_add,
    }
    if object_type == "monkey":
        op = getattr(bpy.ops.mesh, "primitive_monkey_add", None)
        if op is None:
            raise CommandError("UnsupportedPrimitive", "Monkey primitive requires Blender's add mesh extra objects operator.", 400)
    else:
        op = operations.get(object_type)
    if op is None:
        raise CommandError("UnsupportedPrimitive", f"Primitive '{object_type}' is not supported.", 400)
    if object_type == "torus":
        op(location=location, rotation=rotation)
        obj = bpy.context.object
        obj.scale = scale
    else:
        op(location=location, rotation=rotation, scale=scale)
        obj = bpy.context.object
    if params.get("name"):
        obj.name = params["name"]
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    return {**_object_summary(obj), "object_type": object_type}


def delete_object(params: dict[str, Any]) -> dict[str, Any]:
    """Delete objects by name(s) or selection."""
    if params.get("selected"):
        targets = list(bpy.context.selected_objects)
    else:
        names = params.get("names") or ([params["name"]] if params.get("name") else [])
        targets = [_object(name) for name in names]
    deleted_names = [obj.name for obj in targets]
    for obj in targets:
        bpy.data.objects.remove(obj, do_unlink=True)
    return {"deleted": deleted_names}


def duplicate_object(params: dict[str, Any]) -> dict[str, Any]:
    """Duplicate one object."""
    obj = _object(params["name"])
    copy = obj.copy()
    copy.data = obj.data.copy()
    copy.location = obj.location + Vector(_vec(params.get("offset"), (0.0, 0.0, 0.0)))
    copy.name = params.get("new_name") or f"{obj.name}_Copy"
    bpy.context.collection.objects.link(copy)
    return _object_summary(copy)


def move_object(params: dict[str, Any]) -> dict[str, Any]:
    """Move an object."""
    obj = _object(params["name"])
    location = params.get("location")
    offset = params.get("offset")
    relative = params.get("relative", False)

    if location is None and offset is None:
        raise CommandError("InvalidParams", "move_object requires either 'location' or 'offset'.", 400)

    if offset is not None:
        target = Vector(_vec(offset, (0.0, 0.0, 0.0)))
        obj.location = obj.location + target
    elif relative:
        target = Vector(_vec(location, (0.0, 0.0, 0.0)))
        obj.location = obj.location + target
    else:
        global_loc = Vector(_vec(location, (0.0, 0.0, 0.0)))
        if obj.parent:
            obj.location = obj.matrix_parent_inverse.inverted() @ obj.parent.matrix_world.inverted() @ global_loc
        else:
            obj.location = global_loc

    return _object_summary(obj)


def rotate_object(params: dict[str, Any]) -> dict[str, Any]:
    """Rotate an object."""
    obj = _object(params["name"])
    rotation = _vec(params.get("rotation"), (0.0, 0.0, 0.0))
    if params.get("relative"):
        obj.rotation_euler.rotate_axis("X", rotation[0])
        obj.rotation_euler.rotate_axis("Y", rotation[1])
        obj.rotation_euler.rotate_axis("Z", rotation[2])
    else:
        obj.rotation_euler = rotation
    return _object_summary(obj)


def scale_object(params: dict[str, Any]) -> dict[str, Any]:
    """Scale an object."""
    obj = _object(params["name"])
    scale = Vector(_vec(params.get("scale"), (1.0, 1.0, 1.0)))
    obj.scale = Vector(obj.scale) * scale if params.get("relative") else scale
    return _object_summary(obj)


def rename_object(params: dict[str, Any]) -> dict[str, Any]:
    """Rename an object."""
    obj = _object(params["name"])
    old_name = obj.name
    obj.name = params["new_name"]
    return {"old_name": old_name, "name": obj.name}


def list_objects(params: dict[str, Any]) -> list[dict[str, Any]]:
    """List objects in the active file."""
    return [_object_summary(obj) for obj in bpy.data.objects]


def get_object_info(params: dict[str, Any]) -> dict[str, Any]:
    """Return detailed object metadata."""
    obj = _object(params["name"])
    mesh = obj.data if obj.type == "MESH" else None
    return {
        **_object_summary(obj),
        "dimensions": list(obj.dimensions),
        "vertices": len(mesh.vertices) if mesh else 0,
        "faces": len(mesh.polygons) if mesh else 0,
        "modifiers": [modifier.name for modifier in obj.modifiers],
        "materials": [slot.material.name for slot in obj.material_slots if slot.material],
    }


def select_object(params: dict[str, Any]) -> dict[str, Any]:
    """Select or deselect one object."""
    obj = _object(params["name"])
    obj.select_set(bool(params.get("selected", True)))
    if params.get("active"):
        bpy.context.view_layer.objects.active = obj
    return _object_summary(obj)


def join_objects(params: dict[str, Any]) -> dict[str, Any]:
    """Join named mesh objects."""
    bpy.ops.object.select_all(action="DESELECT")
    objects = [_object(name) for name in params["names"]]
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    joined = bpy.context.object
    if params.get("new_name"):
        joined.name = params["new_name"]
    return _object_summary(joined)


def separate_object(params: dict[str, Any]) -> dict[str, Any]:
    """Separate mesh geometry."""
    obj = _object(params["name"])
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    method = {"loose_parts": "LOOSE", "material": "MATERIAL", "selection": "SELECTED"}.get(params["method"], params["method"])
    bpy.ops.mesh.separate(type=method)
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"objects": [obj.name for obj in bpy.context.selected_objects]}


def set_object_visibility(params: dict[str, Any]) -> dict[str, Any]:
    """Set object visibility flags."""
    obj = _object(params["name"])
    if params.get("viewport") is not None:
        obj.hide_viewport = not bool(params["viewport"])
    if params.get("render") is not None:
        obj.hide_render = not bool(params["render"])
    return _object_summary(obj)


def parent_object(params: dict[str, Any]) -> dict[str, Any]:
    """Parent an object."""
    child = _object(params["child"])
    parent = _object(params["parent"]) if params.get("parent") else None
    matrix_world = child.matrix_world.copy()
    child.parent = parent
    if params.get("keep_transform", True):
        child.matrix_world = matrix_world
    return {"child": child.name, "parent": parent.name if parent else None}


def apply_transform(params: dict[str, Any]) -> dict[str, Any]:
    """Apply object transform."""
    obj = _object(params["name"])
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(
        location=bool(params.get("location")),
        rotation=bool(params.get("rotation")),
        scale=bool(params.get("scale", True)),
    )
    return _object_summary(obj)


def enter_edit_mode(params: dict[str, Any]) -> dict[str, Any]:
    """Enter edit mode."""
    if params.get("name"):
        bpy.context.view_layer.objects.active = _object(params["name"])
    bpy.ops.object.mode_set(mode="EDIT")
    return {"mode": bpy.context.object.mode}


def exit_edit_mode(params: dict[str, Any]) -> dict[str, Any]:
    """Exit edit mode."""
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"mode": bpy.context.object.mode if bpy.context.object else "OBJECT"}


def _mesh_op(name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Run a named mesh operator in edit mode."""
    if params.get("name"):
        bpy.context.view_layer.objects.active = _object(params["name"])
    if bpy.context.object and bpy.context.object.mode != "EDIT":
        bpy.ops.object.mode_set(mode="EDIT")
    if name == "select_mesh_elements":
        action = {"all": "SELECT", "none": "DESELECT", "invert": "INVERT"}.get(params.get("mode", "indices"))
        if action:
            bpy.ops.mesh.select_all(action=action)
        return {"selected": params.get("indices", [])}
    if name == "extrude":
        bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": _vec(params.get("axis"), (0, 0, params.get("distance", 1)))})
    elif name == "loop_cut":
        bpy.ops.mesh.loopcut_slide(number_cuts=params.get("cuts", 1), edge_index=params["edge_index"], TRANSFORM_OT_edge_slide={"value": params.get("slide", 0.0)})
    elif name == "bevel":
        bpy.ops.mesh.bevel(offset=params["width"], segments=params.get("segments", 1), affect=params.get("affect", "edges").upper())
    elif name == "subdivide":
        bpy.ops.mesh.subdivide(number_cuts=params.get("cuts", 1))
    elif name == "merge_vertices":
        if params.get("method") in {"by_distance", "BY_DISTANCE"}:
            bpy.ops.mesh.remove_doubles(threshold=params.get("distance", 0.0001))
        else:
            bpy.ops.mesh.merge(type="CENTER")
    elif name == "inset_faces":
        bpy.ops.mesh.inset(thickness=params["thickness"], depth=params.get("depth", 0.0))
    elif name == "bridge_edge_loops":
        bpy.ops.mesh.bridge_edge_loops()
    elif name == "flip_normals":
        bpy.ops.mesh.flip_normals()
    elif name == "recalculate_normals":
        bpy.ops.mesh.normals_make_consistent(inside=not params.get("outside", True))
    elif name == "knife_cut":
        return {"queued": True, "message": "Knife cuts are validated by MCP; interactive cut execution requires viewport context."}
    elif name == "set_vertex_position":
        obj = _object(params["name"])
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.verts[params["index"]].co = Vector(params["position"])
        bmesh.update_edit_mesh(obj.data)
    return {"mode": "EDIT", "operation": name}


def create_material(params: dict[str, Any]) -> dict[str, Any]:
    """Create a Principled BSDF material."""
    name = params.get("material_name") or params.get("name")
    if not name:
        raise CommandError("InvalidParameters", "Material name is required.")
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = _color(params.get("base_color") or params.get("color") or "#ffffff")
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        for socket, value in {
            "Base Color": material.diffuse_color,
            "Metallic": params.get("metallic", 0.0),
            "Roughness": params.get("roughness", 0.5),
            "Specular IOR Level": params.get("specular", 0.5),
            "Specular": params.get("specular", 0.5),
        }.items():
            if socket in bsdf.inputs:
                bsdf.inputs[socket].default_value = value
    return {"name": material.name, "base_color": list(material.diffuse_color)}


def assign_material(params: dict[str, Any]) -> dict[str, Any]:
    """Assign material to object."""
    obj = _object(params["object_name"])
    material = _material(params["material_name"])
    if material.name not in [slot.material.name for slot in obj.material_slots if slot.material]:
        obj.data.materials.append(material)
    return {"object_name": obj.name, "material_name": material.name}


def list_materials(params: dict[str, Any]) -> list[dict[str, Any]]:
    """List materials."""
    return [{"name": mat.name, "use_nodes": mat.use_nodes, "diffuse_color": list(mat.diffuse_color)} for mat in bpy.data.materials]


def delete_material(params: dict[str, Any]) -> dict[str, Any]:
    """Delete a material."""
    name = params.get("material_name") or params.get("name")
    if not name:
        raise CommandError("InvalidParameters", "Material name is required.")
    material = _material(name)
    bpy.data.materials.remove(material)
    return {"deleted": name}


def set_material_color(params: dict[str, Any]) -> dict[str, Any]:
    """Set material base color."""
    name = params.get("material_name") or params.get("name")
    if not name:
        raise CommandError("InvalidParameters", "Material name is required.")
    material = _material(name)
    color = params.get("base_color") or params.get("color")
    if not color:
        raise CommandError("InvalidParameters", "Color value is required.")

    duplicate_if_shared = bool(params.get("duplicate_if_shared", False))
    object_name = params.get("object_name")

    users = material.users
    warning = None

    if users > 1:
        if duplicate_if_shared and object_name:
            obj = _object(object_name)
            new_mat = material.copy()
            new_mat.name = f"{material.name}_Unique"
            replaced = False
            for slot in obj.material_slots:
                if slot.material == material:
                    slot.material = new_mat
                    replaced = True
            if not replaced:
                obj.data.materials.append(new_mat)
            material = new_mat
        else:
            warning = f"This material is shared by {users} objects; the color change affects all of them."

    material.diffuse_color = _color(color)
    if material.use_nodes:
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf and "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = material.diffuse_color

    result_data = {"name": material.name, "base_color": list(material.diffuse_color)}
    if warning:
        result_data["warning"] = warning
    return result_data


def set_material_property(params: dict[str, Any]) -> dict[str, Any]:
    """Set a Principled BSDF input by name."""
    material = _material(params["name"])
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if not bsdf or params["property"] not in bsdf.inputs:
        raise CommandError("PropertyNotFound", f"Material property '{params['property']}' does not exist.", 404)
    bsdf.inputs[params["property"]].default_value = params["value"]
    return {"name": material.name, "property": params["property"], "value": params["value"]}


def create_emission_material(params: dict[str, Any]) -> dict[str, Any]:
    """Create emission material."""
    material = bpy.data.materials.new(params["name"])
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = _color(params["color"])
    emission.inputs["Strength"].default_value = params.get("strength", 1.0)
    output = nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return {"name": material.name}


def create_glass_material(params: dict[str, Any]) -> dict[str, Any]:
    """Create glass material."""
    result = create_material({"name": params["name"], "base_color": params.get("color", "#ffffff"), "roughness": params.get("roughness", 0.0), "metallic": 0.0})
    material = _material(params["name"])
    material.use_screen_refraction = True
    return result


def add_texture(params: dict[str, Any]) -> dict[str, Any]:
    """Add image texture node to a material."""
    material = _material(params["material_name"])
    material.use_nodes = True
    image = bpy.data.images.load(params["image_path"])
    tex = material.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = image
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf and params.get("socket", "Base Color") in bsdf.inputs:
        material.node_tree.links.new(tex.outputs["Color"], bsdf.inputs[params.get("socket", "Base Color")])
    return {"material_name": material.name, "image": image.name}


def setup_pbr_material(params: dict[str, Any]) -> dict[str, Any]:
    """Create a PBR material and attach texture maps."""
    create_material({"name": params["name"], "base_color": "#ffffff"})
    for key in ("diffuse_map", "normal_map", "roughness_map", "metallic_map"):
        if params.get(key):
            add_texture({"material_name": params["name"], "image_path": params[key], "socket": "Base Color"})
    return get_material_info({"name": params["name"]})


def enable_nodes(params: dict[str, Any]) -> dict[str, Any]:
    """Enable material nodes."""
    name = params.get("material_name") or params.get("name")
    if not name:
        raise CommandError("InvalidParameters", "Material name is required.")
    material = _material(name)
    material.use_nodes = bool(params.get("enable") if params.get("enable") is not None else params.get("enabled", True))
    return {"name": material.name, "use_nodes": material.use_nodes}


def get_material_info(params: dict[str, Any]) -> dict[str, Any]:
    """Inspect material node tree."""
    name = params.get("material_name") or params.get("name")
    if not name:
        raise CommandError("InvalidParameters", "Material name is required.")
    material = _material(name)
    return {
        "name": material.name,
        "use_nodes": material.use_nodes,
        "nodes": [node.name for node in material.node_tree.nodes] if material.use_nodes else [],
    }


def passthrough_scene(tool: str, params: dict[str, Any]) -> Any:
    """Handle scene, camera, light, modifier, animation, render, UV, geometry, and IO tools."""
    scene = bpy.context.scene
    if tool == "get_scene_info":
        info = {
            "name": scene.name,
            "frame": scene.frame_current,
            "frame_start": scene.frame_start,
            "frame_end": scene.frame_end,
            "render_engine": scene.render.engine,
            "active_camera": scene.camera.name if scene.camera else None
        }
        if params.get("include_collections", True):
            info["collections"] = [{"name": col.name, "objects": len(col.objects)} for col in bpy.data.collections]
        if params.get("include_render_settings", True):
            info["render_settings"] = {
                "resolution_x": scene.render.resolution_x,
                "resolution_y": scene.render.resolution_y,
                "resolution_percentage": scene.render.resolution_percentage,
                "filepath": scene.render.filepath,
                "file_format": scene.render.image_settings.file_format,
                "engine": scene.render.engine
            }
        return info
    if tool == "set_scene_property":
        path = params.get("property_path") or params.get("property")
        if not path:
            raise CommandError("InvalidParameters", "Property path is required.")
        parts = path.split('.')
        target = scene
        for part in parts[:-1]:
            target = getattr(target, part)
        setattr(target, parts[-1], params["value"])
        return {"property": path, "value": getattr(target, parts[-1])}
    if tool == "set_unit_system":
        scene.unit_settings.system = params["system"].upper()
        scene.unit_settings.scale_length = params.get("scale", 1.0)
        if params.get("length_unit"):
            scene.unit_settings.length_unit = params["length_unit"].upper()
        return {
            "system": scene.unit_settings.system,
            "scale": scene.unit_settings.scale_length,
            "length_unit": getattr(scene.unit_settings, "length_unit", None)
        }
    if tool == "set_frame":
        if params.get("current") is not None:
            scene.frame_set(params["current"])
        if params.get("start") is not None:
            scene.frame_start = params["start"]
        if params.get("end") is not None:
            scene.frame_end = params["end"]
        return {"current": scene.frame_current, "start": scene.frame_start, "end": scene.frame_end}
    if tool == "set_frame_range":
        scene.frame_start = params["start"]
        scene.frame_end = params["end"]
        if params.get("preview_start") is not None:
            scene.frame_preview_start = params["preview_start"]
        if params.get("preview_end") is not None:
            scene.frame_preview_end = params["preview_end"]
        return {
            "start": scene.frame_start,
            "end": scene.frame_end,
            "preview_start": getattr(scene, "frame_preview_start", None),
            "preview_end": getattr(scene, "frame_preview_end", None)
        }
    if tool == "clear_scene":
        keep = set(params.get("keep_types", []))
        for obj in list(bpy.data.objects):
            if obj.type not in keep:
                bpy.data.objects.remove(obj, do_unlink=True)
        if params.get("include_collections", False):
            for col in list(bpy.data.collections):
                if not col.objects:
                    bpy.data.collections.remove(col)
        return {"objects": len(bpy.data.objects), "collections": len(bpy.data.collections)}
    if tool == "list_collections":
        result = []
        include_objs = params.get("include_objects", True)
        for col in bpy.data.collections:
            cinfo = {"name": col.name}
            if include_objs:
                cinfo["objects"] = [obj.name for obj in col.objects]
            result.append(cinfo)
        return result
    if tool == "create_collection":
        collection = bpy.data.collections.new(params["name"])
        parent_name = params.get("parent")
        if parent_name:
            parent_col = bpy.data.collections.get(parent_name)
            if parent_col:
                parent_col.children.link(collection)
            else:
                raise CommandError("ParentCollectionNotFound", f"Parent collection '{parent_name}' does not exist.")
        else:
            scene.collection.children.link(collection)
        return {"name": collection.name, "parent": parent_name}
    if tool == "move_to_collection":
        collection = bpy.data.collections.get(params["collection_name"])
        if not collection and params.get("create_if_missing", True):
            collection = bpy.data.collections.new(params["collection_name"])
            scene.collection.children.link(collection)
        if not collection:
            raise CommandError("CollectionNotFound", f"Collection '{params['collection_name']}' does not exist.")
        for name in params["object_names"]:
            obj = _object(name)
            if obj.name not in collection.objects:
                collection.objects.link(obj)
            if params.get("unlink_from_others", True):
                for c in list(obj.users_collection):
                    if c != collection:
                        c.objects.unlink(obj)
        return {"collection_name": collection.name, "object_names": params["object_names"]}
    if tool == "set_world_color":
        scene.world = scene.world or bpy.data.worlds.new("World")
        scene.world.use_nodes = True
        nodes = scene.world.node_tree.nodes
        links = scene.world.node_tree.links
        
        if params.get("hdri_path"):
            nodes.clear()
            output = nodes.new("ShaderNodeOutputWorld")
            bg = nodes.new("ShaderNodeBackground")
            bg.inputs["Strength"].default_value = params.get("strength", 1.0)
            
            env = nodes.new("ShaderNodeTexEnvironment")
            try:
                env.image = bpy.data.images.load(params["hdri_path"])
            except Exception as e:
                raise CommandError("HDRILoadFailed", f"Failed to load HDRI file: {str(e)}")
                
            links.new(env.outputs["Color"], bg.inputs["Color"])
            links.new(bg.outputs["Background"], output.inputs["Surface"])
            return {"world": scene.world.name, "hdri_path": params["hdri_path"], "strength": params.get("strength", 1.0)}
        else:
            nodes.clear()
            output = nodes.new("ShaderNodeOutputWorld")
            bg = nodes.new("ShaderNodeBackground")
            bg.inputs["Strength"].default_value = params.get("strength", 1.0)
            if params.get("color"):
                bg.inputs["Color"].default_value = _color(params["color"])
            links.new(bg.outputs["Background"], output.inputs["Surface"])
            return {"world": scene.world.name, "color": params.get("color"), "strength": params.get("strength", 1.0)}
    raise CommandError("UnsupportedTool", f"Tool '{tool}' needs a specialized handler.", 501)



def create_camera(params: dict[str, Any]) -> dict[str, Any]:
    bpy.ops.object.camera_add(location=_vec(params.get("location"), (0, -5, 3)), rotation=_vec(params.get("rotation"), (math.radians(60), 0, 0)))
    camera = bpy.context.object
    camera.name = params.get("name") or camera.name
    camera.data.type = params.get("type", "PERSP").upper()
    return _object_summary(camera)


def create_light(params: dict[str, Any]) -> dict[str, Any]:
    bpy.ops.object.light_add(type=params["type"].upper(), location=_vec(params.get("location"), (0, 0, 5)))
    light = bpy.context.object
    light.name = params.get("name") or light.name
    light.data.energy = params.get("energy", 500.0)
    if params.get("color"):
        light.data.color = _color(params["color"])[:3]
    return _object_summary(light)


def execute_python(params: dict[str, Any]) -> dict[str, Any]:
    """Execute whitelisted Python in Blender."""
    stdout = io.StringIO()
    globals_dict = {"bpy": bpy, "bmesh": bmesh, "math": math, "os": os, "json": json}
    try:
        with contextlib.redirect_stdout(stdout):
            exec(params["code"], globals_dict)
        return {"stdout": stdout.getvalue(), "result": None, "errors": None}
    except Exception as exc:  # noqa: BLE001
        return {"stdout": stdout.getvalue(), "result": None, "errors": str(exc), "traceback": traceback.format_exc(limit=8)}


def evaluate_expression(params: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a Python expression."""
    value = eval(params["expression"], {"bpy": bpy, "math": math, "json": json}, {})
    return {"result": repr(value)}


def _generic_object_tool(tool: str, params: dict[str, Any]) -> Any:
    if tool == "set_active_camera" or tool == "set_render_camera":
        scene = bpy.context.scene
        name = params.get("camera_name") or params.get("name")
        if not name:
            raise CommandError("InvalidParameters", "Camera name is required.")
        scene.camera = _object(name)
        return {"active_camera": scene.camera.name}
    if tool == "set_camera_property":
        camera = _object(params["name"])
        setattr(camera.data, params["property"], params["value"])
        return {"name": camera.name, "property": params["property"], "value": getattr(camera.data, params["property"])}
    if tool == "point_camera_at":
        camera = _object(params["name"])
        target = _object(params["target_object"]).location if params.get("target_object") else Vector(params["target_location"])
        direction = target - camera.location
        camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        return _object_summary(camera)
    if tool == "camera_from_view":
        camera = _object(params["name"])
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        rv3d = space.region_3d
                        camera.location = rv3d.view_matrix.inverted().to_translation()
                        camera.rotation_euler = rv3d.view_matrix.inverted().to_euler()
                        return {"name": camera.name, "status": "matched_viewport"}
        raise CommandError("No3DView", "No 3D viewport found to copy view from.")
    if tool == "add_camera_constraint":
        camera = _object(params["name"])
        constraint_type = params["constraint_type"]
        target = _object(params["target_name"])
        constraint = camera.constraints.new(constraint_type)
        constraint.target = target
        constraint.influence = params.get("influence", 1.0)
        for k, v in params.get("options", {}).items():
            if hasattr(constraint, k):
                setattr(constraint, k, v)
        return {"name": camera.name, "constraint_name": constraint.name, "constraint_type": constraint.type}
    if tool == "list_lights":
        return [_object_summary(obj) for obj in bpy.data.objects if obj.type == "LIGHT"]
    if tool == "delete_light":
        return delete_object(params)
    if tool == "set_light_property":
        light = _object(params["name"])
        setattr(light.data, params["property"], params["value"])
        return {"name": light.name, "property": params["property"], "value": getattr(light.data, params["property"])}
    if tool == "add_modifier":
        obj = _object(params.get("object_name") or params["name"])
        mod_type = params.get("modifier_type") or params.get("type")
        if not mod_type:
            raise CommandError("InvalidParameters", "Modifier type is required.")
        modifier = obj.modifiers.new(params.get("name", mod_type), mod_type)
        for key, value in params.get("properties", {}).items():
            setattr(modifier, key, value)
        return {"object_name": obj.name, "modifier_name": modifier.name, "type": modifier.type}
    if tool in {"set_modifier_property", "apply_modifier", "remove_modifier", "reorder_modifier"}:
        obj = _object(params["object_name"])
        modifier = obj.modifiers.get(params["modifier_name"])
        if modifier is None:
            raise CommandError("ModifierNotFound", f"Modifier '{params['modifier_name']}' does not exist.", 404)
        bpy.context.view_layer.objects.active = obj
        if tool == "set_modifier_property":
            prop_name = params.get("property_name") or params.get("property")
            if not prop_name:
                raise CommandError("InvalidParameters", "Property name is required.")
            setattr(modifier, prop_name, params["value"])
        elif tool == "apply_modifier":
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        elif tool == "remove_modifier":
            obj.modifiers.remove(modifier)
        elif tool == "reorder_modifier":
            direction = params.get("direction", "UP").upper()
            idx = obj.modifiers.find(modifier.name)
            if direction == "UP":
                target_idx = max(0, idx - 1)
            elif direction == "DOWN":
                target_idx = min(len(obj.modifiers) - 1, idx + 1)
            elif direction == "TOP":
                target_idx = 0
            elif direction == "BOTTOM":
                target_idx = len(obj.modifiers) - 1
            elif direction == "INDEX":
                target_idx = params.get("index")
                if target_idx is None:
                    raise CommandError("InvalidParameters", "Index is required for direction INDEX.")
            else:
                raise CommandError("InvalidParameters", f"Unsupported direction '{direction}'")
            bpy.ops.object.modifier_move_to_index(modifier=modifier.name, index=target_idx)
            return {"object_name": obj.name, "modifier_name": modifier.name, "direction": direction, "index": target_idx}
        return {"object_name": obj.name, "modifier_name": params["modifier_name"]}
    if tool == "list_modifiers":
        name = params.get("object_name") or params.get("name")
        if not name:
            raise CommandError("InvalidParameters", "Object name is required.")
        obj = _object(name)
        return [{"name": modifier.name, "type": modifier.type} for modifier in obj.modifiers]
    if tool == "insert_keyframe":
        name = params.get("object_name") or params.get("name")
        obj = _object(name)
        if "value" in params and params["value"] is not None:
            val = params["value"]
            try:
                idx = params.get("index")
                if idx is not None and idx >= 0:
                    prop = obj.path_resolve(params["data_path"])
                    prop[idx] = val
                else:
                    parts = params["data_path"].rsplit(".", 1)
                    if len(parts) == 2:
                        parent = obj.path_resolve(parts[0])
                        setattr(parent, parts[1], val)
                    else:
                        setattr(obj, params["data_path"], val)
            except Exception:
                pass
        idx_arg = params.get("index")
        idx_val = idx_arg if idx_arg is not None else -1
        obj.keyframe_insert(data_path=params["data_path"], frame=params["frame"], index=idx_val)
        return {"name": obj.name, "frame": params["frame"]}
    if tool == "delete_keyframe":
        name = params.get("object_name") or params.get("name")
        obj = _object(name)
        kwargs = {"data_path": params["data_path"]}
        if params.get("frame") is not None:
            kwargs["frame"] = params["frame"]
        kwargs["index"] = params.get("index") if params.get("index") is not None else -1
        obj.keyframe_delete(**kwargs)
        return {"name": obj.name, "frame": params.get("frame")}
    if tool == "list_keyframes":
        name = params.get("object_name") or params.get("name")
        obj = _object(name)
        filter_dp = params.get("data_path")
        include_vals = bool(params.get("include_values", True))
        results = []
        for fc in _get_fcurves(obj):
            if filter_dp and fc.data_path != filter_dp:
                continue
            fcurve_data = {
                "data_path": fc.data_path,
                "array_index": fc.array_index,
            }
            if include_vals:
                fcurve_data["keyframes"] = [
                    {
                        "frame": kp.co.x,
                        "value": kp.co.y,
                        "interpolation": kp.interpolation,
                    }
                    for kp in fc.keyframe_points
                ]
            else:
                fcurve_data["frames"] = [kp.co.x for kp in fc.keyframe_points]
            results.append(fcurve_data)
        return results
    raise CommandError("UnsupportedTool", f"Tool '{tool}' needs a specialized handler.", 501)


def create_primitive(params: dict[str, Any]) -> dict[str, Any]:
    """Create a universal modeling primitive."""
    primitive_type = params["type"]
    name = params.get("name")
    location = _vec(params.get("location"), (0.0, 0.0, 0.0))
    rotation = _vec(params.get("rotation"), (0.0, 0.0, 0.0))
    size = _vec(params.get("size"), (1.0, 1.0, 1.0))
    radius = float(params.get("radius") or max(abs(size[0]), abs(size[1])) / 2)
    depth = float(params.get("depth") or abs(size[2]))
    segments = int(params.get("segments", 24))

    if primitive_type in {"cube", "box", "beveled_box", "panel", "slab"}:
        obj = _box_object(name or primitive_type.title(), size, location, rotation)
    elif primitive_type in {"cylinder", "column"}:
        bpy.ops.mesh.primitive_cylinder_add(vertices=segments, radius=radius, depth=depth, location=location, rotation=rotation)
        obj = bpy.context.object
    elif primitive_type == "cone":
        bpy.ops.mesh.primitive_cone_add(vertices=segments, radius1=radius, radius2=0.0, depth=depth, location=location, rotation=rotation)
        obj = bpy.context.object
    elif primitive_type in {"sphere", "uv_sphere"}:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=max(8, segments // 2), radius=radius, location=location, rotation=rotation)
        obj = bpy.context.object
        obj.scale = (size[0] / (radius * 2), size[1] / (radius * 2), size[2] / (radius * 2))
    elif primitive_type == "icosphere":
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=radius, location=location, rotation=rotation)
        obj = bpy.context.object
    elif primitive_type == "torus":
        bpy.ops.mesh.primitive_torus_add(major_radius=radius, minor_radius=max(0.01, abs(size[2]) / 2), major_segments=segments, minor_segments=max(8, segments // 3), location=location)
        obj = bpy.context.object
        obj.rotation_euler = rotation
    elif primitive_type == "plane":
        obj = _plane_object(name or "Plane", size, location, rotation)
    elif primitive_type == "wedge":
        sx, sy, sz = size[0] / 2, size[1] / 2, size[2]
        verts = [(-sx, -sy, 0), (sx, -sy, 0), (-sx, sy, 0), (sx, sy, 0), (-sx, -sy, sz), (sx, -sy, sz)]
        faces = [(0, 1, 3, 2), (0, 4, 5, 1), (0, 2, 4), (1, 5, 3), (2, 3, 5, 4)]
        mesh = bpy.data.meshes.new(f"{name or 'Wedge'}Mesh")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name or "Wedge", mesh)
        bpy.context.collection.objects.link(obj)
        obj.location = location
        obj.rotation_euler = rotation
    elif primitive_type == "capsule":
        bpy.ops.mesh.primitive_cylinder_add(vertices=segments, radius=radius, depth=max(0.01, depth - 2 * radius), location=location, rotation=rotation)
        obj = bpy.context.object
        obj.name = name or "Capsule"
        bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=max(8, segments // 2), radius=radius, location=(location[0], location[1], location[2] + max(0.0, depth / 2 - radius)))
        top = bpy.context.object
        top.name = f"{obj.name}_Top"
        bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=max(8, segments // 2), radius=radius, location=(location[0], location[1], location[2] - max(0.0, depth / 2 - radius)))
        bottom = bpy.context.object
        bottom.name = f"{obj.name}_Bottom"
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
        bpy.context.view_layer.objects.active = top
        top.select_set(True)
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
        bpy.context.view_layer.objects.active = bottom
        bottom.select_set(True)
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
        return {"name": obj.name, "parts": [obj.name, top.name, bottom.name], "type": "capsule"}
    elif primitive_type == "pipe":
        bpy.ops.mesh.primitive_cylinder_add(vertices=segments, radius=radius, depth=depth, location=location, rotation=rotation)
        obj = bpy.context.object
        solidify = obj.modifiers.new("Pipe_Wall", "SOLIDIFY")
        solidify.thickness = max(0.01, radius * 0.18)
    elif primitive_type == "monkey":
        op = getattr(bpy.ops.mesh, "primitive_monkey_add", None)
        if op is None:
            raise CommandError("UnsupportedPrimitive", "Monkey primitive is not supported in this Blender version.", 400)
        op(location=location, rotation=rotation, scale=size)
        obj = bpy.context.object
    else:
        raise CommandError("UnsupportedPrimitive", f"Primitive '{primitive_type}' is not supported.", 400)

    if name:
        obj.name = name
    if params.get("bevel", 0) > 0:
        bevel = obj.modifiers.new("MCP_Primitive_Bevel", "BEVEL")
        bevel.width = params["bevel"]
        bevel.segments = 2
        obj.modifiers.new("MCP_Weighted_Normals", "WEIGHTED_NORMAL")
    if params.get("metadata"):
        _write_metadata(obj, params["metadata"])
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    return {**_object_summary(obj), "bounds": _bounds_for(obj), "primitive_type": primitive_type}


def create_curve_path(params: dict[str, Any]) -> dict[str, Any]:
    """Create a polyline curve path."""
    curve = bpy.data.curves.new(params["name"], "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = float(params.get("bevel_depth", 0.0))
    curve.use_path = True
    poly = curve.splines.new("POLY")
    points = params["points"]
    poly.points.add(len(points) - 1)
    for point, co in zip(poly.points, points, strict=False):
        point.co = (float(co[0]), float(co[1]), float(co[2]), 1.0)
    poly.use_cyclic_u = bool(params.get("cyclic", False))
    obj = bpy.data.objects.new(params["name"], curve)
    bpy.context.collection.objects.link(obj)
    if params.get("metadata"):
        _write_metadata(obj, params["metadata"])
    return {**_object_summary(obj), "points": len(points), "bevel_depth": curve.bevel_depth}


def create_pipe_along_path(params: dict[str, Any]) -> dict[str, Any]:
    """Create a pipe by using a beveled 3D curve."""
    result = create_curve_path({**params, "bevel_depth": params["radius"]})
    obj = _object(result["name"])
    obj.data.fill_mode = "FULL"
    obj.data.use_fill_caps = bool(params.get("fill_caps", True))
    if params.get("material_name"):
        obj.data.materials.append(_material(params["material_name"]))
    return {**result, "radius": params["radius"], "fill_caps": obj.data.use_fill_caps}


def boolean_operation(params: dict[str, Any]) -> dict[str, Any]:
    """Run a Boolean modifier between target and cutter."""
    target = _object(params["target"])
    cutter = _object(params["cutter"])
    modifier = target.modifiers.new(params.get("modifier_name", "MCP_Boolean"), "BOOLEAN")
    modifier.operation = params.get("operation", "DIFFERENCE")
    modifier.solver = params.get("solver", "EXACT")
    modifier.object = cutter
    bpy.context.view_layer.objects.active = target
    if params.get("apply", True):
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        if not params.get("keep_cutter", False):
            bpy.data.objects.remove(cutter, do_unlink=True)
    return {"target": target.name, "cutter": params["cutter"], "operation": modifier.operation, "applied": params.get("apply", True)}


def bevel_edges(params: dict[str, Any]) -> dict[str, Any]:
    """Add or apply a bevel modifier."""
    obj = _object(params["object_name"])
    modifier = obj.modifiers.new(params.get("modifier_name", "MCP_Bevel"), "BEVEL")
    modifier.width = params["width"]
    modifier.segments = params.get("segments", 2)
    modifier.affect = params.get("affect", "EDGES")
    if params.get("angle_limit") is not None:
        modifier.limit_method = "ANGLE"
        modifier.angle_limit = params["angle_limit"]
    obj.modifiers.new(f"{modifier.name}_Weighted_Normals", "WEIGHTED_NORMAL")
    if params.get("apply", False):
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    return {"object_name": obj.name, "modifier_name": modifier.name, "applied": params.get("apply", False)}


def set_origin(params: dict[str, Any]) -> dict[str, Any]:
    """Set object origin/pivot."""
    obj = _object(params["object_name"])
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    mode = params.get("mode", "GEOMETRY")
    if mode == "WORLD_ORIGIN":
        bpy.context.scene.cursor.location = (0, 0, 0)
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    elif mode == "CURSOR":
        if params.get("location"):
            bpy.context.scene.cursor.location = params["location"]
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    elif mode == "CENTER_OF_MASS":
        bpy.ops.object.origin_set(type="ORIGIN_CENTER_OF_MASS")
    else:
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    return {**_object_summary(obj), "origin": list(obj.location)}


def get_bounding_box(params: dict[str, Any]) -> dict[str, Any]:
    """Return bounds for one or more objects."""
    bounds = [_bounds_for(_object(name)) for name in params["objects"]]
    min_v = Vector((min(item["min"][0] for item in bounds), min(item["min"][1] for item in bounds), min(item["min"][2] for item in bounds)))
    max_v = Vector((max(item["max"][0] for item in bounds), max(item["max"][1] for item in bounds), max(item["max"][2] for item in bounds)))
    return {"objects": bounds, "combined": {"min": list(min_v), "max": list(max_v), "center": list((min_v + max_v) / 2), "dimensions": list(max_v - min_v)}}


def snap_to_ground(params: dict[str, Any]) -> dict[str, Any]:
    """Move objects down/up to a ground height."""
    moved = []
    ground_z = float(params.get("ground_z", 0.0))
    for name in params["objects"]:
        obj = _object(name)
        delta = ground_z - (obj.location.z if params.get("use_origin") else _bounds_for(obj)["min"][2])
        obj.location.z += delta
        moved.append({"name": obj.name, "delta_z": delta, "location": list(obj.location)})
    return {"moved": moved}


def align_objects(params: dict[str, Any]) -> dict[str, Any]:
    """Align objects by origin or bound component."""
    axis_index = {"X": 0, "Y": 1, "Z": 2}[params.get("axis", "Z")]
    mode = params.get("mode", "MIN")
    objects = [_object(name) for name in params["objects"]]
    if params.get("target") is not None:
        target = float(params["target"])
    else:
        first_bounds = _bounds_for(objects[0])
        target = objects[0].location[axis_index] if mode == "ORIGIN" else first_bounds[mode.lower()][axis_index]
    changed = []
    for obj in objects:
        bounds = _bounds_for(obj)
        current = obj.location[axis_index] if mode == "ORIGIN" else bounds[mode.lower()][axis_index]
        obj.location[axis_index] += target - current
        changed.append({"name": obj.name, "location": list(obj.location)})
    return {"axis": params.get("axis", "Z"), "mode": mode, "target": target, "objects": changed}


def distribute_objects(params: dict[str, Any]) -> dict[str, Any]:
    """Distribute objects evenly on an axis with edge-to-edge spacing.

    When *spacing* is provided the gap between each adjacent pair's bounding-box
    edges equals *spacing* (not origin-to-origin distance), so objects of
    different sizes never overlap.  When *start*/*end* are used instead, origins
    are distributed evenly between those two world-space positions (original
    centre-to-centre behaviour preserved for the range case).
    """
    axis_index = {"X": 0, "Y": 1, "Z": 2}[params.get("axis", "X")]
    objects = [_object(name) for name in params["objects"]]
    changed = []

    if params.get("spacing") is not None:
        gap = float(params["spacing"])
        # Compute bounding-box extents for every object once (world space).
        bounds_list = [_bounds_for(obj) for obj in objects]
        half_extents = [b["dimensions"][axis_index] / 2.0 for b in bounds_list]

        # The *start* param is the desired world-space minimum edge of the
        # first object.  Default: keep the first object where it is.
        if params.get("start") is not None:
            cursor = float(params["start"]) + half_extents[0]
        else:
            # Place first object's bbox-min at its current bbox-min position.
            cursor = bounds_list[0]["min"][axis_index] + half_extents[0]

        positions = []
        for i, obj in enumerate(objects):
            obj.location[axis_index] += cursor - bounds_list[i]["center"][axis_index]
            positions.append(obj.location[axis_index])
            changed.append({"name": obj.name, "location": list(obj.location)})
            # Advance cursor to the right edge of this object plus the gap.
            cursor += half_extents[i] + gap + half_extents[i + 1] if i + 1 < len(objects) else 0.0
    else:
        start, end = float(params["start"]), float(params["end"])
        step = (end - start) / max(1, len(objects) - 1)
        positions = [start + index * step for index in range(len(objects))]
        for obj, position in zip(objects, positions, strict=False):
            obj.location[axis_index] = position
            changed.append({"name": obj.name, "location": list(obj.location)})

    return {"axis": params.get("axis", "X"), "positions": positions, "objects": changed}


def duplicate_along_axis(params: dict[str, Any]) -> dict[str, Any]:
    """Duplicate an object along a vector offset."""
    source = _object(params["object_name"])
    offset = Vector(_vec(params.get("offset"), (1.0, 0.0, 0.0)))
    created = []
    for index in range(1, int(params["count"]) + 1):
        copy = source.copy()
        copy.data = source.data if params.get("linked", False) else source.data.copy()
        copy.location = source.location + offset * index
        copy.name = f"{params.get('name_prefix') or source.name}_{index:03d}"
        bpy.context.collection.objects.link(copy)
        created.append(copy.name)
    return {"source": source.name, "created": created}


def create_component_group(params: dict[str, Any]) -> dict[str, Any]:
    """Create an empty parent and optionally attach children."""
    empty = bpy.data.objects.new(params["name"], None)
    empty.empty_display_type = "CUBE"
    bpy.context.collection.objects.link(empty)
    if params.get("collection"):
        _link_to_collection(empty, params["collection"])
    for child_name in params.get("children", []):
        child = _object(child_name)
        matrix = child.matrix_world.copy()
        child.parent = empty
        child.matrix_world = matrix
    if params.get("metadata"):
        _write_metadata(empty, params["metadata"])
    return {"name": empty.name, "children": params.get("children", []), "metadata": _read_metadata(empty)}


def set_object_metadata(params: dict[str, Any]) -> dict[str, Any]:
    """Attach metadata to objects."""
    namespace = params.get("namespace", "mcp")
    updated = []
    for name in params["objects"]:
        obj = _object(name)
        metadata = _write_metadata(obj, params["metadata"], namespace, params.get("merge", True))
        updated.append({"name": obj.name, "metadata": metadata})
    return {"namespace": namespace, "objects": updated}


def find_objects(params: dict[str, Any]) -> dict[str, Any]:
    """Find objects by multiple filters."""
    found = []
    bounds_filter = params.get("within_bounds")
    min_bound = Vector(bounds_filter[0]) if bounds_filter else None
    max_bound = Vector(bounds_filter[1]) if bounds_filter else None
    for obj in bpy.data.objects:
        if params.get("name_contains") and params["name_contains"].lower() not in obj.name.lower():
            continue
        if params.get("object_type") and obj.type != params["object_type"]:
            continue
        if params.get("material_name"):
            materials = [slot.material.name for slot in obj.material_slots if slot.material]
            if params["material_name"] not in materials:
                continue
        if params.get("metadata"):
            metadata = _read_metadata(obj)
            if any(metadata.get(key) != value for key, value in params["metadata"].items()):
                continue
        if min_bound and max_bound:
            center = Vector(_bounds_for(obj)["center"])
            if any(center[index] < min_bound[index] or center[index] > max_bound[index] for index in range(3)):
                continue
        found.append({**_object_summary(obj), "metadata": _read_metadata(obj)})
        if len(found) >= params.get("limit", 100):
            break
    return {"objects": found, "count": len(found)}


def validate_model(params: dict[str, Any]) -> dict[str, Any]:
    """Run basic quality checks for arbitrary models."""
    names = params.get("objects") or [obj.name for obj in bpy.data.objects if obj.type == "MESH"]
    objects = [_object(name) for name in names]
    tolerance = float(params.get("tolerance", 0.001))
    issues = []
    bounds = {obj.name: _bounds_for(obj) for obj in objects}
    if params.get("check_floating", True):
        ground_z = float(params.get("ground_z", 0.0))
        for obj in objects:
            min_z = bounds[obj.name]["min"][2]
            if min_z > ground_z + tolerance:
                issues.append({"type": "FloatingObject", "object": obj.name, "min_z": min_z, "ground_z": ground_z})
    if params.get("check_missing_materials", True):
        for obj in objects:
            if obj.type == "MESH" and not obj.material_slots:
                issues.append({"type": "MissingMaterial", "object": obj.name})
    if params.get("check_overlaps", True):
        for index, obj_a in enumerate(objects):
            a = bounds[obj_a.name]
            for obj_b in objects[index + 1 :]:
                b = bounds[obj_b.name]
                overlap = all(a["min"][axis] < b["max"][axis] - tolerance and a["max"][axis] > b["min"][axis] + tolerance for axis in range(3))
                if overlap:
                    issues.append({"type": "BoundsOverlap", "objects": [obj_a.name, obj_b.name]})
                    if len(issues) > 200:
                        return {"valid": False, "issues": issues, "checked": len(objects), "truncated": True}
    return {"valid": not issues, "issues": issues, "checked": len(objects)}


def create_lowpoly_asset(params: dict[str, Any]) -> dict[str, Any]:
    """Create a complete lowpoly asset from a production-oriented preset."""
    asset_type = params.get("asset_type", "cargo_ship")
    if asset_type not in {"cargo_ship", "industrial_cargo_ship"}:
        raise CommandError("UnsupportedAssetType", f"Asset type '{asset_type}' is not supported yet.", 400)
    return _create_lowpoly_cargo_ship(params)


def _create_lowpoly_cargo_ship(params: dict[str, Any]) -> dict[str, Any]:
    asset_name = params.get("name", "CargoShip")
    collection_name = params.get("collection", asset_name)
    replace_existing = bool(params.get("replace_existing", True))
    scale = float(params.get("scale", 1.0))
    container_rows = int(params.get("container_rows", 2))
    container_tiers = int(params.get("container_tiers", 2))
    include_crane = bool(params.get("include_crane", True))
    include_metadata = bool(params.get("include_metadata", True))

    collection = _ensure_collection(collection_name)
    if replace_existing:
        for obj in list(collection.objects):
            if obj.name == asset_name or obj.name.startswith(f"{asset_name}_"):
                bpy.data.objects.remove(obj, do_unlink=True)

    materials = {
        "hull": _material_named(f"{asset_name}_Mat_Hull", "#555c66", metallic=0.08, roughness=0.82),
        "deck": _material_named(f"{asset_name}_Mat_Deck", "#8f9499", metallic=0.03, roughness=0.72),
        "bridge": _material_named(f"{asset_name}_Mat_Bridge", "#d7dbd2", metallic=0.02, roughness=0.60),
        "funnel": _material_named(f"{asset_name}_Mat_Funnel", "#2e333a", metallic=0.10, roughness=0.75),
        "accent": _material_named(f"{asset_name}_Mat_Accent", "#ef8c29", roughness=0.60),
        "red": _material_named(f"{asset_name}_Mat_Container_Red", "#b83333", roughness=0.78),
        "blue": _material_named(f"{asset_name}_Mat_Container_Blue", "#3366bf", roughness=0.78),
        "green": _material_named(f"{asset_name}_Mat_Container_Green", "#389955", roughness=0.78),
        "yellow": _material_named(f"{asset_name}_Mat_Container_Yellow", "#d1ad33", roughness=0.78),
        "gray": _material_named(f"{asset_name}_Mat_Container_Gray", "#9499a3", roughness=0.80),
    }

    parent = bpy.data.objects.new(asset_name, None)
    parent.empty_display_type = "CUBE"
    parent.empty_display_size = max(1.0, scale)
    _link_object(parent, collection_name)

    def asset_box(role: str, size: tuple[float, float, float], location: tuple[float, float, float], material_key: str) -> bpy.types.Object:
        obj = _box_object(
            f"{asset_name}_{role}",
            tuple(component * scale for component in size),
            tuple(component * scale for component in location),
            material=materials[material_key],
            collection_name=collection_name,
        )
        obj.parent = parent
        return obj

    created: list[bpy.types.Object] = []
    hull = _lowpoly_hull_object(asset_name, scale, materials["hull"], collection_name)
    hull.parent = parent
    created.append(hull)
    created.append(asset_box("Deck", (7.4, 2.1, 0.35), (-0.2, 0.0, 1.725), "deck"))
    bridge = _lowpoly_bridge_object(asset_name, scale, materials["bridge"], collection_name)
    bridge.parent = parent
    created.append(bridge)
    funnel = _lowpoly_cylinder_object(
        f"{asset_name}_Funnel",
        0.28 * scale,
        0.95 * scale,
        8,
        (-3.25 * scale, 0.0, 2.375 * scale),
        materials["funnel"],
        collection_name,
    )
    funnel.parent = parent
    created.append(funnel)

    if include_crane:
        created.append(asset_box("Mast", (0.12, 0.12, 1.2), (-3.0, -0.95, 2.5), "accent"))
        arm = asset_box("CraneArm", (1.8, 0.1, 0.1), (-2.25, -0.95, 3.15), "accent")
        arm.rotation_euler.z = 0.5
        created.append(arm)

    material_cycle = ["red", "blue", "green", "yellow", "gray"]
    index = 1
    x_positions = [0.8, -0.7, -2.2][: max(1, min(container_rows + 1, 3))]
    y_positions = [0.62, 0.0, -0.62]
    for tier in range(max(1, min(container_tiers, 3))):
        for x_pos in x_positions:
            for y_pos in y_positions[: max(1, min(container_rows + 1, 3))]:
                material_key = material_cycle[(index - 1) % len(material_cycle)]
                obj = asset_box(
                    f"Container_{index:02d}",
                    (1.25, 0.55, 0.55),
                    (x_pos, y_pos, 2.175 + tier * 0.55),
                    material_key,
                )
                created.append(obj)
                index += 1

    if include_metadata:
        _write_metadata(
            parent,
            {
                "asset_type": "cargo_ship",
                "style": "lowpoly",
                "pipeline_stage": "generated_blockout",
                "quality_target": params.get("quality_target", "clean"),
                "component_count": len(created),
            },
        )
        for obj in created:
            _write_metadata(
                obj,
                {
                    "asset": asset_name,
                    "style": "lowpoly",
                    "role": obj.name.removeprefix(f"{asset_name}_").lower(),
                    "generated_by": "create_lowpoly_asset",
                },
            )

    bpy.context.view_layer.update()
    report = validate_scene_quality(
        {
            "objects": [obj.name for obj in created],
            "checks": ["overlaps", "floating", "missing_materials", "bad_names", "unapplied_scale", "high_poly"],
            "tolerance": 0.025 * scale,
        }
    )
    return {
        "name": asset_name,
        "asset_type": "cargo_ship",
        "style": "lowpoly",
        "collection": collection.name,
        "objects": [obj.name for obj in created],
        "parent": parent.name,
        "quality": report,
        "pipeline": [
            "blockout",
            "component_layout",
            "material_assignment",
            "metadata_tagging",
            "quality_validation",
        ],
    }


def _lowpoly_hull_object(
    asset_name: str,
    scale: float,
    material: bpy.types.Material,
    collection_name: str,
) -> bpy.types.Object:
    verts = [
        (-4.8, -1.2, 0.2), (-4.8, 1.2, 0.2),
        (-3.4, -1.45, -0.05), (-3.4, 1.45, -0.05),
        (-0.8, -1.55, -0.10), (-0.8, 1.55, -0.10),
        (2.8, -1.45, -0.05), (2.8, 1.45, -0.05),
        (4.9, -0.95, 0.25), (4.9, 0.95, 0.25),
        (-4.2, -0.95, 1.45), (-4.2, 0.95, 1.45),
        (-2.2, -1.20, 1.20), (-2.2, 1.20, 1.20),
        (1.2, -1.15, 1.25), (1.2, 1.15, 1.25),
        (4.2, -0.80, 1.55), (4.2, 0.80, 1.55),
    ]
    faces = [
        (0, 2, 3, 1), (2, 4, 5, 3), (4, 6, 7, 5), (6, 8, 9, 7),
        (10, 11, 3, 2), (2, 0, 10), (1, 3, 11),
        (10, 12, 13, 11), (12, 14, 15, 13), (14, 16, 17, 15),
        (0, 1, 11, 10), (12, 2, 3, 13), (14, 4, 5, 15), (16, 6, 7, 17),
        (10, 11, 13, 12), (12, 13, 15, 14), (14, 15, 17, 16),
    ]
    mesh = bpy.data.meshes.new(f"{asset_name}_HullMesh")
    mesh.from_pydata([(x * scale, y * scale, z * scale) for x, y, z in verts], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(f"{asset_name}_Hull", mesh)
    obj.data.materials.append(material)
    _shade_flat(obj)
    return _link_object(obj, collection_name)


def _lowpoly_bridge_object(
    asset_name: str,
    scale: float,
    material: bpy.types.Material,
    collection_name: str,
) -> bpy.types.Object:
    verts = [
        (-0.9, -0.7, 0.0), (0.9, -0.7, 0.0), (1.0, 0.7, 0.0), (-1.0, 0.7, 0.0),
        (-0.9, -0.7, 1.1), (0.9, -0.7, 1.1), (1.0, 0.7, 1.1), (-1.0, 0.7, 1.1),
        (0.0, 0.0, 1.45),
    ]
    faces = [(0, 1, 2, 3), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 8), (5, 6, 8), (6, 7, 8), (7, 4, 8)]
    mesh = bpy.data.meshes.new(f"{asset_name}_BridgeMesh")
    mesh.from_pydata([(x * scale, y * scale, z * scale) for x, y, z in verts], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(f"{asset_name}_Bridge", mesh)
    obj.location = (3.15 * scale, 0.0, 1.9 * scale)
    obj.data.materials.append(material)
    _shade_flat(obj)
    return _link_object(obj, collection_name)


def import_reference_image(params: dict[str, Any]) -> dict[str, Any]:
    """Import an image reference plane."""
    name = params.get("name") or f"Reference_{params.get('view', 'FRONT')}"
    obj = _create_reference_plane_object(
        params["image_path"],
        name,
        params.get("view", "FRONT"),
        _vec(params.get("location"), (0.0, 0.0, 0.0)),
        float(params.get("scale", 1.0)),
        float(params.get("opacity", 0.45)),
    )
    if params.get("locked", True):
        obj.hide_select = True
        obj.lock_location = (True, True, True)
        obj.lock_rotation = (True, True, True)
        obj.lock_scale = (True, True, True)
    _link_to_collection(obj, "References")
    return {**_object_summary(obj), "image_path": params["image_path"], "view": params.get("view", "FRONT")}


def setup_reference_planes(params: dict[str, Any]) -> dict[str, Any]:
    """Create a reference collection with front, side, and top planes."""
    collection_name = params.get("collection", "References")
    created = []
    scale = float(params.get("scale", 5.0))
    opacity = float(params.get("opacity", 0.45))
    specs = [
        ("front", "FRONT", (0.0, 2.5, scale / 2)),
        ("side", "SIDE", (-2.5, 0.0, scale / 2)),
        ("top", "TOP", (0.0, 0.0, scale)),
    ]
    for key, view, location in specs:
        if not params.get(key):
            continue
        obj = _create_reference_plane_object(params[key], f"Reference_{view}", view, location, scale, opacity)
        obj.hide_select = True
        _link_to_collection(obj, collection_name)
        created.append(obj.name)
    return {"collection": collection_name, "references": created}


def lock_reference(params: dict[str, Any]) -> dict[str, Any]:
    """Lock or unlock reference objects."""
    updated = []
    for name in params["objects"]:
        obj = _object(name)
        locked = bool(params.get("locked", True))
        obj.lock_location = (locked, locked, locked)
        obj.lock_rotation = (locked, locked, locked)
        obj.lock_scale = (locked, locked, locked)
        obj.hide_select = bool(params.get("hide_select", True)) if locked else False
        updated.append({"name": obj.name, "locked": locked, "hide_select": obj.hide_select})
    return {"objects": updated}


def set_landmark(params: dict[str, Any]) -> dict[str, Any]:
    """Create or update a landmark empty."""
    object_name = _landmark_object_name(params["name"])
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        obj = bpy.data.objects.new(object_name, None)
        obj.empty_display_type = "SPHERE"
        obj.empty_display_size = 0.18
        bpy.context.collection.objects.link(obj)
    obj.location = params["location"]
    obj["mcp:is_landmark"] = True
    obj["mcp:landmark_category"] = params.get("category", "default")
    if params.get("target_object"):
        obj["mcp:target_object"] = params["target_object"]
    if params.get("metadata"):
        _write_metadata(obj, params["metadata"], "landmark")
    _link_to_collection(obj, "Landmarks")
    if not params.get("create_empty", True):
        obj.hide_viewport = True
    return _landmark_data(obj)


def get_landmarks(params: dict[str, Any]) -> dict[str, Any]:
    """Return landmark data."""
    requested = set(params.get("names") or [])
    result = []
    for obj in bpy.data.objects:
        if not obj.get("mcp:is_landmark"):
            continue
        data = _landmark_data(obj)
        if requested and data["name"] not in requested and obj.name not in requested:
            continue
        if params.get("category") and data["category"] != params["category"]:
            continue
        if params.get("target_object") and data.get("target_object") != params["target_object"]:
            continue
        result.append(data)
    return {"landmarks": result, "count": len(result)}


def measure_between_landmarks(params: dict[str, Any]) -> dict[str, Any]:
    """Measure distance between two landmarks."""
    a = _get_landmark(params["a"])
    b = _get_landmark(params["b"])
    vector = b.location - a.location
    return {"a": params["a"], "b": params["b"], "distance": vector.length, "vector": list(vector)}


def align_object_to_landmarks(params: dict[str, Any]) -> dict[str, Any]:
    """Move an object from one landmark position to another."""
    obj = _object(params["object_name"])
    source = _get_landmark(params["source_landmark"])
    target = _get_landmark(params["target_landmark"])
    delta = target.location - source.location
    obj.location += delta
    if params.get("scale_to_distance"):
        a = _get_landmark(params["scale_to_distance"][0])
        b = _get_landmark(params["scale_to_distance"][1])
        current = max(0.0001, max(_bounds_for(obj)["dimensions"]))
        factor = (b.location - a.location).length / current
        obj.scale *= factor
    return {**_object_summary(obj), "delta": list(delta)}


def calibrate_reference_scale(params: dict[str, Any]) -> dict[str, Any]:
    """Scale reference objects from landmark distance."""
    a = _get_landmark(params["landmark_a"])
    b = _get_landmark(params["landmark_b"])
    measured = (b.location - a.location).length
    factor = float(params["real_distance"]) / max(0.0001, measured)
    objects = [_object(name) for name in params.get("objects", [])] if params.get("objects") else [obj for obj in bpy.data.objects if obj.get("mcp:reference_image")]
    for obj in objects:
        obj.scale *= factor
    return {"measured_distance": measured, "scale_factor": factor, "objects": [obj.name for obj in objects]}


def render_orthographic_view(params: dict[str, Any]) -> dict[str, Any]:
    """Create or render an orthographic camera view."""
    view = params.get("view", "FRONT")
    camera = bpy.data.objects.get(params.get("camera_name", "Reference_Ortho_Camera"))
    if camera is None:
        bpy.ops.object.camera_add()
        camera = bpy.context.object
        camera.name = params.get("camera_name", "Reference_Ortho_Camera")
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = params.get("ortho_scale", 6.0)
    positions = {
        "FRONT": ((0, -10, 0), (math.radians(90), 0, 0)),
        "BACK": ((0, 10, 0), (math.radians(90), 0, math.radians(180))),
        "SIDE": ((10, 0, 0), (math.radians(90), 0, math.radians(90))),
        "TOP": ((0, 0, 10), (0, 0, 0)),
    }
    camera.location, camera.rotation_euler = positions[view]
    bpy.context.scene.camera = camera
    width, height = params.get("resolution", (1024, 1024))
    bpy.context.scene.render.resolution_x = int(width)
    bpy.context.scene.render.resolution_y = int(height)
    if params.get("output_path"):
        bpy.context.scene.render.filepath = params["output_path"]
    if params.get("render", False):
        bpy.ops.render.render(write_still=bool(params.get("output_path")))
    return {"camera": camera.name, "view": view, "output_path": params.get("output_path"), "rendered": params.get("render", False)}


def compare_silhouette_bounds(params: dict[str, Any]) -> dict[str, Any]:
    """Compare combined object bounds to expected bounds."""
    actual = get_bounding_box({"objects": params["objects"]})["combined"]
    expected_min = Vector(params["expected_min"])
    expected_max = Vector(params["expected_max"])
    actual_min = Vector(actual["min"])
    actual_max = Vector(actual["max"])
    tolerance = float(params.get("tolerance", 0.05))
    errors = {
        "min_delta": list(actual_min - expected_min),
        "max_delta": list(actual_max - expected_max),
    }
    max_error = max(abs(value) for values in errors.values() for value in values)
    return {"match": max_error <= tolerance, "max_error": max_error, "tolerance": tolerance, "actual": actual, "errors": errors}


def create_rounded_box(params: dict[str, Any]) -> dict[str, Any]:
    """Create a rounded box with bevel and weighted normals."""
    result = create_primitive(
        {
            "type": "beveled_box",
            "name": params["name"],
            "location": params.get("location", (0, 0, 0)),
            "size": params.get("size", (1, 1, 1)),
            "bevel": params.get("bevel", 0.05),
            "metadata": params.get("metadata", {}),
        }
    )
    obj = _object(params["name"])
    _assign_material_if_available(obj, params.get("material_name"))
    for modifier in obj.modifiers:
        if modifier.type == "BEVEL":
            modifier.segments = params.get("segments", 3)
    return result


def create_tapered_cylinder(params: dict[str, Any]) -> dict[str, Any]:
    """Create a tapered cylinder or cone frustum."""
    bpy.ops.mesh.primitive_cone_add(
        vertices=params.get("vertices", 48),
        radius1=params["radius_bottom"],
        radius2=params["radius_top"],
        depth=params["depth"],
        location=params.get("location", (0, 0, 0)),
    )
    obj = bpy.context.object
    obj.name = params["name"]
    _assign_material_if_available(obj, params.get("material_name"))
    if params.get("bevel", 0) > 0:
        bevel = obj.modifiers.new("MCP_Taper_Bevel", "BEVEL")
        bevel.width = params["bevel"]
        bevel.segments = 2
        obj.modifiers.new("MCP_Weighted_Normals", "WEIGHTED_NORMAL")
    return {**_object_summary(obj), "bounds": _bounds_for(obj)}


def create_capsule_segment(params: dict[str, Any]) -> dict[str, Any]:
    """Create a capsule segment from cylinder and sphere caps."""
    axis = params.get("axis", "Z")
    radius = params["radius"]
    length = params["length"]
    loc = Vector(params.get("location", (0, 0, 0)))
    rotation = {"X": (0, math.radians(90), 0), "Y": (math.radians(90), 0, 0), "Z": (0, 0, 0)}[axis]
    body = cyl(f"{params['name']}.Body", loc, radius, max(0.001, length - 2 * radius), _material(params["material_name"]) if params.get("material_name") else bpy.data.materials.new(f"{params['name']}_Material"), 48, rotation)
    direction = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}[axis]
    material = body.data.materials[0] if body.data.materials else None
    cap_a = sphere(f"{params['name']}.Cap_A", loc + direction * (length / 2 - radius), radius, material or body.data.materials[0])
    cap_b = sphere(f"{params['name']}.Cap_B", loc - direction * (length / 2 - radius), radius, material or body.data.materials[0])
    return {"name": params["name"], "parts": [body.name, cap_a.name, cap_b.name]}


def create_panel_seam(params: dict[str, Any]) -> dict[str, Any]:
    """Create a panel seam as a thin detail strip."""
    obj = cube(params["name"], params["location"], params["size"], _material(params["material_name"]) if params.get("material_name") else bpy.data.materials.new(f"{params['name']}_Material"), params.get("orientation", (0, 0, 0)))
    obj["mcp:role"] = "panel_seam"
    if params.get("target_name"):
        obj.parent = _object(params["target_name"])
    return {**_object_summary(obj), "bounds": _bounds_for(obj)}


def create_ring_joint(params: dict[str, Any]) -> dict[str, Any]:
    """Create a torus ring joint."""
    material = _material(params["material_name"]) if params.get("material_name") else bpy.data.materials.new(f"{params['name']}_Material")
    obj = torus(params["name"], params["location"], params["major_radius"], params["minor_radius"], material, params.get("orientation", (0, 0, 0)))
    obj["mcp:role"] = "ring_joint"
    return _object_summary(obj)


def create_slot_cut(params: dict[str, Any]) -> dict[str, Any]:
    """Create and optionally apply a Boolean rectangular slot."""
    cutter = cube(params.get("name", "Slot_Cutter"), params["location"], params["size"], bpy.data.materials.new(f"{params.get('name', 'Slot_Cutter')}_Material"))
    cutter.display_type = "WIRE"
    cutter.hide_render = True
    if params.get("apply", True):
        return boolean_operation({"target": params["target"], "cutter": cutter.name, "operation": "DIFFERENCE", "apply": True, "keep_cutter": params.get("keep_cutter", False)})
    return {"cutter": cutter.name, "target": params["target"], "applied": False}


def add_screw_array(params: dict[str, Any]) -> dict[str, Any]:
    """Place screw heads at points."""
    material = _material(params["material_name"]) if params.get("material_name") else bpy.data.materials.new(f"{params.get('name_prefix', 'Screw')}_Material")
    created = []
    for index, point in enumerate(params["points"], 1):
        head = cyl(f"{params.get('name_prefix', 'Screw')}_{index:03d}", point, params.get("radius", 0.08), params.get("depth", 0.035), material, 32)
        slot = cube(f"{head.name}_Slot", (point[0], point[1], point[2] + params.get("depth", 0.035) / 2), (params.get("radius", 0.08) * 1.3, 0.018, 0.012), material)
        created.extend([head.name, slot.name])
    return {"created": created}


def add_vent_grille(params: dict[str, Any]) -> dict[str, Any]:
    """Create repeated vent slats."""
    material = _material(params["material_name"]) if params.get("material_name") else bpy.data.materials.new(f"{params['name']}_Material")
    axis = _axis_index(params.get("axis", "X"))
    base = Vector(params["location"])
    created = []
    count = params["slat_count"]
    start = -((count - 1) * params["spacing"]) / 2
    for index in range(count):
        loc = base.copy()
        loc[axis] += start + index * params["spacing"]
        obj = cube(f"{params['name']}_Slat_{index + 1:03d}", loc, params["slat_size"], material)
        created.append(obj.name)
    return {"created": created, "count": len(created)}


def apply_weighted_normals(params: dict[str, Any]) -> dict[str, Any]:
    """Add weighted normal modifiers."""
    updated = []
    for name in params["objects"]:
        obj = _object(name)
        modifier = obj.modifiers.new("MCP_Weighted_Normals", "WEIGHTED_NORMAL")
        modifier.keep_sharp = params.get("keep_sharp", True)
        modifier.weight = params.get("weight", 50)
        updated.append({"name": obj.name, "modifier": modifier.name})
    return {"objects": updated}


def add_support_loops(params: dict[str, Any]) -> dict[str, Any]:
    """Add a narrow bevel as support-loop equivalent."""
    return bevel_edges({"object_name": params["object_name"], "width": params["width"], "segments": params.get("segments", 1), "apply": params.get("apply", False), "modifier_name": "MCP_Support_Loops"})


def create_pbr_material(params: dict[str, Any]) -> dict[str, Any]:
    """Create a PBR material with optional texture nodes."""
    material = bpy.data.materials.new(params["name"])
    material.use_nodes = True
    material.diffuse_color = _hex_or_rgba(params.get("base_color", "#ffffff"))
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        values = {
            "Base Color": material.diffuse_color,
            "Metallic": params.get("metallic", 0.0),
            "Roughness": params.get("roughness", 0.5),
            "Alpha": params.get("alpha", 1.0),
            "Specular IOR Level": params.get("specular", 0.5),
            "Specular": params.get("specular", 0.5),
        }
        for socket, value in values.items():
            if socket in bsdf.inputs:
                bsdf.inputs[socket].default_value = value
    for channel, path in params.get("texture_paths", {}).items():
        with contextlib.suppress(Exception):
            image = bpy.data.images.load(path)
            tex = material.node_tree.nodes.new("ShaderNodeTexImage")
            tex.name = f"{channel}_Texture"
            tex.image = image
            if bsdf and channel in {"Base Color", "base_color", "albedo", "diffuse"}:
                material.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return {"name": material.name, "base_color": list(material.diffuse_color), "use_nodes": material.use_nodes}


def create_toon_material(params: dict[str, Any]) -> dict[str, Any]:
    """Create a toon material using shader-to-RGB style nodes when available."""
    material = bpy.data.materials.new(params["name"])
    material.diffuse_color = _hex_or_rgba(params["base_color"])
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = material.diffuse_color
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = params.get("roughness", 0.55)
    material["mcp:material_style"] = "toon"
    material["mcp:toon_levels"] = params.get("levels", 3)
    if params.get("shadow_color"):
        material["mcp:shadow_color"] = json.dumps(_hex_or_rgba(params["shadow_color"]))
    return {"name": material.name, "style": "toon", "levels": params.get("levels", 3)}


def create_procedural_material(params: dict[str, Any]) -> dict[str, Any]:
    """Create a procedural noise-based material."""
    material = bpy.data.materials.new(params["name"])
    material.diffuse_color = _hex_or_rgba(params["base_color"])
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = params.get("scale", 18.0)
    noise.inputs["Detail"].default_value = 8
    color_ramp = nodes.new("ShaderNodeValToRGB")
    color_ramp.color_ramp.elements[0].position = 0.25
    color_ramp.color_ramp.elements[0].color = _hex_or_rgba(params["secondary_color"])
    color_ramp.color_ramp.elements[1].color = _hex_or_rgba(params["base_color"])
    material.node_tree.links.new(noise.outputs["Fac"], color_ramp.inputs["Fac"])
    if bsdf:
        material.node_tree.links.new(color_ramp.outputs["Color"], bsdf.inputs["Base Color"])
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.65
    material["mcp:procedural_pattern"] = params.get("pattern", "noise")
    return {"name": material.name, "pattern": params.get("pattern", "noise")}


def add_edge_wear(params: dict[str, Any]) -> dict[str, Any]:
    """Store edge-wear settings and add a real edge-wear shader node setup."""
    material = _material(params["material_name"])
    amount = params.get("amount", 0.2)
    color_val = params.get("color", "#d8d0b8")

    material["mcp:edge_wear_amount"] = amount
    material["mcp:edge_wear_color"] = json.dumps(_hex_or_rgba(color_val))

    material.use_nodes = True
    nt = material.node_tree
    nodes = nt.nodes
    links = nt.links

    bsdf = nodes.get("Principled BSDF")
    if not bsdf:
        raise CommandError("ShaderNodeError", "Principled BSDF node not found in material.")

    # Remove existing wear nodes to avoid accumulation
    for node_name in ["MCP_Geometry", "MCP_ColorRamp", "MCP_Mix"]:
        if node_name in nodes:
            nodes.remove(nodes[node_name])

    # Intercept existing link to Base Color
    base_color_input = bsdf.inputs.get("Base Color")
    existing_link = None
    if base_color_input:
        for link in nt.links:
            if link.to_socket == base_color_input:
                existing_link = link
                break

    # Create new nodes
    geom = nodes.new("ShaderNodeNewGeometry")
    geom.name = "MCP_Geometry"
    geom.label = "Edge Wear Geometry"
    geom.location = (-600, 300)

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.name = "MCP_ColorRamp"
    ramp.label = "Edge Wear Contrast"
    ramp.location = (-400, 300)

    # Configure ColorRamp elements
    ramp.color_ramp.elements[0].position = 0.5
    ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)

    pos_1 = max(0.501, min(0.9, 0.5 + (1.0 - amount) * 0.1))
    ramp.color_ramp.elements[1].position = pos_1
    ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    mix = nodes.new("ShaderNodeMix")
    mix.name = "MCP_Mix"
    mix.label = "Edge Wear Mix"
    mix.data_type = 'RGBA'
    mix.location = (-150, 300)

    mix.inputs["B"].default_value = _hex_or_rgba(color_val)

    if existing_link:
        source_socket = existing_link.from_socket
        links.remove(existing_link)
        links.new(source_socket, mix.inputs["A"])
    else:
        if base_color_input:
            mix.inputs["A"].default_value = list(base_color_input.default_value)

    # Connect nodes
    links.new(geom.outputs["Pointiness"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], mix.inputs["Factor"])
    if base_color_input:
        links.new(mix.outputs["Result"], base_color_input)

    return {"material_name": material.name, "edge_wear_amount": amount, "edge_wear_color": color_val}


def assign_material_by_name(params: dict[str, Any]) -> dict[str, Any]:
    """Assign one material to multiple objects."""
    material = _material(params["material_name"])
    updated = []
    for name in params["objects"]:
        obj = _object(name)
        if hasattr(obj.data, "materials"):
            obj.data.materials.clear()
            obj.data.materials.append(material)
            updated.append(obj.name)
    return {"material_name": material.name, "objects": updated}


def create_decal(params: dict[str, Any]) -> dict[str, Any]:
    """Create a simple decal plane or text object."""
    material = bpy.data.materials.new(f"{params['name']}_Material")
    material.diffuse_color = _hex_or_rgba(params.get("color", "#ffffff"))
    if params.get("image_path"):
        material.use_nodes = True
        image = bpy.data.images.load(params["image_path"])
        tex = material.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = image
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            material.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if params.get("text"):
        curve = bpy.data.curves.new(params["name"], "FONT")
        curve.body = params["text"]
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        obj = bpy.data.objects.new(params["name"], curve)
        bpy.context.collection.objects.link(obj)
        obj.location = params.get("location", (0, 0, 0))
        obj.scale = (params.get("size", (1.0, 0.35))[0], params.get("size", (1.0, 0.35))[1], 1)
    else:
        bpy.ops.mesh.primitive_plane_add(size=1, location=params.get("location", (0, 0, 0)))
        obj = bpy.context.object
        obj.name = params["name"]
        size = params.get("size", (1.0, 0.35))
        obj.dimensions = (size[0], size[1], 0)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if params.get("target_object"):
        obj.parent = _object(params["target_object"])
    obj["mcp:role"] = "decal"
    return _object_summary(obj)


def add_outline_modifier(params: dict[str, Any]) -> dict[str, Any]:
    """Add an outline material and solidify modifier."""
    outline_material = bpy.data.materials.get("MCP_Outline_Material") or bpy.data.materials.new("MCP_Outline_Material")
    outline_material.diffuse_color = _hex_or_rgba(params.get("edge_color", "#000000"))
    updated = []
    for name in params["objects"]:
        obj = _object(name)
        if hasattr(obj.data, "materials") and outline_material.name not in [slot.material.name for slot in obj.material_slots if slot.material]:
            obj.data.materials.append(outline_material)
        modifier = obj.modifiers.new("MCP_Toon_Outline", "SOLIDIFY")
        modifier.thickness = params.get("thickness", 0.025)
        modifier.use_flip_normals = True
        updated.append({"name": obj.name, "modifier": modifier.name})
    return {"objects": updated, "material": outline_material.name}


def apply_material_variation(params: dict[str, Any]) -> dict[str, Any]:
    """Duplicate a source material and assign variations."""
    source = _material(params["source_material"])
    updated = []
    for index, name in enumerate(params["objects"], 1):
        obj = _object(name)
        material = source.copy()
        material.name = f"{params.get('variation_prefix', 'Var')}_{index:03d}_{source.name}"
        if material.diffuse_color:
            color = list(material.diffuse_color)
            color[0] = min(1.0, max(0.0, color[0] + params.get("hue_shift", 0.0)))
            material.diffuse_color = color
        obj.data.materials.clear()
        obj.data.materials.append(material)
        updated.append({"object": obj.name, "material": material.name})
    return {"objects": updated}


def _quality_objects(params: dict[str, Any]) -> list[bpy.types.Object]:
    names = params.get("objects")
    return [_object(name) for name in names] if names else [obj for obj in bpy.data.objects if obj.type == "MESH"]


def detect_overlaps(params: dict[str, Any]) -> dict[str, Any]:
    """Detect bounding-box overlaps."""
    objects = _quality_objects(params)
    tolerance = float(params.get("tolerance", 0.001))
    issues = []
    bounds = {obj.name: _bounds_for(obj) for obj in objects}
    for index, obj_a in enumerate(objects):
        a = bounds[obj_a.name]
        for obj_b in objects[index + 1 :]:
            b = bounds[obj_b.name]
            if params.get("ignore_touching", True):
                overlap = all(a["min"][axis] < b["max"][axis] - tolerance and a["max"][axis] > b["min"][axis] + tolerance for axis in range(3))
            else:
                overlap = all(a["min"][axis] <= b["max"][axis] + tolerance and a["max"][axis] >= b["min"][axis] - tolerance for axis in range(3))
            if overlap:
                issues.append({"objects": [obj_a.name, obj_b.name]})
                if len(issues) >= params.get("limit", 200):
                    return {"overlaps": issues, "count": len(issues), "truncated": True}
    return {"overlaps": issues, "count": len(issues), "truncated": False}


def validate_scene_quality(params: dict[str, Any]) -> dict[str, Any]:
    """Run a broad quality pass."""
    objects = _quality_objects(params)
    checks = set(params.get("checks", []))
    issues = []
    if "overlaps" in checks:
        for item in detect_overlaps({"objects": [obj.name for obj in objects], "tolerance": params.get("tolerance", 0.001), "limit": 200})["overlaps"]:
            issues.append({"type": "BoundsOverlap", **item})
    if "floating" in checks:
        ground_z = params.get("ground_z", 0.0)
        bounds_by_name = {obj.name: _bounds_for(obj) for obj in objects}
        for obj in objects:
            bounds = bounds_by_name[obj.name]
            min_z = bounds["min"][2]
            supported = False
            for other in objects:
                if other.name == obj.name:
                    continue
                other_bounds = bounds_by_name[other.name]
                horizontal_overlap = all(
                    bounds["min"][axis] < other_bounds["max"][axis] - params.get("tolerance", 0.001)
                    and bounds["max"][axis] > other_bounds["min"][axis] + params.get("tolerance", 0.001)
                    for axis in (0, 1)
                )
                vertical_contact = abs(min_z - other_bounds["max"][2]) <= params.get("tolerance", 0.001)
                if horizontal_overlap and vertical_contact:
                    supported = True
                    break
            if min_z > ground_z + params.get("tolerance", 0.001) and not supported:
                issues.append({"type": "FloatingObject", "object": obj.name, "min_z": min_z})
    if "missing_materials" in checks:
        for obj in objects:
            if not obj.material_slots:
                issues.append({"type": "MissingMaterial", "object": obj.name})
    if "missing_metadata" in checks:
        for obj in objects:
            if not _read_metadata(obj) and not any(str(key).startswith("mcp:") for key in obj.keys()):
                issues.append({"type": "MissingMetadata", "object": obj.name})
    if "bad_names" in checks:
        for obj in objects:
            if obj.name.startswith(("Cube", "Cylinder", "Sphere")):
                issues.append({"type": "GenericName", "object": obj.name})
    if "unapplied_scale" in checks:
        for obj in objects:
            if any(abs(component - 1.0) > 0.001 for component in obj.scale):
                issues.append({"type": "UnappliedScale", "object": obj.name, "scale": list(obj.scale)})
    if "high_poly" in checks:
        max_vertices = params.get("max_vertices", 100000)
        for obj in objects:
            if hasattr(obj.data, "vertices") and len(obj.data.vertices) > max_vertices:
                issues.append({"type": "HighPoly", "object": obj.name, "vertices": len(obj.data.vertices)})
    if "no_parent" in checks:
        for obj in objects:
            if obj.parent is None:
                issues.append({"type": "NoParent", "object": obj.name})
    return {"valid": not issues, "issues": issues, "checked": len(objects)}


def validate_symmetry(params: dict[str, Any]) -> dict[str, Any]:
    """Validate approximate symmetry by comparing centers and dimensions."""
    axis = _axis_index(params.get("axis", "X"))
    tolerance = float(params.get("tolerance", 0.05))
    pairs = []
    issues = []
    for left_name, right_name in zip(params["left_objects"], params["right_objects"], strict=False):
        left = _bounds_for(_object(left_name))
        right = _bounds_for(_object(right_name))
        left_center = Vector(left["center"])
        right_center = Vector(right["center"])
        center_error = abs(left_center[axis] + right_center[axis])
        dim_error = max(abs(left["dimensions"][idx] - right["dimensions"][idx]) for idx in range(3))
        pair = {"left": left_name, "right": right_name, "center_error": center_error, "dimension_error": dim_error}
        pairs.append(pair)
        if center_error > tolerance or dim_error > tolerance:
            issues.append(pair)
    return {"symmetric": not issues, "pairs": pairs, "issues": issues}


def check_scale_consistency(params: dict[str, Any]) -> dict[str, Any]:
    """Check object dimensions against ranges."""
    issues = []
    for name in params["objects"]:
        bounds = _bounds_for(_object(name))
        dims = bounds["dimensions"]
        if params.get("min_dimensions") and any(dims[idx] < params["min_dimensions"][idx] for idx in range(3)):
            issues.append({"type": "BelowMinDimensions", "object": name, "dimensions": dims})
        if params.get("max_dimensions") and any(dims[idx] > params["max_dimensions"][idx] for idx in range(3)):
            issues.append({"type": "AboveMaxDimensions", "object": name, "dimensions": dims})
    return {"valid": not issues, "issues": issues}


def generate_quality_report(params: dict[str, Any]) -> dict[str, Any]:
    """Generate a compact scene quality report."""
    objects = _quality_objects(params)
    report: dict[str, Any] = {"object_count": len(objects)}
    if params.get("include_counts", True):
        report["type_counts"] = {}
        for obj in objects:
            report["type_counts"][obj.type] = report["type_counts"].get(obj.type, 0) + 1
    if params.get("include_materials", True):
        report["materials"] = sorted({slot.material.name for obj in objects for slot in obj.material_slots if slot.material})
    if params.get("include_collections", True):
        report["collections"] = [{"name": collection.name, "objects": len(collection.objects)} for collection in bpy.data.collections]
    if params.get("include_issues", True):
        report["quality"] = validate_scene_quality(
            {
                "objects": [obj.name for obj in objects],
                "checks": [
                    "overlaps",
                    "floating",
                    "missing_materials",
                    "bad_names",
                    "unapplied_scale",
                    "high_poly",
                ],
            }
        )
    return report


def suggest_model_improvements(params: dict[str, Any]) -> dict[str, Any]:
    """Suggest next modeling improvements."""
    quality = validate_scene_quality({"objects": params.get("objects") or None})
    suggestions = []
    issue_types = {issue["type"] for issue in quality["issues"]}
    if "MissingMaterial" in issue_types:
        suggestions.append("Assign PBR/toon materials to unshaded mesh objects.")
    if "UnappliedScale" in issue_types:
        suggestions.append("Apply transforms or normalize scale before beveling/boolean operations.")
    if "BoundsOverlap" in issue_types:
        suggestions.append("Resolve object overlaps with get_bounding_box, align_objects, or snap_to_ground.")
    if "FloatingObject" in issue_types:
        suggestions.append("Use snap_to_ground on floating objects.")
    if params.get("target_quality", "production") == "production":
        suggestions.extend(["Add bevels/weighted normals to hard-surface parts.", "Organize components under named roots and attach semantic metadata.", "Render orthographic previews for visual review."])
    return {"quality": quality, "suggestions": suggestions}


def set_render_engine(params: dict[str, Any]) -> dict[str, Any]:
    scene = bpy.context.scene
    engine = params["engine"].upper()
    if engine == "BLENDER_EEVEE_NEXT":
        engine = "BLENDER_EEVEE"
    scene.render.engine = engine
    if params.get("device") and engine == "CYCLES":
        scene.cycles.device = params["device"].upper()
    return {"engine": scene.render.engine, "device": getattr(scene.cycles, "device", None) if hasattr(scene, "cycles") else None}


def set_render_resolution(params: dict[str, Any]) -> dict[str, Any]:
    scene = bpy.context.scene
    scene.render.resolution_x = int(params["width"])
    scene.render.resolution_y = int(params["height"])
    scene.render.resolution_percentage = int(params.get("percentage", 100))
    return {"width": scene.render.resolution_x, "height": scene.render.resolution_y, "percentage": scene.render.resolution_percentage}


def set_render_output(params: dict[str, Any]) -> dict[str, Any]:
    scene = bpy.context.scene
    scene.render.filepath = params["output_path"]
    scene.render.image_settings.file_format = params.get("file_format", "PNG").upper()
    scene.render.image_settings.color_mode = params.get("color_mode", "RGBA").upper()
    scene.render.image_settings.color_depth = str(params.get("color_depth", "8"))
    if params.get("compression") is not None:
        scene.render.image_settings.compression = int(params["compression"])
    return {
        "output_path": scene.render.filepath,
        "file_format": scene.render.image_settings.file_format,
        "color_mode": scene.render.image_settings.color_mode,
        "color_depth": scene.render.image_settings.color_depth
    }


def set_cycles_samples(params: dict[str, Any]) -> dict[str, Any]:
    scene = bpy.context.scene
    if hasattr(scene, "cycles"):
        scene.cycles.samples = int(params["render_samples"])
        if params.get("viewport_samples") is not None:
            scene.cycles.preview_samples = int(params["viewport_samples"])
        if params.get("use_denoising") is not None:
            scene.cycles.use_denoising = bool(params["use_denoising"])
        return {
            "render_samples": scene.cycles.samples,
            "viewport_samples": getattr(scene.cycles, "preview_samples", None),
            "use_denoising": getattr(scene.cycles, "use_denoising", None)
        }
    raise CommandError("CyclesNotActive", "Cycles settings are not accessible.")


def set_eevee_settings(params: dict[str, Any]) -> dict[str, Any]:
    scene = bpy.context.scene
    eevee = scene.eevee
    if params.get("ambient_occlusion") is not None:
        if hasattr(eevee, "use_ambient_occlusion"):
            eevee.use_ambient_occlusion = bool(params["ambient_occlusion"])
        elif hasattr(eevee, "use_gtao"):
            eevee.use_gtao = bool(params["ambient_occlusion"])
    if params.get("bloom") is not None:
        if hasattr(eevee, "use_bloom"):
            eevee.use_bloom = bool(params["bloom"])
    if params.get("screen_space_reflections") is not None:
        if hasattr(eevee, "use_ssr"):
            eevee.use_ssr = bool(params["screen_space_reflections"])
        elif hasattr(eevee, "use_raytracing"):
            eevee.use_raytracing = bool(params["screen_space_reflections"])
    for k, v in params.get("settings", {}).items():
        if hasattr(eevee, k):
            setattr(eevee, k, v)
    return {
        "ambient_occlusion": getattr(eevee, "use_ambient_occlusion", getattr(eevee, "use_gtao", None)),
        "bloom": getattr(eevee, "use_bloom", None),
        "ssr": getattr(eevee, "use_ssr", getattr(eevee, "use_raytracing", None))
    }


def render_image(params: dict[str, Any]) -> dict[str, Any]:
    scene = bpy.context.scene
    old_path = scene.render.filepath
    if params.get("output_path"):
        scene.render.filepath = params["output_path"]
    bpy.ops.render.render(write_still=bool(params.get("write_still", True)))
    res_path = scene.render.filepath
    if params.get("output_path"):
        scene.render.filepath = old_path
    return {"status": "rendered", "filepath": res_path}


def render_animation(params: dict[str, Any]) -> dict[str, Any]:
    scene = bpy.context.scene
    old_path = scene.render.filepath
    if params.get("output_path"):
        scene.render.filepath = params["output_path"]
    old_start = scene.frame_start
    old_end = scene.frame_end
    if params.get("start_frame") is not None:
        scene.frame_start = int(params["start_frame"])
    if params.get("end_frame") is not None:
        scene.frame_end = int(params["end_frame"])
    
    bpy.ops.render.render(animation=True)
    
    if params.get("output_path"):
        scene.render.filepath = old_path
    if params.get("start_frame") is not None:
        scene.frame_start = old_start
    if params.get("end_frame") is not None:
        scene.frame_end = old_end
    return {"status": "rendered_animation"}


def add_render_pass(params: dict[str, Any]) -> dict[str, Any]:
    vl = bpy.context.view_layer
    pass_name = params["pass_name"].lower()
    attr = f"use_pass_{pass_name}"
    if hasattr(vl, attr):
        setattr(vl, attr, bool(params.get("enabled", True)))
        return {"pass_name": pass_name, "enabled": getattr(vl, attr)}
    raise CommandError("PassNotFound", f"Render pass '{params['pass_name']}' is not supported directly on view layer.")


def set_color_management(params: dict[str, Any]) -> dict[str, Any]:
    scene = bpy.context.scene
    vs = scene.view_settings
    ds = scene.display_settings
    if params.get("display_device"):
        ds.display_device = params["display_device"]
    if params.get("view_transform"):
        vs.view_transform = params["view_transform"]
    if params.get("look"):
        vs.look = params["look"]
    if params.get("exposure") is not None:
        vs.exposure = float(params["exposure"])
    if params.get("gamma") is not None:
        vs.gamma = float(params["gamma"])
    return {"view_transform": vs.view_transform, "exposure": vs.exposure, "gamma": vs.gamma}


def unwrap_uv(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="OBJECT")
    if params.get("uv_map"):
        uv_map = obj.data.uv_layers.get(params["uv_map"]) or obj.data.uv_layers.new(name=params["uv_map"])
        obj.data.uv_layers.active = uv_map
    bpy.ops.object.mode_set(mode="EDIT")
    if not params.get("selected_only", False):
        bpy.ops.mesh.select_all(action="SELECT")
    
    method = params.get("method", "SMART").upper()
    if method == "SMART":
        bpy.ops.uv.smart_project(
            angle_limit=math.radians(params.get("angle_limit", 66.0)),
            island_margin=params.get("island_margin", 0.03),
            area_weight=params.get("area_weight", 0.0),
            correct_aspect=params.get("correct_aspect", True)
        )
    elif method == "CUBE":
        bpy.ops.uv.cube_project(cube_size=1.0)
    elif method == "CYLINDER":
        bpy.ops.uv.cylinder_project()
    elif method == "SPHERE":
        bpy.ops.uv.sphere_project()
    else:
        bpy.ops.uv.unwrap(method=method, margin=params.get("island_margin", 0.03))
        
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"object_name": obj.name, "uv_map": obj.data.uv_layers.active.name, "method": method}


def pack_uvs(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    bpy.context.view_layer.objects.active = obj
    if params.get("uv_map"):
        uv_map = obj.data.uv_layers.get(params["uv_map"])
        if uv_map:
            obj.data.uv_layers.active = uv_map
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try:
        bpy.ops.uv.pack_islands(
            margin=params.get("margin", 0.03),
            rotate=params.get("rotate", True),
            scale_to_fit=params.get("scale", True)
        )
    except Exception:
        bpy.ops.uv.pack_islands(margin=params.get("margin", 0.03))
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"object_name": obj.name, "packed": True}


def scale_uvs(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    bpy.context.view_layer.objects.active = obj
    if params.get("uv_map"):
        uv_map = obj.data.uv_layers.get(params["uv_map"])
        if uv_map:
            obj.data.uv_layers.active = uv_map
    bpy.ops.object.mode_set(mode="OBJECT")
    scale = params["scale"]
    pivot = params.get("pivot", (0.5, 0.5))
    uv_layer = obj.data.uv_layers.active.data
    for loop in obj.data.loops:
        uv = uv_layer[loop.index].uv
        uv[0] = pivot[0] + (uv[0] - pivot[0]) * scale[0]
        uv[1] = pivot[1] + (uv[1] - pivot[1]) * scale[1]
    obj.data.update()
    return {"object_name": obj.name, "scaled": True, "scale": scale}


def select_uv_island(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(obj.data)
    if not params.get("extend", False):
        for f in bm.faces:
            f.select = False
    if params.get("face_index") is not None:
        face_idx = params["face_index"]
        if face_idx < len(bm.faces):
            bm.faces[face_idx].select = True
            bmesh.update_edit_mesh(obj.data)
            bpy.ops.mesh.select_linked(delimit={'UV'})
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"object_name": obj.name, "selected": True}


def export_uv_layout(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.export_layout(
        filepath=params["output_path"],
        size=params.get("size", (2048, 2048)),
        opacity=params.get("opacity", 0.25),
        format=params.get("mode", "PNG").upper()
    )
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"object_name": obj.name, "filepath": params["output_path"]}


def add_geometry_nodes_modifier(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    modifier = obj.modifiers.new(params.get("modifier_name", "Geometry Nodes"), "NODES")
    if params.get("node_group_name"):
        group_name = params["node_group_name"]
        node_group = bpy.data.node_groups.get(group_name)
        if not node_group:
            node_group = bpy.data.node_groups.new(group_name, "GeometryNodeTree")
            if params.get("create_default_io", True):
                node_group.nodes.new("NodeGroupInput")
                node_group.nodes.new("NodeGroupOutput")
        modifier.node_group = node_group
    return {"object_name": obj.name, "modifier_name": modifier.name, "node_group": modifier.node_group.name if modifier.node_group else None}


def create_node(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    modifier = obj.modifiers.get(params.get("modifier_name") or "Geometry Nodes")
    if not modifier or modifier.type != "NODES" or not modifier.node_group:
        raise CommandError("GeometryNodesNotSetup", f"Geometry Nodes modifier is not setup on '{obj.name}'")
    group = modifier.node_group
    node = group.nodes.new(params["node_type"])
    if params.get("node_name"):
        node.name = params["node_name"]
    if "location" in params:
        node.location = params["location"]
    for k, v in params.get("properties", {}).items():
        if hasattr(node, k):
            setattr(node, k, v)
    return {"node_name": node.name, "node_type": node.bl_idname}


def connect_nodes(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    modifier = obj.modifiers.get(params.get("modifier_name") or "Geometry Nodes")
    if not modifier or modifier.type != "NODES" or not modifier.node_group:
        raise CommandError("GeometryNodesNotSetup", f"Geometry Nodes modifier is not setup on '{obj.name}'")
    group = modifier.node_group
    from_node = group.nodes.get(params["from_node"])
    to_node = group.nodes.get(params["to_node"])
    if not from_node or not to_node:
        raise CommandError("NodeNotFound", "From or to node not found in nodes tree.")
        
    def get_socket(node, ref, is_output=False):
        sockets = node.outputs if is_output else node.inputs
        if isinstance(ref, int):
            if ref < len(sockets):
                return sockets[ref]
        else:
            if ref in sockets:
                return sockets[ref]
            for s in sockets:
                if s.name == ref:
                    return s
        raise CommandError("SocketNotFound", f"Socket '{ref}' not found on node '{node.name}'")
        
    out_socket = get_socket(from_node, params["from_socket"], True)
    in_socket = get_socket(to_node, params["to_socket"], False)
    group.links.new(out_socket, in_socket)
    return {"connected": True}


def set_node_input(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    modifier = obj.modifiers.get(params.get("modifier_name") or "Geometry Nodes")
    if not modifier or modifier.type != "NODES" or not modifier.node_group:
        raise CommandError("GeometryNodesNotSetup", f"Geometry Nodes modifier is not setup on '{obj.name}'")
    group = modifier.node_group
    node = group.nodes.get(params["node_name"])
    if not node:
        raise CommandError("NodeNotFound", f"Node '{params['node_name']}' not found.")
    
    ref = params["input_socket"]
    sockets = node.inputs
    socket = None
    if isinstance(ref, int):
        if ref < len(sockets):
            socket = sockets[ref]
    else:
        if ref in sockets:
            socket = sockets[ref]
        else:
            for s in sockets:
                if s.name == ref:
                    socket = s
                    break
    if not socket:
        raise CommandError("SocketNotFound", f"Socket '{ref}' not found on node '{node.name}'")
    socket.default_value = params["value"]
    return {"node_name": node.name, "socket": socket.name, "value": socket.default_value}


def set_geonode_input(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    modifier = obj.modifiers.get(params.get("modifier_name") or "Geometry Nodes")
    if not modifier or modifier.type != "NODES":
        raise CommandError("GeometryNodesNotSetup", f"Geometry Nodes modifier is not setup on '{obj.name}'")
    group = modifier.node_group
    if not group:
        raise CommandError("NoNodeGroup", "No node group linked to modifier.")
    
    found_input = None
    if hasattr(group, "interface"):
        for item in group.interface.items:
            if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == params["input_name"]:
                found_input = item
                break
    else:
        found_input = group.inputs.get(params["input_name"])
        
    if not found_input:
        raise CommandError("InputNotFound", f"Group input '{params['input_name']}' not found.")
        
    identifier = found_input.identifier
    modifier[identifier] = params["value"]
    obj.data.update()
    return {"object_name": obj.name, "input_name": params["input_name"], "value": modifier[identifier]}


def list_nodes(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    modifier = obj.modifiers.get(params.get("modifier_name") or "Geometry Nodes")
    if not modifier or modifier.type != "NODES" or not modifier.node_group:
        return {"nodes": [], "links": []}
    group = modifier.node_group
    nodes_list = []
    for node in group.nodes:
        ninfo = {"name": node.name, "type": node.bl_idname, "location": list(node.location)}
        if params.get("include_socket_defaults", True):
            ninfo["inputs"] = [{"name": s.name, "default_value": getattr(s, "default_value", None)} for s in node.inputs]
            ninfo["outputs"] = [{"name": s.name, "default_value": getattr(s, "default_value", None)} for s in node.outputs]
        nodes_list.append(ninfo)
    links_list = []
    if params.get("include_links", True):
        for link in group.links:
            links_list.append({
                "from_node": link.from_node.name,
                "from_socket": link.from_socket.name,
                "to_node": link.to_node.name,
                "to_socket": link.to_socket.name
            })
    return {"nodes": nodes_list, "links": links_list}


def import_file(params: dict[str, Any]) -> dict[str, Any]:
    filepath = params["file_path"]
    fmt = params.get("file_format", "AUTO").upper()
    if fmt == "AUTO":
        ext = os.path.splitext(filepath)[1].lower()
        ext_map = {
            ".fbx": "FBX", ".obj": "OBJ", ".gltf": "GLTF", ".glb": "GLTF",
            ".stl": "STL", ".ply": "PLY", ".abc": "ABC", ".usd": "USD",
            ".usda": "USD", ".usdc": "USD", ".usdz": "USD", ".svg": "SVG", ".dxf": "DXF"
        }
        fmt = ext_map.get(ext, "AUTO")
    if fmt == "AUTO":
        raise CommandError("UnknownFormat", "Could not automatically determine the file format.")
    
    pre_objs = set(bpy.data.objects)
    
    if fmt == "FBX":
        bpy.ops.import_scene.fbx(filepath=filepath, **params.get("options", {}))
    elif fmt == "OBJ":
        if hasattr(bpy.ops.import_scene, "obj"):
            bpy.ops.import_scene.obj(filepath=filepath, **params.get("options", {}))
        else:
            bpy.ops.wm.obj_import(filepath=filepath, **params.get("options", {}))
    elif fmt in ("GLTF", "GLB"):
        bpy.ops.import_scene.gltf(filepath=filepath, **params.get("options", {}))
    elif fmt == "STL":
        if hasattr(bpy.ops.import_mesh, "stl"):
            bpy.ops.import_mesh.stl(filepath=filepath, **params.get("options", {}))
        else:
            bpy.ops.wm.stl_import(filepath=filepath, **params.get("options", {}))
    elif fmt == "PLY":
        if hasattr(bpy.ops.import_mesh, "ply"):
            bpy.ops.import_mesh.ply(filepath=filepath, **params.get("options", {}))
        else:
            bpy.ops.wm.ply_import(filepath=filepath, **params.get("options", {}))
    elif fmt == "ABC":
        bpy.ops.wm.alembic_import(filepath=filepath, **params.get("options", {}))
    elif fmt == "USD":
        bpy.ops.wm.usd_import(filepath=filepath, **params.get("options", {}))
    elif fmt == "SVG":
        bpy.ops.import_curve.svg(filepath=filepath, **params.get("options", {}))
    else:
        raise CommandError("UnsupportedFormat", f"Importer for format '{fmt}' is not implemented.")
        
    new_objs = list(set(bpy.data.objects) - pre_objs)
    
    if params.get("collection_name") and new_objs:
        col = bpy.data.collections.get(params["collection_name"]) or bpy.data.collections.new(params["collection_name"])
        if col.name not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(col)
        for obj in new_objs:
            if obj.name not in col.objects:
                col.objects.link(obj)
            for c in list(obj.users_collection):
                if c != col:
                    c.objects.unlink(obj)
                    
    return {"imported_count": len(new_objs), "imported_objects": [obj.name for obj in new_objs]}


def export_file(params: dict[str, Any]) -> dict[str, Any]:
    filepath = params["file_path"]
    fmt = params.get("file_format", "AUTO").upper()
    if fmt == "AUTO":
        ext = os.path.splitext(filepath)[1].lower()
        ext_map = {
            ".fbx": "FBX", ".obj": "OBJ", ".gltf": "GLTF", ".glb": "GLTF",
            ".stl": "STL", ".ply": "PLY", ".abc": "ABC", ".usd": "USD",
            ".usda": "USD", ".usdc": "USD", ".usdz": "USD", ".svg": "SVG", ".dxf": "DXF"
        }
        fmt = ext_map.get(ext, "AUTO")
    if fmt == "AUTO":
        raise CommandError("UnknownFormat", "Could not automatically determine the file format.")
    
    opts = params.get("options", {})
    selected_only = params.get("selected_only", False)
    
    if fmt == "FBX":
        bpy.ops.export_scene.fbx(filepath=filepath, use_selection=selected_only, **opts)
    elif fmt == "OBJ":
        if hasattr(bpy.ops.export_scene, "obj"):
            bpy.ops.export_scene.obj(filepath=filepath, use_selection=selected_only, **opts)
        else:
            bpy.ops.wm.obj_export(filepath=filepath, export_selected=selected_only, **opts)
    elif fmt in ("GLTF", "GLB"):
        export_format = "GLB" if os.path.splitext(filepath)[1].lower() == ".glb" else "GLTF_EMBEDDED"
        bpy.ops.export_scene.gltf(filepath=filepath, export_format=export_format, use_selection=selected_only, **opts)
    elif fmt == "STL":
        if hasattr(bpy.ops.export_mesh, "stl"):
            bpy.ops.export_mesh.stl(filepath=filepath, use_selection=selected_only, **opts)
        else:
            bpy.ops.wm.stl_export(filepath=filepath, export_selected=selected_only, **opts)
    elif fmt == "PLY":
        if hasattr(bpy.ops.export_mesh, "ply"):
            bpy.ops.export_mesh.ply(filepath=filepath, use_selection=selected_only, **opts)
        else:
            bpy.ops.wm.ply_export(filepath=filepath, export_selected=selected_only, **opts)
    else:
        raise CommandError("UnsupportedFormat", f"Exporter for format '{fmt}' is not implemented.")
    return {"filepath": filepath}


def import_image_as_plane(params: dict[str, Any]) -> dict[str, Any]:
    try:
        if "io_import_images_as_planes" not in bpy.context.preferences.addons:
            bpy.ops.preferences.addon_enable(module="io_import_images_as_planes")
        bpy.ops.import_image.to_plane(
            files=[{"name": os.path.basename(params["image_path"])}],
            directory=os.path.dirname(params["image_path"]),
            size_mode='ABSOLUTE',
            height=params.get("size", 1.0),
            shader=params.get("shader", "PRINCIPLED")
        )
        obj = bpy.context.object
    except Exception:
        size = params.get("size", 1.0)
        mesh = bpy.data.meshes.new("PlaneImage")
        sx, sy = size / 2.0, size / 2.0
        verts = [(-sx, -sy, 0), (sx, -sy, 0), (sx, sy, 0), (-sx, sy, 0)]
        faces = [(0, 1, 2, 3)]
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        
        uv = mesh.uv_layers.new(name="UVMap")
        uv.data[0].uv = (0, 0)
        uv.data[1].uv = (1, 0)
        uv.data[2].uv = (1, 1)
        uv.data[3].uv = (0, 1)
        
        obj = bpy.data.objects.new(params.get("name") or "ImagePlane", mesh)
        bpy.context.collection.objects.link(obj)
        
        mat = bpy.data.materials.new(name=f"Mat_{obj.name}")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        img_node = nodes.new("ShaderNodeTexImage")
        try:
            img_node.image = bpy.data.images.load(params["image_path"])
        except Exception:
            pass
            
        bsdf = nodes.get("Principled BSDF")
        if bsdf:
            links.new(img_node.outputs["Color"], bsdf.inputs["Base Color"])
            if params.get("use_alpha", True) and "Alpha" in bsdf.inputs and "Alpha" in img_node.outputs:
                links.new(img_node.outputs["Alpha"], bsdf.inputs["Alpha"])
                mat.blend_method = 'BLEND'
        obj.data.materials.append(mat)
        
    obj.location = params.get("location", (0.0, 0.0, 0.0))
    obj.rotation_euler = params.get("rotation", (0.0, 0.0, 0.0))
    if params.get("name"):
        obj.name = params["name"]
    return _object_summary(obj)


def link_blend_file(params: dict[str, Any]) -> dict[str, Any]:
    return _load_blend_library("link", params)


def append_blend_file(params: dict[str, Any]) -> dict[str, Any]:
    return _load_blend_library("append", params)


def _load_blend_library(mode: str, params: dict[str, Any]) -> dict[str, Any]:
    filepath = params["blend_path"]
    data_type = params["data_type"]
    names = params["names"]
    col_name = params.get("collection_name")
    
    with bpy.data.libraries.load(filepath, link=(mode == "link")) as (data_from, data_to):
        from_list = getattr(data_from, data_type, [])
        to_list = []
        for n in names:
            if n in from_list:
                to_list.append(n)
        setattr(data_to, data_type, to_list)
        
    loaded = getattr(data_to, data_type, [])
    
    if data_type == "objects" and loaded:
        target_col = bpy.context.scene.collection
        if col_name:
            target_col = bpy.data.collections.get(col_name) or bpy.data.collections.new(col_name)
            if target_col.name not in bpy.context.scene.collection.children:
                bpy.context.scene.collection.children.link(target_col)
                
        for obj in loaded:
            if obj:
                if obj.name not in target_col.objects:
                    target_col.objects.link(obj)
                    
    return {"loaded": [getattr(item, "name", str(item)) for item in loaded if item is not None]}


def install_addon(params: dict[str, Any]) -> dict[str, Any]:
    addon_path = params["addon_path"]
    bpy.ops.preferences.addon_install(filepath=addon_path)
    module_name = params.get("module_name") or os.path.splitext(os.path.basename(addon_path))[0]
    bpy.ops.preferences.addon_enable(module=module_name)
    return {"module_name": module_name, "status": "enabled"}


def create_three_point_lighting(params: dict[str, Any]) -> dict[str, Any]:
    target_name = params.get("target_object")
    if target_name:
        target_obj = _object(target_name)
        target_loc = target_obj.location
    else:
        target_loc = Vector((0.0, 0.0, 0.0))
        if bpy.context.active_object:
            target_loc = bpy.context.active_object.location
            
    distance = params.get("distance", 5.0)
    
    key_pos = target_loc + Vector((-0.7 * distance, -0.7 * distance, 0.6 * distance))
    key_data = bpy.data.lights.new(name="Key_Light", type="AREA")
    key_data.energy = params.get("key_energy", 800.0)
    key_obj = bpy.data.objects.new(name="Key_Light", object_data=key_data)
    bpy.context.collection.objects.link(key_obj)
    key_obj.location = key_pos
    dir_key = target_loc - key_obj.location
    key_obj.rotation_euler = dir_key.to_track_quat("-Z", "Y").to_euler()
    
    fill_pos = target_loc + Vector((0.8 * distance, -0.6 * distance, 0.3 * distance))
    fill_data = bpy.data.lights.new(name="Fill_Light", type="AREA")
    fill_data.energy = params.get("fill_energy", 250.0)
    fill_obj = bpy.data.objects.new(name="Fill_Light", object_data=fill_data)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = fill_pos
    dir_fill = target_loc - fill_obj.location
    fill_obj.rotation_euler = dir_fill.to_track_quat("-Z", "Y").to_euler()
    
    rim_pos = target_loc + Vector((0.0, 0.9 * distance, 0.8 * distance))
    rim_data = bpy.data.lights.new(name="Rim_Light", type="SPOT" if distance < 8 else "SUN")
    rim_data.energy = params.get("rim_energy", 450.0)
    rim_obj = bpy.data.objects.new(name="Rim_Light", object_data=rim_data)
    bpy.context.collection.objects.link(rim_obj)
    rim_obj.location = rim_pos
    dir_rim = target_loc - rim_obj.location
    rim_obj.rotation_euler = dir_rim.to_track_quat("-Z", "Y").to_euler()
    
    return {
        "key_light": key_obj.name,
        "fill_light": fill_obj.name,
        "rim_light": rim_obj.name
    }


def create_hdri_lighting(params: dict[str, Any]) -> dict[str, Any]:
    scene = bpy.context.scene
    scene.use_nodes = True
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    
    output = nodes.new("ShaderNodeOutputWorld")
    bg = nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = params.get("strength", 1.0)
    
    env = nodes.new("ShaderNodeTexEnvironment")
    try:
        env.image = bpy.data.images.load(params["hdri_path"])
    except Exception as e:
        raise CommandError("HDRILoadFailed", f"Failed to load HDRI file: {str(e)}")
        
    mapping = nodes.new("ShaderNodeMapping")
    rot = params.get("rotation", 0.0)
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, rot)
    coord = nodes.new("ShaderNodeTexCoord")
    
    links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], bg.inputs["Color"])
    links.new(bg.outputs["Background"], output.inputs["Surface"])
    
    return {"hdri_path": params["hdri_path"], "strength": bg.inputs["Strength"].default_value}


def create_rotation_animation(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("object_name") or params.get("name")
    obj = _object(name)
    sf = int(params["start_frame"])
    ef = int(params["end_frame"])
    axis = params.get("axis", "Z").upper()
    revolutions = float(params.get("revolutions", 1.0))
    interpolation = params.get("interpolation", "LINEAR").upper()
    
    axis_idx = {"X": 0, "Y": 1, "Z": 2}[axis]
    
    bpy.context.scene.frame_set(sf)
    rot = list(obj.rotation_euler)
    obj.keyframe_insert(data_path="rotation_euler", index=axis_idx, frame=sf)
    
    bpy.context.scene.frame_set(ef)
    rot[axis_idx] += revolutions * 2.0 * math.pi
    obj.rotation_euler = rot
    obj.keyframe_insert(data_path="rotation_euler", index=axis_idx, frame=ef)
    
    for fc in _get_fcurves(obj):
        if fc.data_path == "rotation_euler" and fc.array_index == axis_idx:
            for kp in fc.keyframe_points:
                if kp.co.x in (sf, ef):
                    kp.interpolation = interpolation
    return {"object_name": obj.name, "start_frame": sf, "end_frame": ef}


def create_path_animation(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("object_name") or params.get("name")
    obj = _object(name)
    path = _object(params["path_name"])
    sf = int(params["start_frame"])
    ef = int(params["end_frame"])
    
    constraint = obj.constraints.new("FOLLOW_PATH")
    constraint.target = path
    constraint.use_fixed_location = bool(params.get("use_fixed_location", False))
    constraint.use_curve_follow = bool(params.get("follow_curve", True))
    
    if constraint.use_fixed_location:
        constraint.offset_factor = 0.0
        constraint.keyframe_insert(data_path="offset_factor", frame=sf)
        constraint.offset_factor = 1.0
        constraint.keyframe_insert(data_path="offset_factor", frame=ef)
    else:
        constraint.offset = 0.0
        constraint.keyframe_insert(data_path="offset", frame=sf)
        constraint.offset = -100.0
        constraint.keyframe_insert(data_path="offset", frame=ef)
        
    return {"object_name": obj.name, "constraint_name": constraint.name}


def set_fps(params: dict[str, Any]) -> dict[str, Any]:
    scene = bpy.context.scene
    scene.render.fps = int(params["fps"])
    scene.render.fps_base = float(params.get("fps_base", 1.0))
    return {"fps": scene.render.fps, "fps_base": scene.render.fps_base}


def bake_animation(params: dict[str, Any]) -> dict[str, Any]:
    sf = int(params["start_frame"])
    ef = int(params["end_frame"])
    step = int(params.get("step", 1))
    
    names = params.get("object_names")
    if names:
        bpy.ops.object.select_all(action='DESELECT')
        for name in names:
            _object(name).select_set(True)
            
    bpy.ops.nla.bake(
        frame_start=sf,
        frame_end=ef,
        step=step,
        only_selected=True if names else False,
        visual_keying=bool(params.get("visual_keying", True)),
        clear_constraints=bool(params.get("clear_constraints", False)),
        clear_parents=bool(params.get("clear_parents", False)),
        bake_types=set(params.get("bake_types", ["OBJECT"]))
    )
    return {"baked": True, "start_frame": sf, "end_frame": ef}


def set_interpolation(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("object_name") or params.get("name")
    obj = _object(name)
    interpolation = params["interpolation"].upper()
    data_path = params.get("data_path")
    frame = params.get("frame")
    
    if not obj.animation_data or not obj.animation_data.action:
        raise CommandError("NoAnimationData", f"Object '{obj.name}' has no active action/keyframes.")
        
    action = obj.animation_data.action
    count = 0
    for fc in action.fcurves:
        if data_path and fc.data_path != data_path:
            continue
        for kp in fc.keyframe_points:
            if frame is not None and abs(kp.co.x - frame) > 0.01:
                continue
            kp.interpolation = interpolation
            count += 1
    return {"object_name": obj.name, "updated_keyframes_count": count, "interpolation": interpolation}


def setup_advanced_pbr_material(params: dict[str, Any]) -> dict[str, Any]:
    material_name = params["material_name"]
    material = bpy.data.materials.get(material_name) or bpy.data.materials.new(material_name)
    material.use_nodes = True
    
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    
    tex_coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])
    
    scale = params.get("scale", (1.0, 1.0, 1.0))
    rotation = params.get("rotation", (0.0, 0.0, 0.0))
    translation = params.get("translation", (0.0, 0.0, 0.0))
    
    mapping.inputs["Scale"].default_value = scale
    mapping.inputs["Rotation"].default_value = rotation
    mapping.inputs["Location"].default_value = translation
    
    blend = params.get("blend", 0.2)
    color_tint = params.get("color_tint")
    
    def create_map(filepath, socket_name, colorspace="sRGB", is_normal=False):
        if not filepath:
            return None
        tex_node = nodes.new("ShaderNodeTexImage")
        try:
            tex_node.image = bpy.data.images.load(filepath)
        except Exception as e:
            raise CommandError("TextureLoadFailed", f"Failed to load texture {filepath}: {str(e)}")
        
        tex_node.projection = "BOX"
        tex_node.projection_blend = blend
        tex_node.image.colorspace_settings.name = colorspace
        links.new(mapping.outputs["Vector"], tex_node.inputs["Vector"])
        
        if is_normal:
            normal_map_node = nodes.new("ShaderNodeNormalMap")
            normal_map_node.inputs["Strength"].default_value = params.get("normal_strength", 1.0)
            links.new(tex_node.outputs["Color"], normal_map_node.inputs["Color"])
            links.new(normal_map_node.outputs["Normal"], bsdf.inputs[socket_name])
        else:
            if socket_name == "Base Color" and color_tint:
                mix = nodes.new("ShaderNodeMix")
                mix.data_type = 'RGBA'
                mix.blend_type = 'MULTIPLY'
                mix.inputs["Factor"].default_value = 1.0
                if "A" in mix.inputs:
                    links.new(tex_node.outputs["Color"], mix.inputs["A"])
                    mix.inputs["B"].default_value = _color(color_tint)
                else:
                    links.new(tex_node.outputs["Color"], mix.inputs[6])
                    mix.inputs[7].default_value = _color(color_tint)
                links.new(mix.outputs["Result"] if "Result" in mix.outputs else mix.outputs[2], bsdf.inputs[socket_name])
            else:
                links.new(tex_node.outputs["Color"], bsdf.inputs[socket_name])
        return tex_node

    create_map(params.get("diffuse_map"), "Base Color", "sRGB")
    create_map(params.get("roughness_map"), "Roughness", "Non-Color")
    create_map(params.get("metallic_map"), "Metallic", "Non-Color")
    create_map(params.get("normal_map"), "Normal", "Non-Color", is_normal=True)
    
    if not params.get("metallic_map") and "metallic" in params:
        bsdf.inputs["Metallic"].default_value = float(params["metallic"])
    if not params.get("roughness_map") and "roughness" in params:
        bsdf.inputs["Roughness"].default_value = float(params["roughness"])
        
    return {"material_name": material.name, "nodes_created": len(nodes)}


def setup_studio_backdrop_and_lighting(params: dict[str, Any]) -> dict[str, Any]:
    backdrop_name = params.get("backdrop_name", "Studio_Backdrop")
    backdrop_size = params.get("backdrop_size", 20.0)
    
    if backdrop_name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[backdrop_name], do_unlink=True)
        
    mesh = bpy.data.meshes.new(backdrop_name)
    s = backdrop_size
    verts = [
        (-s, -s, 0.0), (s, -s, 0.0), (s, s, 0.0), (-s, s, 0.0),
        (-s, s, s), (s, s, s)
    ]
    faces = [
        (0, 1, 2, 3),
        (3, 2, 5, 4)
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    
    backdrop_obj = bpy.data.objects.new(backdrop_name, mesh)
    bpy.context.collection.objects.link(backdrop_obj)
    
    bev_mod = backdrop_obj.modifiers.new("Curve_Bevel", "BEVEL")
    bev_mod.width = params.get("backdrop_curve_radius", 4.0)
    bev_mod.segments = 16
    bev_mod.limit_method = "ANGLE"
    bev_mod.angle_limit = math.radians(45.0)
    
    sub_mod = backdrop_obj.modifiers.new("Curve_Subdiv", "SUBSURF")
    sub_mod.levels = 2
    
    for poly in mesh.polygons:
        poly.use_smooth = True
        
    mat_name = f"Mat_{backdrop_name}"
    backdrop_mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    backdrop_mat.use_nodes = True
    bsdf = backdrop_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        color = params.get("backdrop_color", "#e2e2e2")
        bsdf.inputs["Base Color"].default_value = _color(color)
        bsdf.inputs["Roughness"].default_value = 0.9
        if "Specular IOR Level" in bsdf.inputs:
            bsdf.inputs["Specular IOR Level"].default_value = 0.1
        elif "Specular" in bsdf.inputs:
            bsdf.inputs["Specular"].default_value = 0.1
            
    backdrop_obj.data.materials.append(backdrop_mat)
    
    for name in ["Studio_Key", "Studio_Fill", "Studio_Rim"]:
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
            
    target_name = params.get("target_object")
    target_loc = Vector((0.0, 0.0, 0.0))
    if target_name:
        try:
            target_loc = Vector(_object(target_name).location)
        except Exception:
            pass
            
    light_dist = params.get("light_distance", 8.0)
    
    key_data = bpy.data.lights.new(name="Studio_Key", type="AREA")
    key_data.shape = "RECTANGLE"
    key_data.size = params.get("key_size", 4.0)
    key_data.size_y = params.get("key_size_y", 3.0)
    key_data.energy = params.get("key_energy", 1200.0)
    key_obj = bpy.data.objects.new(name="Studio_Key", object_data=key_data)
    bpy.context.collection.objects.link(key_obj)
    key_obj.location = target_loc + Vector((-0.8 * light_dist, -0.6 * light_dist, 0.7 * light_dist))
    key_obj.rotation_euler = (target_loc - key_obj.location).to_track_quat("-Z", "Y").to_euler()
    
    fill_data = bpy.data.lights.new(name="Studio_Fill", type="AREA")
    fill_data.shape = "SQUARE"
    fill_data.size = params.get("fill_size", 5.0)
    fill_data.energy = params.get("fill_energy", 400.0)
    fill_obj = bpy.data.objects.new(name="Studio_Fill", object_data=fill_data)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = target_loc + Vector((0.8 * light_dist, -0.5 * light_dist, 0.4 * light_dist))
    fill_obj.rotation_euler = (target_loc - fill_obj.location).to_track_quat("-Z", "Y").to_euler()
    
    rim_data = bpy.data.lights.new(name="Studio_Rim", type="AREA")
    rim_data.shape = "SQUARE"
    rim_data.size = params.get("rim_size", 3.0)
    rim_data.energy = params.get("rim_energy", 800.0)
    rim_obj = bpy.data.objects.new(name="Studio_Rim", object_data=rim_data)
    bpy.context.collection.objects.link(rim_obj)
    rim_obj.location = target_loc + Vector((0.0, 0.9 * light_dist, 0.8 * light_dist))
    rim_obj.rotation_euler = (target_loc - rim_obj.location).to_track_quat("-Z", "Y").to_euler()
    
    scene = bpy.context.scene
    cam_obj = None
    camera_name = params.get("camera_name")
    if camera_name:
        cam_obj = _object(camera_name)
    else:
        cam_obj = scene.camera
        
    if not cam_obj:
        cam_data = bpy.data.cameras.new("Studio_Camera")
        cam_obj = bpy.data.objects.new("Studio_Camera", cam_data)
        bpy.context.collection.objects.link(cam_obj)
        scene.camera = cam_obj
        cam_obj.location = target_loc + Vector((0.0, -1.2 * light_dist, 0.4 * light_dist))
        track_mod = cam_obj.constraints.new("TRACK_TO")
        if target_name:
            track_mod.target = _object(target_name)
        track_mod.track_axis = "TRACK_NEGATIVE_Z"
        track_mod.up_axis = "UP_Y"
        
    if cam_obj and cam_obj.type == 'CAMERA':
        cam_obj.data.dof.use_dof = True
        if target_name:
            cam_obj.data.dof.focus_object = _object(target_name)
        else:
            cam_obj.data.dof.focus_distance = (cam_obj.location - target_loc).length
        cam_obj.data.dof.aperture_fstop = params.get("aperture_fstop", 2.8)
        
    scene.view_settings.view_transform = params.get("view_transform", "AgX" if hasattr(scene.view_settings, "view_transform") and "AgX" in bpy.types.ColorManagedViewSettings.bl_rna.properties["view_transform"].enum_items else "Filmic")
    scene.view_settings.look = params.get("look", "Medium High Contrast")
    
    return {
        "backdrop": backdrop_obj.name,
        "key_light": key_obj.name,
        "fill_light": fill_obj.name,
        "rim_light": rim_obj.name,
        "dof_enabled": True
    }


def polish_topology(params: dict[str, Any]) -> dict[str, Any]:
    names = params.get("objects")
    if not names:
        names = [obj.name for obj in bpy.context.selected_objects if obj.type == 'MESH']
        
    if not names:
        raise CommandError("NoObjectsSelected", "Provide objects list or select at least one mesh object.")
        
    polished_count = 0
    for name in names:
        obj = _object(name)
        if obj.type != 'MESH':
            continue
            
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
        
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        
        dist = params.get("merge_distance", 0.0001)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
        
        loose_verts = [v for v in bm.verts if not v.link_edges]
        bmesh.ops.delete(bm, geom=loose_verts, context='VERTS')
        
        loose_edges = [e for e in bm.edges if not e.link_faces]
        if loose_edges and params.get("remove_loose_edges", True):
            bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')
            
        bmesh.update_edit_mesh(obj.data)
        bpy.ops.object.mode_set(mode='OBJECT')
        
        has_custom = False
        if hasattr(obj.data, "has_custom_normals"):
            has_custom = obj.data.has_custom_normals
        elif hasattr(obj.data, "has_custom_split_normals"):
            has_custom = obj.data.has_custom_split_normals
            
        if has_custom:
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
            
        for poly in obj.data.polygons:
            poly.use_smooth = True
            
        mod_name = "MCP_Weighted_Normals"
        if mod_name in obj.modifiers:
            obj.modifiers.remove(obj.modifiers[mod_name])
        wn_mod = obj.modifiers.new(name=mod_name, type='WEIGHTED_NORMAL')
        wn_mod.keep_sharp = params.get("keep_sharp", True)
        
        if hasattr(obj.data, "use_auto_smooth"):
            obj.data.use_auto_smooth = True
            obj.data.auto_smooth_angle = math.radians(params.get("auto_smooth_angle", 30.0))
        elif hasattr(bpy.ops.object, "shade_smooth_by_angle"):
            # Blender 4.2+ / 5.1+ operator
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(params.get("auto_smooth_angle", 30.0)))
        else:
            # Fallback if SMOOTH_BY_ANGLE modifier exists (Blender 4.1)
            if "Smooth by Angle" not in obj.modifiers:
                try:
                    sba_mod = obj.modifiers.new("Smooth by Angle", "SMOOTH_BY_ANGLE")
                    sba_mod.angle = math.radians(params.get("auto_smooth_angle", 30.0))
                    bpy.ops.object.modifier_move_to_index(modifier=sba_mod.name, index=0)
                except Exception:
                    pass
                
        polished_count += 1
        
    return {"polished_count": polished_count, "objects": names}


def setup_subdivision_modeling(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    if obj.type != 'MESH':
        raise CommandError("InvalidObjectType", f"Object '{obj.name}' is not a mesh.")
        
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    
    angle_limit = math.radians(params.get("angle_limit", 40.0))
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    
    crease_layer = None
    if hasattr(bm.edges.layers, "crease"):
        crease_layer = bm.edges.layers.crease.verify()
    else:
        crease_layer = bm.edges.layers.float.get("crease_edge") or bm.edges.layers.float.new("crease_edge")
        
    for edge in bm.edges:
        edge[crease_layer] = 0.0
        
    sharp_count = 0
    for edge in bm.edges:
        if edge.is_boundary:
            edge[crease_layer] = 1.0
            sharp_count += 1
        elif len(edge.link_faces) == 2:
            f1, f2 = edge.link_faces
            angle = f1.normal.angle(f2.normal)
            if angle >= angle_limit:
                edge[crease_layer] = float(params.get("crease_weight", 1.0))
                sharp_count += 1
                
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')
    
    mod_name = "MCP_Subdivision"
    if mod_name in obj.modifiers:
        obj.modifiers.remove(obj.modifiers[mod_name])
    sub_mod = obj.modifiers.new(name=mod_name, type='SUBSURF')
    sub_mod.levels = int(params.get("levels", 2))
    sub_mod.render_levels = int(params.get("render_levels", 3))
    sub_mod.boundary_smooth = 'ALL'
    
    return {
        "object_name": obj.name,
        "sharp_edges_creased": sharp_count,
        "subdivision_levels": sub_mod.levels
    }


def remesh_for_sculpting(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    if obj.type != 'MESH':
        raise CommandError("InvalidObjectType", f"Object '{obj.name}' is not a mesh.")
        
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    
    remesh_type = params.get("remesh_type", "VOXEL").upper()
    
    if remesh_type == "VOXEL":
        voxel_size = params.get("voxel_size", 0.05)
        obj.data.remesh_voxel_size = voxel_size
        obj.data.remesh_mode = 'VOXEL'
        obj.data.use_remesh_fix_poles = True
        
        bpy.ops.object.voxel_remesh()
        result_voxels = voxel_size
    else:
        target_faces = int(params.get("target_faces", 3000))
        try:
            bpy.ops.object.quadriflow_remesh(
                target_faces=target_faces,
                use_mesh_symmetry=params.get("use_symmetry", True),
                preserve_sharp=params.get("preserve_sharp", True)
            )
            result_voxels = target_faces
        except Exception as e:
            raise CommandError("QuadriflowFailed", f"Quadriflow remesh operator failed: {str(e)}")
            
    return {
        "object_name": obj.name,
        "remesh_type": remesh_type,
        "parameter_value": result_voxels
    }


def set_renderer_effects(params: dict[str, Any]) -> dict[str, Any]:
    scene = bpy.context.scene
    version = bpy.app.version
    
    bloom = params.get("bloom", True)
    ao = params.get("ambient_occlusion", True)
    ssr = params.get("screen_space_reflections", True)
    raytracing = params.get("raytracing", ssr)
    
    results = {}
    
    if scene.render.engine not in {'EEVEE', 'BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'}:
        # Force EEVEE for realtime effects
        scene.render.engine = 'BLENDER_EEVEE' if hasattr(bpy.types, "RenderSettings") and version < (4, 2) else 'BLENDER_EEVEE_NEXT'
        if not hasattr(scene.render, "engine") or scene.render.engine not in {'EEVEE', 'BLENDER_EEVEE_NEXT'}:
            for engine in ['BLENDER_EEVEE_NEXT', 'EEVEE', 'BLENDER_EEVEE']:
                try:
                    scene.render.engine = engine
                    break
                except Exception:
                    pass

    engine = scene.render.engine
    results["engine"] = engine
    
    if version >= (4, 2, 0):
        if hasattr(scene, "eevee"):
            scene.eevee.use_gtao = ao
            scene.eevee.use_raytracing = raytracing
            results["ambient_occlusion"] = scene.eevee.use_gtao
            results["raytracing"] = scene.eevee.use_raytracing
            
            if bloom:
                try:
                    scene.use_nodes = True
                    tree = scene.node_tree
                    glare_node = next((n for n in tree.nodes if n.type == 'GLARE'), None)
                    if not glare_node:
                        glare_node = tree.nodes.new('CompositorNodeGlare')
                        glare_node.glare_type = 'BLOOM'
                        glare_node.quality = 'MEDIUM'
                        
                        rl_node = next((n for n in tree.nodes if n.type == 'R_LAYERS'), None)
                        comp_node = next((n for n in tree.nodes if n.type == 'COMPOSITE'), None)
                        if rl_node and comp_node:
                            tree.links.new(rl_node.outputs['Image'], glare_node.inputs['Image'])
                            tree.links.new(glare_node.outputs['Image'], comp_node.inputs['Image'])
                    results["bloom"] = "Enabled via Compositor"
                except Exception as exc:
                    results["bloom"] = f"Compositor configuration failed: {str(exc)}"
            else:
                results["bloom"] = "Disabled"
    else:
        if hasattr(scene, "eevee"):
            if hasattr(scene.eevee, "use_bloom"):
                scene.eevee.use_bloom = bloom
                results["bloom"] = scene.eevee.use_bloom
            if hasattr(scene.eevee, "use_gtao"):
                scene.eevee.use_gtao = ao
                results["ambient_occlusion"] = scene.eevee.use_gtao
            if hasattr(scene.eevee, "use_ssr"):
                scene.eevee.use_ssr = ssr
                results["screen_space_reflections"] = scene.eevee.use_ssr
                
    return results


def render_viewport_to_base64(params: dict[str, Any]) -> dict[str, Any]:
    import base64
    import tempfile
    
    temp_fd, temp_path = tempfile.mkstemp(suffix=".png")
    os.close(temp_fd)
    
    scene = bpy.context.scene
    orig_path = scene.render.filepath
    orig_format = scene.render.image_settings.file_format
    
    try:
        scene.render.filepath = temp_path
        scene.render.image_settings.file_format = 'PNG'
        
        # Render OpenGL viewport (very fast)
        bpy.ops.render.opengl(write_still=True, view_context=True)
        
        with open(temp_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
        return {
            "success": True,
            "image_base64": f"data:image/png;base64,{encoded_string}",
            "format": "PNG"
        }
    finally:
        scene.render.filepath = orig_path
        scene.render.image_settings.file_format = orig_format
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def create_character_skeleton(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name", "Skeleton")
    skeleton_type = params.get("skeleton_type", "HUMANOID").upper()
    
    arm_data = bpy.data.armatures.new(f"{name}_Data")
    arm_obj = bpy.data.objects.new(name, arm_data)
    bpy.context.collection.objects.link(arm_obj)
    
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode='EDIT')
    
    bones_created = []
    
    if skeleton_type == "HUMANOID":
        # Basic skeleton hierarchy
        hips = arm_data.edit_bones.new("Hips")
        hips.head = (0.0, 0.0, 1.0)
        hips.tail = (0.0, 0.0, 1.2)
        bones_created.append("Hips")
        
        spine = arm_data.edit_bones.new("Spine")
        spine.head = (0.0, 0.0, 1.2)
        spine.tail = (0.0, 0.0, 1.5)
        spine.parent = hips
        bones_created.append("Spine")
        
        neck = arm_data.edit_bones.new("Neck")
        neck.head = (0.0, 0.0, 1.5)
        neck.tail = (0.0, 0.0, 1.6)
        neck.parent = spine
        bones_created.append("Neck")
        
        head = arm_data.edit_bones.new("Head")
        head.head = (0.0, 0.0, 1.6)
        head.tail = (0.0, 0.0, 1.85)
        head.parent = neck
        bones_created.append("Head")
        
        leg_l = arm_data.edit_bones.new("Leg.L")
        leg_l.head = (0.15, 0.0, 1.0)
        leg_l.tail = (0.15, 0.0, 0.5)
        leg_l.parent = hips
        bones_created.append("Leg.L")
        
        foot_l = arm_data.edit_bones.new("Foot.L")
        foot_l.head = (0.15, 0.0, 0.5)
        foot_l.tail = (0.15, 0.2, 0.0)
        foot_l.parent = leg_l
        bones_created.append("Foot.L")
        
        leg_r = arm_data.edit_bones.new("Leg.R")
        leg_r.head = (-0.15, 0.0, 1.0)
        leg_r.tail = (-0.15, 0.0, 0.5)
        leg_r.parent = hips
        bones_created.append("Leg.R")
        
        foot_r = arm_data.edit_bones.new("Foot.R")
        foot_r.head = (-0.15, 0.0, 0.5)
        foot_r.tail = (-0.15, 0.2, 0.0)
        foot_r.parent = leg_r
        bones_created.append("Foot.R")
        
        arm_l = arm_data.edit_bones.new("Arm.L")
        arm_l.head = (0.2, 0.0, 1.45)
        arm_l.tail = (0.5, 0.0, 1.2)
        arm_l.parent = spine
        bones_created.append("Arm.L")
        
        hand_l = arm_data.edit_bones.new("Hand.L")
        hand_l.head = (0.5, 0.0, 1.2)
        hand_l.tail = (0.6, 0.0, 1.1)
        hand_l.parent = arm_l
        bones_created.append("Hand.L")
        
        arm_r = arm_data.edit_bones.new("Arm.R")
        arm_r.head = (-0.2, 0.0, 1.45)
        arm_r.tail = (-0.5, 0.0, 1.2)
        arm_r.parent = spine
        bones_created.append("Arm.R")
        
        hand_r = arm_data.edit_bones.new("Hand.R")
        hand_r.head = (-0.5, 0.0, 1.2)
        hand_r.tail = (-0.6, 0.0, 1.1)
        hand_r.parent = arm_r
        bones_created.append("Hand.R")
    else:
        root = arm_data.edit_bones.new("Root")
        root.head = (0.0, 0.0, 0.0)
        root.tail = (0.0, 0.0, 1.0)
        bones_created.append("Root")
        
    bpy.ops.object.mode_set(mode='OBJECT')
    
    return {
        "armature_name": arm_obj.name,
        "skeleton_type": skeleton_type,
        "bones_created": bones_created
    }


def bind_mesh_to_armature(params: dict[str, Any]) -> dict[str, Any]:
    mesh_obj = _object(params["mesh_name"])
    arm_obj = _object(params["armature_name"])
    
    if mesh_obj.type != 'MESH':
        raise CommandError("InvalidObjectType", f"Object '{mesh_obj.name}' is not a mesh.")
    if arm_obj.type != 'ARMATURE':
        raise CommandError("InvalidObjectType", f"Object '{arm_obj.name}' is not an armature.")
        
    bpy.ops.object.select_all(action='DESELECT')
    mesh_obj.select_set(True)
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj
    
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    
    return {
        "mesh_name": mesh_obj.name,
        "armature_name": arm_obj.name,
        "status": "Successfully bound with Automatic Weights"
    }


def pose_bone(params: dict[str, Any]) -> dict[str, Any]:
    arm_obj = _object(params["armature_name"])
    if arm_obj.type != 'ARMATURE':
        raise CommandError("InvalidObjectType", f"Object '{arm_obj.name}' is not an armature.")
        
    bone_name = params["bone_name"]
    bone = arm_obj.pose.bones.get(bone_name)
    if bone is None:
        raise CommandError("BoneNotFound", f"Bone '{bone_name}' does not exist in armature '{arm_obj.name}'.")
        
    rotation = params.get("rotation")
    location = params.get("location")
    scale = params.get("scale")
    
    if rotation is not None:
        bone.rotation_mode = 'XYZ'
        bone.rotation_euler = (
            math.radians(rotation[0]),
            math.radians(rotation[1]),
            math.radians(rotation[2])
        )
        
    if location is not None:
        bone.location = (location[0], location[1], location[2])
        
    if scale is not None:
        bone.scale = (scale[0], scale[1], scale[2])
        
    bpy.context.view_layer.update()
    
    return {
        "armature_name": arm_obj.name,
        "bone_name": bone_name,
        "rotation_euler": list(bone.rotation_euler) if rotation else None,
        "location": list(bone.location) if location else None,
        "scale": list(bone.scale) if scale else None
    }


def apply_displacement_map(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    if obj.type != 'MESH':
        raise CommandError("InvalidObjectType", f"Object '{obj.name}' is not a mesh.")
        
    texture_type = params.get("texture_type", "CLOUDS").upper()
    strength = float(params.get("strength", 0.5))
    mid_level = float(params.get("mid_level", 0.5))
    
    tex_name = f"DisplaceTex_{obj.name}"
    if tex_name in bpy.data.textures:
        tex = bpy.data.textures[tex_name]
    else:
        tex = bpy.data.textures.new(name=tex_name, type=texture_type)
        
    mod_name = "MCP_Displace"
    if mod_name in obj.modifiers:
        mod = obj.modifiers[mod_name]
    else:
        mod = obj.modifiers.new(name=mod_name, type='DISPLACE')
        
    mod.texture = tex
    mod.strength = strength
    mod.mid_level = mid_level
    
    return {
        "object_name": obj.name,
        "modifier_name": mod.name,
        "texture_type": texture_type,
        "strength": strength
    }


def apply_animation_preset(params: dict[str, Any]) -> dict[str, Any]:
    obj = _object(params["object_name"])
    preset_type = params.get("preset_type", "BOUNCE").upper()
    start_frame = int(params.get("start_frame", 1))
    end_frame = int(params.get("end_frame", 100))
    speed = float(params.get("speed", 1.0))
    intensity = float(params.get("intensity", 1.0))
    
    if obj.animation_data and obj.animation_data.action:
        old_action = obj.animation_data.action
        obj.animation_data.action = bpy.data.actions.new(name=f"{obj.name}_PresetAction")
        if old_action.users == 0:
            bpy.data.actions.remove(old_action)
        
    if preset_type == "BOUNCE":
        base_z = obj.location.z
        for frame in range(start_frame, end_frame + 1):
            bpy.context.scene.frame_set(frame)
            t = (frame - start_frame) * 0.1 * speed
            obj.location.z = base_z + abs(math.sin(t)) * intensity
            obj.keyframe_insert(data_path="location", index=2)
            
    elif preset_type == "WAVE":
        orig_rot_y = obj.rotation_euler.y
        for frame in range(start_frame, end_frame + 1):
            bpy.context.scene.frame_set(frame)
            t = (frame - start_frame) * 0.15 * speed
            obj.rotation_euler.y = orig_rot_y + math.sin(t) * math.radians(15.0) * intensity
            obj.keyframe_insert(data_path="rotation_euler", index=1)
            
    elif preset_type == "WALK":
        if obj.type == 'ARMATURE':
            leg_l = obj.pose.bones.get("Leg.L")
            leg_r = obj.pose.bones.get("Leg.R")
            arm_l = obj.pose.bones.get("Arm.L")
            arm_r = obj.pose.bones.get("Arm.R")
            
            for frame in range(start_frame, end_frame + 1):
                bpy.context.scene.frame_set(frame)
                t = (frame - start_frame) * 0.15 * speed
                
                if leg_l:
                    leg_l.rotation_mode = 'XYZ'
                    leg_l.rotation_euler.x = math.sin(t) * math.radians(20.0) * intensity
                    leg_l.keyframe_insert(data_path="rotation_euler", index=0)
                if leg_r:
                    leg_r.rotation_mode = 'XYZ'
                    leg_r.rotation_euler.x = -math.sin(t) * math.radians(20.0) * intensity
                    leg_r.keyframe_insert(data_path="rotation_euler", index=0)
                    
                if arm_l:
                    arm_l.rotation_mode = 'XYZ'
                    arm_l.rotation_euler.x = -math.sin(t) * math.radians(15.0) * intensity
                    arm_l.keyframe_insert(data_path="rotation_euler", index=0)
                if arm_r:
                    arm_r.rotation_mode = 'XYZ'
                    arm_r.rotation_euler.x = math.sin(t) * math.radians(15.0) * intensity
                    arm_r.keyframe_insert(data_path="rotation_euler", index=0)
        else:
            base_y = obj.location.y
            for frame in range(start_frame, end_frame + 1):
                bpy.context.scene.frame_set(frame)
                t = (frame - start_frame) * 0.1 * speed
                obj.location.y = base_y + t * intensity
                obj.location.z = abs(math.sin(t * 2)) * 0.2 * intensity
                obj.keyframe_insert(data_path="location", index=1)
                obj.keyframe_insert(data_path="location", index=2)
                
    else:
        raise CommandError("InvalidPresetType", f"Animation preset '{preset_type}' is not supported.")
        
    return {
        "object_name": obj.name,
        "preset_type": preset_type,
        "frames_keyed": end_frame - start_frame + 1
    }


HANDLERS: dict[str, Handler] = {
    "set_renderer_effects": set_renderer_effects,
    "render_viewport_to_base64": render_viewport_to_base64,
    "create_character_skeleton": create_character_skeleton,
    "bind_mesh_to_armature": bind_mesh_to_armature,
    "pose_bone": pose_bone,
    "apply_displacement_map": apply_displacement_map,
    "apply_animation_preset": apply_animation_preset,

    "create_object": create_object,
    "delete_object": delete_object,
    "duplicate_object": duplicate_object,
    "move_object": move_object,
    "rotate_object": rotate_object,
    "scale_object": scale_object,
    "rename_object": rename_object,
    "list_objects": list_objects,
    "get_object_info": get_object_info,
    "select_object": select_object,
    "join_objects": join_objects,
    "separate_object": separate_object,
    "set_object_visibility": set_object_visibility,
    "parent_object": parent_object,
    "apply_transform": apply_transform,
    "setup_advanced_pbr_material": setup_advanced_pbr_material,
    "setup_studio_backdrop_and_lighting": setup_studio_backdrop_and_lighting,
    "polish_topology": polish_topology,
    "setup_subdivision_modeling": setup_subdivision_modeling,
    "remesh_for_sculpting": remesh_for_sculpting,
    "enter_edit_mode": enter_edit_mode,
    "exit_edit_mode": exit_edit_mode,
    "create_material": create_material,
    "assign_material": assign_material,
    "list_materials": list_materials,
    "delete_material": delete_material,
    "set_material_color": set_material_color,
    "set_material_property": set_material_property,
    "create_emission_material": create_emission_material,
    "create_glass_material": create_glass_material,
    "add_texture": add_texture,
    "setup_pbr_material": setup_pbr_material,
    "enable_nodes": enable_nodes,
    "get_material_info": get_material_info,
    "create_camera": create_camera,
    "create_light": create_light,
    "create_primitive": create_primitive,
    "create_curve_path": create_curve_path,
    "create_pipe_along_path": create_pipe_along_path,
    "boolean_operation": boolean_operation,
    "bevel_edges": bevel_edges,
    "set_origin": set_origin,
    "get_bounding_box": get_bounding_box,
    "snap_to_ground": snap_to_ground,
    "align_objects": align_objects,
    "distribute_objects": distribute_objects,
    "duplicate_along_axis": duplicate_along_axis,
    "create_component_group": create_component_group,
    "set_object_metadata": set_object_metadata,
    "find_objects": find_objects,
    "validate_model": validate_model,
    "import_reference_image": import_reference_image,
    "setup_reference_planes": setup_reference_planes,
    "lock_reference": lock_reference,
    "set_landmark": set_landmark,
    "get_landmarks": get_landmarks,
    "measure_between_landmarks": measure_between_landmarks,
    "align_object_to_landmarks": align_object_to_landmarks,
    "calibrate_reference_scale": calibrate_reference_scale,
    "render_orthographic_view": render_orthographic_view,
    "compare_silhouette_bounds": compare_silhouette_bounds,
    "create_rounded_box": create_rounded_box,
    "create_tapered_cylinder": create_tapered_cylinder,
    "create_capsule_segment": create_capsule_segment,
    "create_panel_seam": create_panel_seam,
    "create_ring_joint": create_ring_joint,
    "create_slot_cut": create_slot_cut,
    "add_screw_array": add_screw_array,
    "add_vent_grille": add_vent_grille,
    "apply_weighted_normals": apply_weighted_normals,
    "add_support_loops": add_support_loops,
    "create_pbr_material": create_pbr_material,
    "create_toon_material": create_toon_material,
    "create_procedural_material": create_procedural_material,
    "add_edge_wear": add_edge_wear,
    "assign_material_by_name": assign_material_by_name,
    "create_decal": create_decal,
    "add_outline_modifier": add_outline_modifier,
    "apply_material_variation": apply_material_variation,
    "validate_scene_quality": validate_scene_quality,
    "create_lowpoly_asset": create_lowpoly_asset,
    "detect_overlaps": detect_overlaps,
    "validate_symmetry": validate_symmetry,
    "check_scale_consistency": check_scale_consistency,
    "generate_quality_report": generate_quality_report,
    "suggest_model_improvements": suggest_model_improvements,
    "execute_python": execute_python,
    "evaluate_expression": evaluate_expression,
    "create_three_point_lighting": create_three_point_lighting,
    "create_hdri_lighting": create_hdri_lighting,
    "set_interpolation": set_interpolation,
    "create_rotation_animation": create_rotation_animation,
    "create_path_animation": create_path_animation,
    "set_fps": set_fps,
    "bake_animation": bake_animation,
    "set_render_engine": set_render_engine,
    "set_render_resolution": set_render_resolution,
    "set_render_output": set_render_output,
    "set_cycles_samples": set_cycles_samples,
    "set_eevee_settings": set_eevee_settings,
    "render_image": render_image,
    "render_animation": render_animation,
    "add_render_pass": add_render_pass,
    "set_color_management": set_color_management,
    "unwrap_uv": unwrap_uv,
    "pack_uvs": pack_uvs,
    "scale_uvs": scale_uvs,
    "select_uv_island": select_uv_island,
    "export_uv_layout": export_uv_layout,
    "add_geometry_nodes_modifier": add_geometry_nodes_modifier,
    "create_node": create_node,
    "connect_nodes": connect_nodes,
    "set_node_input": set_node_input,
    "set_geonode_input": set_geonode_input,
    "list_nodes": list_nodes,
    "install_addon": install_addon,
    "import_file": import_file,
    "export_file": export_file,
    "import_image_as_plane": import_image_as_plane,
    "link_blend_file": link_blend_file,
    "append_blend_file": append_blend_file,
}

for _name in ("select_mesh_elements", "extrude", "loop_cut", "bevel", "subdivide", "merge_vertices", "set_vertex_position", "knife_cut", "inset_faces", "bridge_edge_loops", "flip_normals", "recalculate_normals"):
    HANDLERS[_name] = lambda params, name=_name: _mesh_op(name, params)

for _name in ("get_scene_info", "set_scene_property", "set_unit_system", "set_frame", "set_frame_range", "clear_scene", "list_collections", "create_collection", "move_to_collection", "set_world_color"):
    HANDLERS[_name] = lambda params, name=_name: passthrough_scene(name, params)

for _name in ("set_active_camera", "set_camera_property", "point_camera_at", "camera_from_view", "add_camera_constraint", "set_light_property", "delete_light", "list_lights", "add_modifier", "set_modifier_property", "apply_modifier", "remove_modifier", "list_modifiers", "reorder_modifier", "insert_keyframe", "delete_keyframe", "list_keyframes", "set_render_camera"):
    HANDLERS[_name] = lambda params, name=_name: _generic_object_tool(name, params)

