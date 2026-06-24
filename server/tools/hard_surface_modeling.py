"""Hard-surface modeling helpers for clean mechanical and prop assets."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .common import ToolModel, build_tools, export_tools, register_toolset

Vector3 = tuple[float, float, float]


class RoundedBoxParams(ToolModel):
    """Create a bevel-ready rounded box."""

    name: str = Field(..., min_length=1)
    location: Vector3 = (0.0, 0.0, 0.0)
    size: Vector3 = (1.0, 1.0, 1.0)
    bevel: float = Field(0.05, ge=0.0)
    segments: int = Field(3, ge=1, le=32)
    material_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaperedCylinderParams(ToolModel):
    """Create a cylinder with different top and bottom radii."""

    name: str
    location: Vector3 = (0.0, 0.0, 0.0)
    radius_bottom: float = Field(..., gt=0.0)
    radius_top: float = Field(..., ge=0.0)
    depth: float = Field(..., gt=0.0)
    vertices: int = Field(48, ge=3, le=256)
    bevel: float = Field(0.0, ge=0.0)
    material_name: str | None = None


class CapsuleSegmentParams(ToolModel):
    """Create a capsule-like segment for limbs, handles, and sci-fi forms."""

    name: str
    location: Vector3 = (0.0, 0.0, 0.0)
    radius: float = Field(..., gt=0.0)
    length: float = Field(..., gt=0.0)
    axis: Literal["X", "Y", "Z"] = "Z"
    material_name: str | None = None


class PanelSeamParams(ToolModel):
    """Create a thin raised or inset panel seam."""

    target_name: str | None = None
    name: str = Field(..., min_length=1)
    location: Vector3
    size: Vector3
    orientation: Vector3 = (0.0, 0.0, 0.0)
    seam_width: float = Field(0.02, gt=0.0)
    material_name: str | None = None


class RingJointParams(ToolModel):
    """Create a torus/cylindrical ring joint."""

    name: str
    location: Vector3
    major_radius: float = Field(..., gt=0.0)
    minor_radius: float = Field(..., gt=0.0)
    orientation: Vector3 = (0.0, 0.0, 0.0)
    material_name: str | None = None


class SlotCutParams(ToolModel):
    """Create a rectangular cutter and optionally apply it as a Boolean slot."""

    target: str
    name: str = "Slot_Cutter"
    location: Vector3
    size: Vector3
    apply: bool = True
    keep_cutter: bool = False


class ScrewArrayParams(ToolModel):
    """Place screw/bolt heads at given points."""

    name_prefix: str = "Screw"
    points: list[Vector3] = Field(..., min_length=1)
    radius: float = Field(0.08, gt=0.0)
    depth: float = Field(0.035, gt=0.0)
    material_name: str | None = None


class VentGrilleParams(ToolModel):
    """Create a repeated grille/vent slat set."""

    name: str
    location: Vector3
    slat_count: int = Field(..., ge=1, le=200)
    slat_size: Vector3
    spacing: float = Field(..., gt=0.0)
    axis: Literal["X", "Y", "Z"] = "X"
    material_name: str | None = None


class WeightedNormalsParams(ToolModel):
    """Apply weighted normals to hard-surface objects."""

    objects: list[str] = Field(..., min_length=1)
    keep_sharp: bool = True
    weight: int = Field(50, ge=1, le=100)


class SupportLoopsParams(ToolModel):
    """Add bevel modifiers that behave like support loops."""

    object_name: str
    width: float = Field(..., gt=0.0)
    segments: int = Field(1, ge=1, le=8)
    apply: bool = False


_SPECS: list[tuple[str, str, type[BaseModel]]] = [
    ("create_rounded_box", "Create a rounded hard-surface box.", RoundedBoxParams),
    ("create_tapered_cylinder", "Create a tapered cylinder.", TaperedCylinderParams),
    ("create_capsule_segment", "Create a capsule-like segment.", CapsuleSegmentParams),
    ("create_panel_seam", "Create a panel seam detail.", PanelSeamParams),
    ("create_ring_joint", "Create a torus ring joint.", RingJointParams),
    ("create_slot_cut", "Cut a rectangular slot with a Boolean.", SlotCutParams),
    ("add_screw_array", "Place screw or bolt heads.", ScrewArrayParams),
    ("add_vent_grille", "Create repeated vent slats.", VentGrilleParams),
    ("apply_weighted_normals", "Add weighted normals modifiers.", WeightedNormalsParams),
    ("add_support_loops", "Add bevel support-loop style modifier.", SupportLoopsParams),
]

TOOLS = build_tools(_SPECS)
export_tools(globals(), TOOLS)


def register_tools(registry: Any) -> Any:
    """Register hard-surface tools."""
    return register_toolset(registry, TOOLS)


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
