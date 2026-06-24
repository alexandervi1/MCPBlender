"""Quality validation and review tools for production-oriented scenes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .common import ToolModel, build_tools, export_tools, register_toolset

Vector3 = tuple[float, float, float]


class ValidateSceneQualityParams(ToolModel):
    """Run a broad quality pass over a scene or object subset."""

    objects: list[str] | None = None
    checks: list[
        Literal[
            "overlaps",
            "floating",
            "missing_materials",
            "missing_metadata",
            "bad_names",
            "unapplied_scale",
            "high_poly",
            "no_parent",
            "thin_geometry",
        ]
    ] = Field(default_factory=lambda: ["overlaps", "floating", "missing_materials", "bad_names", "unapplied_scale"])
    ground_z: float = 0.0
    tolerance: float = Field(0.001, ge=0.0)
    max_vertices: int = Field(100_000, ge=1)


class DetectOverlapsParams(ToolModel):
    """Detect bounding-box overlaps."""

    objects: list[str] | None = None
    ignore_touching: bool = True
    tolerance: float = Field(0.001, ge=0.0)
    limit: int = Field(200, ge=1, le=5000)


class ValidateSymmetryParams(ToolModel):
    """Validate approximate symmetry around an axis."""

    left_objects: list[str] = Field(..., min_length=1)
    right_objects: list[str] = Field(..., min_length=1)
    axis: Literal["X", "Y", "Z"] = "X"
    tolerance: float = Field(0.05, ge=0.0)


class CheckScaleConsistencyParams(ToolModel):
    """Check dimensions against expected ranges."""

    objects: list[str] = Field(..., min_length=1)
    min_dimensions: Vector3 | None = None
    max_dimensions: Vector3 | None = None

    @model_validator(mode="after")
    def require_range(self) -> "CheckScaleConsistencyParams":
        """Require one bound."""
        if self.min_dimensions is None and self.max_dimensions is None:
            raise ValueError("Provide min_dimensions, max_dimensions, or both.")
        return self


class GenerateQualityReportParams(ToolModel):
    """Generate a compact scene quality report."""

    objects: list[str] | None = None
    include_counts: bool = True
    include_materials: bool = True
    include_collections: bool = True
    include_issues: bool = True


class SuggestModelImprovementsParams(ToolModel):
    """Return improvement suggestions from detected issues."""

    objects: list[str] | None = None
    target_quality: Literal["draft", "clean", "production"] = "production"


class PolishTopologyParams(ToolModel):
    """Clean mesh and optimize shading topology."""

    objects: list[str] | None = Field(None, description="Objects to polish; active/selected objects are used if empty.")
    merge_distance: float = Field(0.0001, ge=0.0, description="Distance threshold for vertex merging.")
    remove_loose_edges: bool = Field(True, description="Remove loose edges with no faces.")
    keep_sharp: bool = Field(True, description="Keep sharp edges in Weighted Normal modifier.")
    auto_smooth_angle: float = Field(30.0, ge=0.0, le=180.0, description="Angle threshold for smooth shading.")


_SPECS: list[tuple[str, str, type[BaseModel]]] = [
    ("validate_scene_quality", "Run scene/model quality checks.", ValidateSceneQualityParams),
    ("detect_overlaps", "Detect object bounding-box overlaps.", DetectOverlapsParams),
    ("validate_symmetry", "Validate left/right symmetry.", ValidateSymmetryParams),
    ("check_scale_consistency", "Check object dimensions against expected ranges.", CheckScaleConsistencyParams),
    ("generate_quality_report", "Generate a compact quality report.", GenerateQualityReportParams),
    ("suggest_model_improvements", "Suggest model improvements from quality checks.", SuggestModelImprovementsParams),
    ("polish_topology", "Clean mesh topology and optimize normals.", PolishTopologyParams),
]

TOOLS = build_tools(_SPECS)
export_tools(globals(), TOOLS)


def register_tools(registry):
    """Register quality validation tools."""
    return register_toolset(registry, TOOLS)


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
