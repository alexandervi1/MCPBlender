"""Reference-image and landmark tools for guided modeling."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .common import ToolModel, build_tools, export_tools, register_toolset

Vector2 = tuple[float, float]
Vector3 = tuple[float, float, float]


class ImportReferenceImageParams(ToolModel):
    """Import an image as a Blender reference object."""

    image_path: str = Field(..., min_length=1)
    name: str | None = Field(None, min_length=1)
    view: Literal["FRONT", "SIDE", "TOP", "BACK", "CUSTOM"] = "FRONT"
    location: Vector3 = (0.0, 0.0, 0.0)
    scale: float = Field(1.0, gt=0.0)
    opacity: float = Field(0.45, ge=0.0, le=1.0)
    locked: bool = True


class SetupReferencePlanesParams(ToolModel):
    """Create front/side/top reference planes from image paths."""

    front: str | None = None
    side: str | None = None
    top: str | None = None
    scale: float = Field(5.0, gt=0.0)
    opacity: float = Field(0.45, ge=0.0, le=1.0)
    collection: str = "References"

    @model_validator(mode="after")
    def at_least_one_reference(self) -> "SetupReferencePlanesParams":
        """Require one image."""
        if not self.front and not self.side and not self.top:
            raise ValueError("Provide at least one of front, side, or top.")
        return self


class LockReferenceParams(ToolModel):
    """Lock or unlock reference objects."""

    objects: list[str] = Field(..., min_length=1)
    locked: bool = True
    hide_select: bool = True


class SetLandmarkParams(ToolModel):
    """Store a named 3D landmark."""

    name: str = Field(..., min_length=1)
    location: Vector3
    target_object: str | None = None
    category: str = "default"
    metadata: dict[str, Any] = Field(default_factory=dict)
    create_empty: bool = True


class GetLandmarksParams(ToolModel):
    """Read stored landmarks."""

    names: list[str] | None = None
    category: str | None = None
    target_object: str | None = None


class MeasureBetweenLandmarksParams(ToolModel):
    """Measure distance between two landmarks."""

    a: str = Field(..., min_length=1)
    b: str = Field(..., min_length=1)


class AlignObjectToLandmarksParams(ToolModel):
    """Move and optionally scale an object between landmarks."""

    object_name: str = Field(..., min_length=1)
    source_landmark: str = Field(..., min_length=1)
    target_landmark: str = Field(..., min_length=1)
    scale_to_distance: tuple[str, str] | None = None


class CalibrateReferenceScaleParams(ToolModel):
    """Scale references using two landmarks and a desired distance."""

    landmark_a: str
    landmark_b: str
    real_distance: float = Field(..., gt=0.0)
    objects: list[str] = Field(default_factory=list)


class RenderOrthographicViewParams(ToolModel):
    """Set or render an orthographic review camera."""

    view: Literal["FRONT", "SIDE", "TOP", "BACK"] = "FRONT"
    camera_name: str = "Reference_Ortho_Camera"
    output_path: str | None = None
    resolution: Vector2 = (1024.0, 1024.0)
    ortho_scale: float = Field(6.0, gt=0.0)
    render: bool = False


class CompareSilhouetteBoundsParams(ToolModel):
    """Compare object bounds against expected reference bounds."""

    objects: list[str] = Field(..., min_length=1)
    expected_min: Vector3
    expected_max: Vector3
    tolerance: float = Field(0.05, ge=0.0)


_SPECS: list[tuple[str, str, type[BaseModel]]] = [
    ("import_reference_image", "Import an image reference into Blender.", ImportReferenceImageParams),
    ("setup_reference_planes", "Create front/side/top reference planes.", SetupReferencePlanesParams),
    ("lock_reference", "Lock or unlock reference objects.", LockReferenceParams),
    ("set_landmark", "Store a modeling landmark.", SetLandmarkParams),
    ("get_landmarks", "List stored modeling landmarks.", GetLandmarksParams),
    ("measure_between_landmarks", "Measure two landmarks.", MeasureBetweenLandmarksParams),
    ("align_object_to_landmarks", "Align an object using landmarks.", AlignObjectToLandmarksParams),
    ("calibrate_reference_scale", "Calibrate references using landmark distance.", CalibrateReferenceScaleParams),
    ("render_orthographic_view", "Create or render an orthographic review view.", RenderOrthographicViewParams),
    ("compare_silhouette_bounds", "Compare combined object bounds against expected bounds.", CompareSilhouetteBoundsParams),
]

TOOLS = build_tools(_SPECS)
export_tools(globals(), TOOLS)


def register_tools(registry: Any) -> Any:
    """Register reference-modeling tools."""
    return register_toolset(registry, TOOLS)


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
