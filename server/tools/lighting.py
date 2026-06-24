"""Lighting MCP tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .common import EmptyParams, NameParams, ToolModel, build_tools, export_tools, register_toolset

Vector3 = tuple[float, float, float]


class CreateLightParams(ToolModel):
    """Create a light object."""

    name: str | None = Field(None, min_length=1, description="Optional light object name.")
    light_type: Literal["POINT", "SUN", "SPOT", "AREA"] = Field(..., description="Blender light type.")
    location: Vector3 = Field((0.0, 0.0, 5.0), description="World-space XYZ location.")
    rotation: Vector3 = Field((0.0, 0.0, 0.0), description="Euler XYZ rotation in radians.")
    energy: float = Field(500.0, ge=0, description="Light energy.")
    color: str | tuple[float, float, float] | tuple[float, float, float, float] = Field(
        (1.0, 1.0, 1.0), description="Hex, RGB, or RGBA light color."
    )
    size: float | None = Field(None, gt=0.0, description="Area size or point radius when supported.")

    @field_validator("color")
    @classmethod
    def valid_color(
        cls, value: str | tuple[float, float, float] | tuple[float, float, float, float]
    ) -> str | tuple[float, float, float] | tuple[float, float, float, float]:
        """Validate light color values."""
        if isinstance(value, str):
            text = value[1:] if value.startswith("#") else value
            if len(text) not in {3, 4, 6, 8}:
                raise ValueError("Hex colors must be RGB, RGBA, RRGGBB, or RRGGBBAA.")
            int(text, 16)
            return value
        if any(component < 0 or component > 1 for component in value):
            raise ValueError("Color tuple components must be between 0 and 1.")
        return value


class LightPropertyParams(NameParams):
    """Set a light data property."""

    property_name: str = Field(..., min_length=1, description="Light data property name.")
    value: Any = Field(..., description="JSON-serializable property value.")


class ThreePointParams(ToolModel):
    """Create three point lighting around a subject."""

    target_object: str | None = Field(None, description="Target object; active object is used if omitted.")
    distance: float = Field(5.0, gt=0, description="Distance from target.")
    key_energy: float = Field(800.0, ge=0, description="Key light energy.")
    fill_energy: float = Field(250.0, ge=0, description="Fill light energy.")
    rim_energy: float = Field(450.0, ge=0, description="Rim light energy.")


class HDRIParams(ToolModel):
    """Load HDRI world lighting."""

    hdri_path: str = Field(..., min_length=1, description="HDRI image path.")
    strength: float = Field(1.0, ge=0, description="World lighting strength.")
    rotation: float = Field(0.0, description="Environment Z rotation in radians.")


class SetupStudioBackdropAndLightingParams(ToolModel):
    """Set up a professional studio cyclorama backdrop, lights, and camera depth of field."""

    backdrop_name: str = Field("Studio_Backdrop", min_length=1, description="Cyclorama object name.")
    backdrop_size: float = Field(20.0, gt=0, description="Cyclorama dimension scale.")
    backdrop_curve_radius: float = Field(4.0, ge=0, description="Bevel radius of the corner curve.")
    backdrop_color: str = Field("#e2e2e2", description="Hex or color tuple of cyclorama backdrop.")
    target_object: str | None = Field(None, description="Focus target object for camera and lights orientation.")
    light_distance: float = Field(8.0, gt=0, description="Distance from target object.")
    key_size: float = Field(4.0, gt=0)
    key_size_y: float = Field(3.0, gt=0)
    key_energy: float = Field(1200.0, ge=0)
    fill_size: float = Field(5.0, gt=0)
    fill_energy: float = Field(400.0, ge=0)
    rim_size: float = Field(3.0, gt=0)
    rim_energy: float = Field(800.0, ge=0)
    camera_name: str | None = Field(None, description="Active camera name override.")
    aperture_fstop: float = Field(2.8, gt=0, description="Camera depth of field f-stop aperture.")
    view_transform: str = Field("AgX", description="Render view transform (Filmic, AgX, etc.).")
    look: str = Field("Medium High Contrast", description="Color grading look preset.")


_SPECS: list[tuple[str, str, type[BaseModel]]] = [
    ("create_light", "Create a light.", CreateLightParams),
    ("set_light_property", "Set a light property.", LightPropertyParams),
    ("delete_light", "Delete a light.", NameParams),
    ("list_lights", "List lights.", EmptyParams),
    ("create_three_point_lighting", "Create studio three-point lighting.", ThreePointParams),
    ("create_hdri_lighting", "Create HDRI world lighting.", HDRIParams),
    ("setup_studio_backdrop_and_lighting", "Set up professional studio cyclorama backdrop and lighting.", SetupStudioBackdropAndLightingParams),
]

TOOLS = build_tools(_SPECS)
export_tools(globals(), TOOLS)


def register_tools(registry: Any) -> Any:
    """Register lighting tools."""
    return register_toolset(registry, TOOLS)


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
