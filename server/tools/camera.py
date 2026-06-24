"""Camera MCP tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .common import NameParams, ToolModel, build_tools, export_tools, register_toolset

Vector3 = tuple[float, float, float]


class CreateCameraParams(ToolModel):
    """Create a camera."""

    name: str | None = Field(None, min_length=1, description="Optional camera object name.")
    camera_type: Literal["PERSP", "ORTHO", "PANO"] = Field("PERSP", description="Camera projection type.")
    location: Vector3 = Field((0.0, -5.0, 3.0), description="World-space XYZ location.")
    rotation: Vector3 = Field((1.109319, 0.0, 0.0), description="Euler XYZ rotation in radians.")
    focal_length: float | None = Field(None, gt=0.0, description="Lens focal length in millimeters.")
    ortho_scale: float | None = Field(None, gt=0.0, description="Orthographic camera scale.")


class CameraPropertyParams(NameParams):
    """Set a camera property."""

    property_name: str = Field(..., min_length=1, description="Camera data property name.")
    value: Any = Field(..., description="JSON-serializable property value.")


class PointCameraAtParams(NameParams):
    """Aim a camera at an object or coordinate."""

    target_object: str | None = Field(None, min_length=1, description="Object to aim at.")
    target_location: Vector3 | None = Field(None, description="World-space XYZ point to aim at.")
    track_axis: Literal[
        "TRACK_NEGATIVE_Z",
        "TRACK_Z",
        "TRACK_X",
        "TRACK_Y",
        "TRACK_NEGATIVE_X",
        "TRACK_NEGATIVE_Y",
    ] = Field("TRACK_NEGATIVE_Z", description="Tracking axis for the camera constraint math.")
    up_axis: Literal["UP_X", "UP_Y", "UP_Z"] = Field("UP_Y", description="Up axis.")

    @model_validator(mode="after")
    def one_target(self) -> "PointCameraAtParams":
        """Require exactly one target source."""
        if (self.target_object is None) == (self.target_location is None):
            raise ValueError("Provide exactly one of target_object or target_location.")
        return self


class CameraConstraintParams(NameParams):
    """Add a camera constraint."""

    constraint_type: Literal["TRACK_TO", "FOLLOW_PATH", "COPY_ROTATION"] = Field(
        ..., description="Constraint type to add."
    )
    target_name: str = Field(..., min_length=1, description="Constraint target object or path.")
    influence: float = Field(1.0, ge=0.0, le=1.0, description="Constraint influence.")
    options: dict[str, Any] = Field(default_factory=dict, description="Constraint-specific pass-through options.")


_SPECS: list[tuple[str, str, type[BaseModel]]] = [
    ("create_camera", "Create a Blender camera.", CreateCameraParams),
    ("set_active_camera", "Set active render camera.", NameParams),
    ("set_camera_property", "Set camera property.", CameraPropertyParams),
    ("point_camera_at", "Point camera at a target.", PointCameraAtParams),
    ("camera_from_view", "Set camera from viewport.", NameParams),
    ("add_camera_constraint", "Add camera constraint.", CameraConstraintParams),
]

TOOLS = build_tools(_SPECS)
export_tools(globals(), TOOLS)


def register_tools(registry: Any) -> Any:
    """Register camera tools."""
    return register_toolset(registry, TOOLS)


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
