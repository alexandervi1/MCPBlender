"""Professional material and look-development tools."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .common import ToolModel, build_tools, export_tools, register_toolset

Color = str | tuple[float, float, float, float] | list[float]
Vector3 = tuple[float, float, float]
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


class ColorMixin(ToolModel):
    """Shared color validation."""

    @field_validator("base_color", "color", "edge_color", check_fields=False)
    @classmethod
    def validate_color(cls, value: Color) -> Color:
        """Accept #RRGGBB/#RRGGBBAA or RGBA arrays."""
        if isinstance(value, str):
            if not HEX_RE.match(value):
                raise ValueError("Colors must be #RRGGBB, #RRGGBBAA, or RGBA values.")
            return value
        if len(value) != 4 or any(component < 0 or component > 1 for component in value):
            raise ValueError("RGBA values must contain four numbers from 0 to 1.")
        return value


class PBRMaterialParams(ColorMixin):
    """Create a principled PBR material."""

    name: str
    base_color: Color = "#ffffff"
    metallic: float = Field(0.0, ge=0.0, le=1.0)
    roughness: float = Field(0.5, ge=0.0, le=1.0)
    specular: float = Field(0.5, ge=0.0, le=1.0)
    alpha: float = Field(1.0, ge=0.0, le=1.0)
    normal_strength: float = Field(1.0, ge=0.0)
    texture_paths: dict[str, str] = Field(default_factory=dict)


class ToonMaterialParams(ColorMixin):
    """Create a toon/cel-shaded material."""

    name: str
    base_color: Color
    shadow_color: Color | None = None
    levels: int = Field(3, ge=2, le=8)
    roughness: float = Field(0.55, ge=0.0, le=1.0)


class ProceduralMaterialParams(ColorMixin):
    """Create a procedural material using noise."""

    name: str
    base_color: Color
    secondary_color: Color = "#222222"
    pattern: Literal["noise", "marble", "brushed_metal", "concrete", "plastic"] = "noise"
    scale: float = Field(18.0, gt=0.0)
    strength: float = Field(0.25, ge=0.0)


class EdgeWearParams(ToolModel):
    """Add an edge-wear style node setup marker to a material."""

    material_name: str
    amount: float = Field(0.2, ge=0.0, le=1.0)
    color: Color = "#d8d0b8"


class AssignMaterialByNameParams(ToolModel):
    """Assign a material to multiple objects."""

    objects: list[str] = Field(..., min_length=1)
    material_name: str


class DecalParams(ColorMixin):
    """Create a simple decal plane near an object."""

    name: str
    target_object: str | None = None
    image_path: str | None = None
    text: str | None = None
    location: Vector3 = (0.0, 0.0, 0.0)
    size: tuple[float, float] = (1.0, 0.35)
    color: Color = "#ffffff"


class OutlineParams(ColorMixin):
    """Add an inverted-hull outline helper."""

    objects: list[str] = Field(..., min_length=1)
    thickness: float = Field(0.025, gt=0.0)
    edge_color: Color = "#000000"


class MaterialVariationParams(ToolModel):
    """Create material variations for selected objects."""

    objects: list[str] = Field(..., min_length=1)
    source_material: str
    variation_prefix: str = "Var"
    hue_shift: float = 0.0
    roughness_jitter: float = Field(0.05, ge=0.0, le=1.0)


_SPECS: list[tuple[str, str, type[BaseModel]]] = [
    ("create_pbr_material", "Create a PBR material with optional texture slots.", PBRMaterialParams),
    ("create_toon_material", "Create a toon/cel-shaded material.", ToonMaterialParams),
    ("create_procedural_material", "Create a procedural material.", ProceduralMaterialParams),
    ("add_edge_wear", "Add edge-wear style material metadata/nodes.", EdgeWearParams),
    ("assign_material_by_name", "Assign a material to many objects.", AssignMaterialByNameParams),
    ("create_decal", "Create a simple decal plane.", DecalParams),
    ("add_outline_modifier", "Add an outline helper modifier/material.", OutlineParams),
    ("apply_material_variation", "Create and assign material variations.", MaterialVariationParams),
]

TOOLS = build_tools(_SPECS)
export_tools(globals(), TOOLS)


def register_tools(registry: Any) -> Any:
    """Register professional material tools."""
    return register_toolset(registry, TOOLS)


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
