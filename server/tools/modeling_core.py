"""Universal modeling-core tools for free-form object creation and layout."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .common import ToolModel, build_tools, export_tools, register_toolset

Vector2 = tuple[float, float]
Vector3 = tuple[float, float, float]


class CreatePrimitiveParams(ToolModel):
    """Create a flexible primitive for arbitrary modeling tasks."""

    type: Literal[
        "cube",
        "box",
        "beveled_box",
        "plane",
        "cylinder",
        "cone",
        "sphere",
        "uv_sphere",
        "icosphere",
        "torus",
        "wedge",
        "capsule",
        "pipe",
        "column",
        "panel",
        "slab",
    ] = Field(..., description="Primitive type.")
    name: str | None = Field(None, min_length=1, description="Optional object name.")
    location: Vector3 = Field((0.0, 0.0, 0.0), description="World-space location.")
    rotation: Vector3 = Field((0.0, 0.0, 0.0), description="Euler rotation in radians.")
    size: Vector3 = Field((1.0, 1.0, 1.0), description="XYZ dimensions or bounding size.")
    radius: float | None = Field(None, gt=0.0, description="Radius for rounded primitives.")
    depth: float | None = Field(None, gt=0.0, description="Depth/height override.")
    bevel: float = Field(0.0, ge=0.0, description="Optional bevel amount for hard-surface primitives.")
    segments: int = Field(24, ge=3, le=256, description="Segment count for radial primitives.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Custom semantic metadata.")

    @field_validator("size")
    @classmethod
    def non_zero_size(cls, value: Vector3) -> Vector3:
        """Reject zero dimensions."""
        if any(component == 0 for component in value):
            raise ValueError("size components must be non-zero.")
        return value


class CreateCurvePathParams(ToolModel):
    """Create a curve path from points."""

    name: str = Field(..., min_length=1)
    points: list[Vector3] = Field(..., min_length=2)
    bevel_depth: float = Field(0.0, ge=0.0)
    cyclic: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatePipeAlongPathParams(ToolModel):
    """Create a pipe or tube following a polyline path."""

    name: str = Field(..., min_length=1)
    points: list[Vector3] = Field(..., min_length=2)
    radius: float = Field(..., gt=0.0)
    fill_caps: bool = True
    material_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BooleanOperationParams(ToolModel):
    """Perform a Boolean operation between objects."""

    target: str = Field(..., min_length=1)
    cutter: str = Field(..., min_length=1)
    operation: Literal["UNION", "DIFFERENCE", "INTERSECT"] = "DIFFERENCE"
    apply: bool = True
    keep_cutter: bool = False
    modifier_name: str = "MCP_Boolean"


class BevelEdgesParams(ToolModel):
    """Add or apply a bevel modifier."""

    object_name: str = Field(..., min_length=1)
    width: float = Field(..., gt=0.0)
    segments: int = Field(2, ge=1, le=64)
    affect: Literal["EDGES", "VERTICES"] = "EDGES"
    angle_limit: float | None = Field(None, ge=0.0, le=3.14159)
    apply: bool = False
    modifier_name: str = "MCP_Bevel"


class SetOriginParams(ToolModel):
    """Set object origin/pivot."""

    object_name: str = Field(..., min_length=1)
    mode: Literal["GEOMETRY", "CENTER_OF_MASS", "CURSOR", "WORLD_ORIGIN"] = "GEOMETRY"
    location: Vector3 | None = None


class BoundsParams(ToolModel):
    """Target objects for bounding-box queries."""

    objects: list[str] = Field(..., min_length=1)
    include_children: bool = True


class SnapToGroundParams(ToolModel):
    """Move objects so their lowest bound sits on a ground height."""

    objects: list[str] = Field(..., min_length=1)
    ground_z: float = 0.0
    use_origin: bool = False


class AlignObjectsParams(ToolModel):
    """Align object bounds or origins along one axis."""

    objects: list[str] = Field(..., min_length=2)
    axis: Literal["X", "Y", "Z"] = "Z"
    mode: Literal["MIN", "CENTER", "MAX", "ORIGIN"] = "MIN"
    target: float | None = None


class DistributeObjectsParams(ToolModel):
    """Distribute objects evenly between bounds on one axis."""

    objects: list[str] = Field(..., min_length=2)
    axis: Literal["X", "Y", "Z"] = "X"
    spacing: float | None = Field(None, gt=0.0)
    start: float | None = None
    end: float | None = None

    @model_validator(mode="after")
    def spacing_or_range(self) -> "DistributeObjectsParams":
        """Require spacing or a complete range."""
        if self.spacing is None and (self.start is None or self.end is None):
            raise ValueError("Provide spacing or both start and end.")
        return self


class DuplicateAlongAxisParams(ToolModel):
    """Duplicate an object along an axis or vector."""

    object_name: str = Field(..., min_length=1)
    count: int = Field(..., ge=1, le=1000)
    offset: Vector3 = Field(..., description="Offset between consecutive duplicates.")
    name_prefix: str | None = Field(None, min_length=1)
    linked: bool = False


class CreateComponentGroupParams(ToolModel):
    """Create an empty parent and attach children as editable components."""

    name: str = Field(..., min_length=1)
    children: list[str] = Field(default_factory=list)
    collection: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SetObjectMetadataParams(ToolModel):
    """Attach semantic metadata to one or more objects."""

    objects: list[str] = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(..., min_length=1)
    namespace: str = "mcp"
    merge: bool = True


class FindObjectsParams(ToolModel):
    """Find objects by name, type, material, metadata, or bounds."""

    name_contains: str | None = None
    object_type: str | None = None
    material_name: str | None = None
    metadata: dict[str, Any] | None = None
    within_bounds: tuple[Vector3, Vector3] | None = None
    limit: int = Field(100, ge=1, le=1000)


class ValidateModelParams(ToolModel):
    """Run basic scene/model quality checks."""

    objects: list[str] | None = None
    check_overlaps: bool = True
    check_floating: bool = True
    check_missing_materials: bool = True
    ground_z: float = 0.0
    tolerance: float = Field(0.001, ge=0.0)


class SetupSubdivisionModelingParams(ToolModel):
    """Set up non-destructive subdivision modeling on a mesh."""

    object_name: str = Field(..., min_length=1, description="Object mesh name.")
    levels: int = Field(2, ge=0, le=6, description="Viewport subdivision levels.")
    render_levels: int = Field(3, ge=0, le=6, description="Render subdivision levels.")
    angle_limit: float = Field(40.0, ge=0.0, le=180.0, description="Angle threshold in degrees for edge crease selection.")
    crease_weight: float = Field(1.0, ge=0.0, le=1.0, description="Sharp edge crease weight.")


class RemeshForSculptingParams(ToolModel):
    """Rebuild mesh as clean quads for sculpting."""

    object_name: str = Field(..., min_length=1, description="Object mesh name.")
    remesh_type: Literal["VOXEL", "QUADRIFLOW"] = Field("VOXEL", description="Remesh algorithm.")
    voxel_size: float = Field(0.05, gt=0.0, description="Voxel size in Blender units (for VOXEL mode).")
    target_faces: int = Field(3000, ge=10, le=1000000, description="Target face count (for QUADRIFLOW mode).")
    use_symmetry: bool = Field(True, description="Enable mesh symmetry constraint (for QUADRIFLOW mode).")
    preserve_sharp: bool = Field(True, description="Preserve sharp detailing (for QUADRIFLOW mode).")


_SPECS: list[tuple[str, str, type[BaseModel]]] = [
    ("create_primitive", "Create a flexible modeling primitive.", CreatePrimitiveParams),
    ("create_curve_path", "Create an editable curve path.", CreateCurvePathParams),
    ("create_pipe_along_path", "Create a pipe along a path.", CreatePipeAlongPathParams),
    ("boolean_operation", "Run a Boolean operation between objects.", BooleanOperationParams),
    ("bevel_edges", "Add or apply a bevel modifier.", BevelEdgesParams),
    ("set_origin", "Set object origin/pivot.", SetOriginParams),
    ("get_bounding_box", "Return object bounding boxes.", BoundsParams),
    ("snap_to_ground", "Snap objects to a ground plane.", SnapToGroundParams),
    ("align_objects", "Align multiple objects along an axis.", AlignObjectsParams),
    ("distribute_objects", "Distribute objects evenly.", DistributeObjectsParams),
    ("duplicate_along_axis", "Duplicate an object along a vector.", DuplicateAlongAxisParams),
    ("create_component_group", "Create an editable component group.", CreateComponentGroupParams),
    ("set_object_metadata", "Attach semantic metadata to objects.", SetObjectMetadataParams),
    ("find_objects", "Find objects using semantic and spatial filters.", FindObjectsParams),
    ("validate_model", "Validate model layout and quality.", ValidateModelParams),
    ("setup_subdivision_modeling", "Set up non-destructive subdivision modeling on a mesh.", SetupSubdivisionModelingParams),
    ("remesh_for_sculpting", "Rebuild mesh as clean quads/voxels for sculpting.", RemeshForSculptingParams),
]

TOOLS = build_tools(_SPECS)
export_tools(globals(), TOOLS)


def register_tools(registry: Any) -> Any:
    """Register universal modeling-core tools."""
    return register_toolset(registry, TOOLS)


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
