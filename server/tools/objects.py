"""Object and mesh-editing MCP tools for Blender."""

from __future__ import annotations

import inspect
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Vector3 = tuple[float, float, float]


class ToolModel(BaseModel):
    """Base model for public tool input schemas."""

    model_config = ConfigDict(extra="forbid")


class NameModel(ToolModel):
    """Parameters for a single object target."""

    name: str = Field(..., min_length=1)


class CreateObjectParams(ToolModel):
    """Create a mesh primitive with transform data."""

    object_type: Literal[
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
    name: str | None = Field(None, min_length=1)
    location: Vector3 = (0.0, 0.0, 0.0)
    rotation: Vector3 = (0.0, 0.0, 0.0)
    scale: Vector3 = (1.0, 1.0, 1.0)

    @field_validator("scale")
    @classmethod
    def non_zero_scale(cls, value: Vector3) -> Vector3:
        """Reject zero scale components."""
        if any(component == 0 for component in value):
            raise ValueError("Scale components must be non-zero.")
        return value


class DeleteObjectParams(ToolModel):
    """Delete one object, many objects, or selected objects."""

    name: str | None = None
    names: list[str] | None = None
    selected: bool = False


class DuplicateObjectParams(NameModel):
    """Duplicate an object with an offset."""

    new_name: str | None = None
    offset: Vector3 = (0.0, 0.0, 0.0)


class MoveObjectParams(NameModel):
    """Set or offset object location."""

    location: Vector3 | None = None
    offset: Vector3 | None = None
    relative: bool = False


class RotateObjectParams(NameModel):
    """Set or offset object rotation."""

    rotation: Vector3 | tuple[float, float, float, float]
    mode: Literal["euler", "quaternion", "EULER", "QUATERNION"] = "euler"
    relative: bool = False


class ScaleObjectParams(NameModel):
    """Set or offset object scale."""

    scale: Vector3
    relative: bool = False


class RenameObjectParams(NameModel):
    """Rename an object."""

    new_name: str = Field(..., min_length=1)


class EmptyParams(ToolModel):
    """No parameters."""


class GetObjectInfoParams(NameModel):
    """Return detailed object information."""


class SelectObjectParams(ToolModel):
    """Select or deselect an object."""

    name: str
    selected: bool = True
    active: bool = False


class JoinObjectsParams(ToolModel):
    """Join multiple mesh objects."""

    names: list[str] = Field(..., min_length=2)
    new_name: str | None = None


class SeparateObjectParams(NameModel):
    """Separate a mesh object."""

    method: Literal["loose_parts", "material", "selection", "LOOSE", "MATERIAL", "SELECTED"]


class SetObjectVisibilityParams(NameModel):
    """Set viewport and render visibility."""

    viewport: bool | None = None
    render: bool | None = None


class ParentObjectParams(ToolModel):
    """Set parent-child relationship."""

    child: str
    parent: str | None = None
    keep_transform: bool = True


class ApplyTransformParams(NameModel):
    """Apply transform components to object data."""

    location: bool = False
    rotation: bool = False
    scale: bool = True


class EditModeParams(ToolModel):
    """Enter or exit edit mode."""

    name: str | None = None


class SelectMeshElementsParams(NameModel):
    """Select mesh elements by index or mode."""

    element_type: Literal["vertex", "edge", "face", "VERT", "EDGE", "FACE"]
    mode: Literal["indices", "all", "none", "invert"] = "indices"
    indices: list[int] | None = None

    @model_validator(mode="after")
    def validate_indices(self) -> "SelectMeshElementsParams":
        """Require valid indices for index-selection mode."""
        if self.mode == "indices" and not self.indices:
            raise ValueError("indices are required when mode is indices.")
        if self.indices and any(index < 0 for index in self.indices):
            raise ValueError("indices must be non-negative.")
        return self


class ExtrudeParams(NameModel):
    """Extrude selected elements."""

    axis: Vector3 | None = None
    distance: float = 1.0


class LoopCutParams(NameModel):
    """Add loop cuts."""

    edge_index: int = Field(..., ge=0)
    cuts: int = Field(1, ge=1)
    slide: float = 0.0


class BevelParams(NameModel):
    """Bevel selected edges or vertices."""

    width: float = Field(..., gt=0)
    segments: int = Field(1, ge=1)
    affect: Literal["edges", "vertices", "EDGES", "VERTICES"] = "edges"


class SubdivideParams(NameModel):
    """Subdivide selected faces."""

    cuts: int = Field(1, ge=1)


class MergeVerticesParams(NameModel):
    """Merge selected vertices."""

    method: Literal["by_distance", "center", "BY_DISTANCE", "CENTER"]
    distance: float | None = None

    @model_validator(mode="after")
    def validate_distance(self) -> "MergeVerticesParams":
        """Require a non-negative merge distance for distance merging."""
        if self.method in {"by_distance", "BY_DISTANCE"}:
            if self.distance is None:
                raise ValueError("distance is required for by-distance merging.")
            if self.distance < 0:
                raise ValueError("distance must be non-negative.")
        return self


class SetVertexPositionParams(NameModel):
    """Move a vertex by index."""

    index: int = Field(..., ge=0)
    position: Vector3


class KnifeCutParams(NameModel):
    """Cut a mesh with points."""

    points: list[Vector3] = Field(..., min_length=2)


class InsetFacesParams(NameModel):
    """Inset selected faces."""

    thickness: float = Field(..., gt=0)
    depth: float = 0.0


class BridgeEdgeLoopsParams(NameModel):
    """Bridge two explicit edge loops."""

    loop_a: list[int]
    loop_b: list[int]

    @model_validator(mode="after")
    def validate_loops(self) -> "BridgeEdgeLoopsParams":
        """Require two non-empty loops with non-negative edge indices."""
        if not self.loop_a or not self.loop_b:
            raise ValueError("loop_a and loop_b must be non-empty.")
        if any(index < 0 for index in [*self.loop_a, *self.loop_b]):
            raise ValueError("edge-loop indices must be non-negative.")
        return self


class RecalculateNormalsParams(NameModel):
    """Recalculate selected normals."""

    outside: bool = True


@dataclass(frozen=True)
class ToolDefinition:
    """MCP tool metadata."""

    name: str
    description: str
    input_model: type[BaseModel]
    handler: Any

    @property
    def input_schema(self) -> dict[str, Any]:
        """Return JSON Schema for this tool."""
        return self.input_model.model_json_schema()


def _structured_error(error: str, message: str, code: int = 400) -> dict[str, Any]:
    return {"success": False, "error": error, "message": message, "code": code}


async def _send(bridge: Any, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Send a validated tool call through the Blender bridge."""
    for method_name in ("call_tool", "execute_tool", "send_command", "request", "call", "execute"):
        method = getattr(bridge, method_name, None)
        if method is None:
            continue
        result = method(tool_name, params)
        if inspect.isawaitable(result):
            result = await result
        return result
    return _structured_error("BridgeUnavailable", "Bridge object does not expose a supported call method.", 503)


async def _dispatch(
    bridge: Any,
    tool_name: str,
    model: type[BaseModel],
    params: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    raw = dict(params or {})
    raw.update(kwargs)
    try:
        model.model_validate(raw)
    except ValidationError as exc:
        return _structured_error("InvalidParams", exc.errors()[0]["msg"], 400)
    return await _send(bridge, tool_name, raw)


def _register_tool(registry: Any, spec: ToolDefinition) -> None:
    if hasattr(registry, "register_tool"):
        registry.register_tool(spec.name, spec.description, spec.input_schema, spec.handler)
    elif isinstance(registry, MutableMapping):
        registry[spec.name] = spec
    else:
        raise TypeError("registry must expose register_tool or be a mutable mapping")


def _make_tool(tool_name: str, model: type[BaseModel]) -> Any:
    async def tool(bridge: Any, params: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Validate parameters and forward the command to Blender."""
        return await _dispatch(bridge, tool_name, model, params, **kwargs)

    tool.__name__ = tool_name
    return tool


_SPECS: list[tuple[str, str, type[BaseModel]]] = [
    ("create_object", "Create mesh primitives.", CreateObjectParams),
    ("delete_object", "Delete object(s).", DeleteObjectParams),
    ("duplicate_object", "Duplicate an object.", DuplicateObjectParams),
    ("move_object", "Move an object.", MoveObjectParams),
    ("rotate_object", "Rotate an object.", RotateObjectParams),
    ("scale_object", "Scale an object.", ScaleObjectParams),
    ("rename_object", "Rename an object.", RenameObjectParams),
    ("list_objects", "List scene objects.", EmptyParams),
    ("get_object_info", "Get detailed object info.", GetObjectInfoParams),
    ("select_object", "Select or deselect an object.", SelectObjectParams),
    ("join_objects", "Join mesh objects.", JoinObjectsParams),
    ("separate_object", "Separate a mesh.", SeparateObjectParams),
    ("set_object_visibility", "Set object visibility.", SetObjectVisibilityParams),
    ("parent_object", "Set object parent.", ParentObjectParams),
    ("apply_transform", "Apply object transform.", ApplyTransformParams),
    ("enter_edit_mode", "Enter edit mode.", EditModeParams),
    ("exit_edit_mode", "Exit edit mode.", EmptyParams),
    ("select_mesh_elements", "Select vertices, edges, or faces.", SelectMeshElementsParams),
    ("extrude", "Extrude selected elements.", ExtrudeParams),
    ("loop_cut", "Add loop cuts.", LoopCutParams),
    ("bevel", "Bevel mesh elements.", BevelParams),
    ("subdivide", "Subdivide selected faces.", SubdivideParams),
    ("merge_vertices", "Merge vertices.", MergeVerticesParams),
    ("set_vertex_position", "Move a vertex.", SetVertexPositionParams),
    ("knife_cut", "Knife cut mesh geometry.", KnifeCutParams),
    ("inset_faces", "Inset faces.", InsetFacesParams),
    ("bridge_edge_loops", "Bridge edge loops.", BridgeEdgeLoopsParams),
    ("flip_normals", "Flip normals.", NameModel),
    ("recalculate_normals", "Recalculate normals.", RecalculateNormalsParams),
]

TOOLS: dict[str, ToolDefinition] = {}
for _name, _description, _model in _SPECS:
    globals()[_name] = _make_tool(_name, _model)
    TOOLS[_name] = ToolDefinition(_name, _description, _model, globals()[_name])


def register_tools(registry: Any) -> Any:
    """Register object tools with a registry."""
    for spec in TOOLS.values():
        _register_tool(registry, spec)
    return registry


__all__ = ["TOOLS", "ToolDefinition", "register_tools", *TOOLS.keys()]
