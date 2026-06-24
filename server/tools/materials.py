"""Material and shader MCP tools for Blender."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .objects import ToolDefinition, _dispatch, _register_tool

ColorValue = str | tuple[float, float, float] | tuple[float, float, float, float]
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list[JsonScalar] | dict[str, JsonScalar]


class StrictModel(BaseModel):
    """Base model for strict material tool parameters."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def _validate_color_value(value: ColorValue) -> ColorValue:
    """Validate a hex or numeric color value."""

    if isinstance(value, str):
        text = value.strip()
        hex_text = text[1:] if text.startswith("#") else text
        if len(hex_text) not in {3, 4, 6, 8}:
            raise ValueError("Color hex strings must be RGB, RGBA, RRGGBB, or RRGGBBAA.")
        int(hex_text, 16)
        return value
    if not 3 <= len(value) <= 4:
        raise ValueError("Color tuples must contain RGB or RGBA components.")
    if any(component < 0.0 or component > 1.0 for component in value):
        raise ValueError("Color tuple components must be between 0 and 1.")
    return value


class MaterialNameParams(StrictModel):
    """Parameters for tools targeting one material."""

    material_name: str = Field(..., min_length=1, description="Material name.")


class CreateMaterialParams(MaterialNameParams):
    """Input model for ``create_material``."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "material_name": "Brushed Steel",
                    "base_color": "#b8c0c8",
                    "metallic": 1.0,
                    "roughness": 0.34,
                }
            ]
        },
    )

    base_color: ColorValue = Field("#ffffff", description="Base color as hex or RGB/RGBA tuple.")
    metallic: float = Field(0.0, ge=0.0, le=1.0, description="Principled metallic value.")
    roughness: float = Field(0.5, ge=0.0, le=1.0, description="Principled roughness value.")
    specular: float = Field(0.5, ge=0.0, le=1.0, description="Principled specular/IOR level.")
    alpha: float = Field(1.0, ge=0.0, le=1.0, description="Material alpha.")
    use_nodes: bool = Field(True, description="Enable node-based material setup.")

    @field_validator("base_color")
    @classmethod
    def _color(cls, value: ColorValue) -> ColorValue:
        return _validate_color_value(value)


class AssignMaterialParams(MaterialNameParams):
    """Input model for ``assign_material``."""

    object_name: str = Field(..., min_length=1, description="Object receiving the material.")
    face_indices: list[int] | None = Field(None, description="Optional face indices for partial assignment.")

    @field_validator("face_indices")
    @classmethod
    def _faces_non_negative(cls, value: list[int] | None) -> list[int] | None:
        if value and any(index < 0 for index in value):
            raise ValueError("face_indices must be non-negative.")
        return value


class ListMaterialsParams(StrictModel):
    """Input model for ``list_materials``."""

    include_nodes: bool = Field(False, description="Include node-tree summaries.")
    include_unused: bool = Field(True, description="Include materials with zero users.")


class SetMaterialColorParams(MaterialNameParams):
    """Input model for ``set_material_color``."""

    color: ColorValue = Field(..., description="New base color.")
    duplicate_if_shared: bool = Field(False, description="Duplicate the material if shared across multiple objects.")
    object_name: str | None = Field(None, description="Object to receive the duplicated material (needed if duplicate_if_shared=True).")

    @field_validator("color")
    @classmethod
    def _color(cls, value: ColorValue) -> ColorValue:
        return _validate_color_value(value)


class SetMaterialPropertyParams(MaterialNameParams):
    """Input model for ``set_material_property``."""

    property_name: str = Field(..., min_length=1, description="Principled BSDF input or material property.")
    value: JsonValue = Field(..., description="JSON-serializable property value.")
    node_name: str | None = Field(None, description="Optional node name override.")


class CreateEmissionMaterialParams(MaterialNameParams):
    """Input model for ``create_emission_material``."""

    color: ColorValue = Field("#ffffff", description="Emission color.")
    strength: float = Field(1.0, ge=0.0, description="Emission strength.")

    @field_validator("color")
    @classmethod
    def _color(cls, value: ColorValue) -> ColorValue:
        return _validate_color_value(value)


class CreateGlassMaterialParams(MaterialNameParams):
    """Input model for ``create_glass_material``."""

    color: ColorValue = Field("#ffffff", description="Glass tint.")
    ior: float = Field(1.45, gt=1.0, le=3.0, description="Index of refraction.")
    roughness: float = Field(0.0, ge=0.0, le=1.0, description="Glass roughness.")
    transmission: float = Field(1.0, ge=0.0, le=1.0, description="Transmission amount.")

    @field_validator("color")
    @classmethod
    def _color(cls, value: ColorValue) -> ColorValue:
        return _validate_color_value(value)


class AddTextureParams(MaterialNameParams):
    """Input model for ``add_texture``."""

    image_path: str = Field(..., min_length=1, description="Image file path accessible to Blender.")
    socket: str = Field("Base Color", min_length=1, description="Target shader input socket.")
    colorspace: Literal["sRGB", "Non-Color", "Linear", "Raw"] = Field("sRGB", description="Texture colorspace.")
    node_name: str | None = Field(None, min_length=1, description="Optional texture node name.")
    uv_map: str | None = Field(None, description="Optional UV map name.")


class SetupPBRMaterialParams(MaterialNameParams):
    """Input model for ``setup_pbr_material``."""

    diffuse_map: str | None = Field(None, description="Albedo/diffuse texture path.")
    normal_map: str | None = Field(None, description="Normal texture path.")
    roughness_map: str | None = Field(None, description="Roughness texture path.")
    metallic_map: str | None = Field(None, description="Metallic texture path.")
    displacement_map: str | None = Field(None, description="Optional displacement texture path.")
    normal_strength: float = Field(1.0, ge=0.0, description="Normal map strength.")
    displacement_scale: float = Field(0.1, ge=0.0, description="Displacement scale.")

    @model_validator(mode="after")
    def _one_map_required(self) -> "SetupPBRMaterialParams":
        if not any(
            [
                self.diffuse_map,
                self.normal_map,
                self.roughness_map,
                self.metallic_map,
                self.displacement_map,
            ]
        ):
            raise ValueError("Provide at least one PBR texture map.")
        return self


class SetupAdvancedPBRMaterialParams(MaterialNameParams):
    """Input model for ``setup_advanced_pbr_material``."""

    diffuse_map: str | None = Field(None, description="Albedo/diffuse texture path.")
    normal_map: str | None = Field(None, description="Normal texture path.")
    roughness_map: str | None = Field(None, description="Roughness texture path.")
    metallic_map: str | None = Field(None, description="Metallic texture path.")
    normal_strength: float = Field(1.0, ge=0.0, description="Normal map strength.")
    scale: tuple[float, float, float] = Field((1.0, 1.0, 1.0), description="Texture mapping scale.")
    rotation: tuple[float, float, float] = Field((0.0, 0.0, 0.0), description="Texture mapping rotation.")
    translation: tuple[float, float, float] = Field((0.0, 0.0, 0.0), description="Texture mapping offset translation.")
    blend: float = Field(0.2, ge=0.0, le=1.0, description="Triplanar box mapping blend factor.")
    color_tint: str | None = Field(None, description="Optional color tint hex code to mix with base color.")
    metallic: float = Field(0.0, ge=0.0, le=1.0)
    roughness: float = Field(0.5, ge=0.0, le=1.0)


class EnableNodesParams(MaterialNameParams):
    """Input model for ``enable_nodes``."""

    enable: bool = Field(True, description="Whether nodes should be enabled.")
    reset_tree: bool = Field(False, description="Reset to a default principled setup.")


class GetMaterialInfoParams(MaterialNameParams):
    """Input model for ``get_material_info``."""

    include_node_links: bool = Field(True, description="Include node link graph.")
    include_users: bool = Field(True, description="Include material users.")


async def create_material(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Create a PBR material.

    Args:
        bridge: Blender bridge instance.
        params: Material color and principled shader properties.

    Returns:
        Bridge response with created material metadata.
    """

    return await _dispatch(bridge, "create_material", CreateMaterialParams, params)


async def assign_material(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Assign a material to an object or selected face indices."""

    return await _dispatch(bridge, "assign_material", AssignMaterialParams, params)


async def list_materials(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """List materials in the current Blender file."""

    return await _dispatch(bridge, "list_materials", ListMaterialsParams, params)


async def delete_material(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Delete a material by name."""

    return await _dispatch(bridge, "delete_material", MaterialNameParams, params)


async def set_material_color(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set a material's base color."""

    return await _dispatch(bridge, "set_material_color", SetMaterialColorParams, params)


async def set_material_property(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set a material or Principled BSDF input property."""

    return await _dispatch(bridge, "set_material_property", SetMaterialPropertyParams, params)


async def create_emission_material(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Create an emissive material."""

    return await _dispatch(bridge, "create_emission_material", CreateEmissionMaterialParams, params)


async def create_glass_material(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Create a glass material preset."""

    return await _dispatch(bridge, "create_glass_material", CreateGlassMaterialParams, params)


async def add_texture(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Add and connect an image texture node."""

    return await _dispatch(bridge, "add_texture", AddTextureParams, params)


async def setup_pbr_material(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Build a PBR node setup from supplied texture maps."""

    return await _dispatch(bridge, "setup_pbr_material", SetupPBRMaterialParams, params)


async def setup_advanced_pbr_material(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Create PBR material with triplanar projection and mapping scale/rotation/translation."""

    return await _dispatch(bridge, "setup_advanced_pbr_material", SetupAdvancedPBRMaterialParams, params)


async def enable_nodes(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Enable or disable node usage for a material."""

    return await _dispatch(bridge, "enable_nodes", EnableNodesParams, params)


async def get_material_info(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Inspect a material and its node tree."""

    return await _dispatch(bridge, "get_material_info", GetMaterialInfoParams, params)


TOOLS: dict[str, ToolDefinition] = {
    "create_material": ToolDefinition("create_material", "Create a PBR material.", CreateMaterialParams, create_material),
    "assign_material": ToolDefinition("assign_material", "Assign a material to an object.", AssignMaterialParams, assign_material),
    "list_materials": ToolDefinition("list_materials", "List scene materials.", ListMaterialsParams, list_materials),
    "delete_material": ToolDefinition("delete_material", "Delete a material by name.", MaterialNameParams, delete_material),
    "set_material_color": ToolDefinition("set_material_color", "Set a material base color.", SetMaterialColorParams, set_material_color),
    "set_material_property": ToolDefinition("set_material_property", "Set a material property or shader input.", SetMaterialPropertyParams, set_material_property),
    "create_emission_material": ToolDefinition("create_emission_material", "Create an emissive material.", CreateEmissionMaterialParams, create_emission_material),
    "create_glass_material": ToolDefinition("create_glass_material", "Create a glass material preset.", CreateGlassMaterialParams, create_glass_material),
    "add_texture": ToolDefinition("add_texture", "Add an image texture node.", AddTextureParams, add_texture),
    "setup_pbr_material": ToolDefinition("setup_pbr_material", "Create a full PBR material node setup.", SetupPBRMaterialParams, setup_pbr_material),
    "setup_advanced_pbr_material": ToolDefinition("setup_advanced_pbr_material", "Create an advanced PBR material with triplanar box mapping.", SetupAdvancedPBRMaterialParams, setup_advanced_pbr_material),
    "enable_nodes": ToolDefinition("enable_nodes", "Enable or disable material nodes.", EnableNodesParams, enable_nodes),
    "get_material_info": ToolDefinition("get_material_info", "Inspect a material node tree.", GetMaterialInfoParams, get_material_info),
}


def register_tools(registry: Any) -> Any:
    """Register all material tools with a registry."""

    for spec in TOOLS.values():
        _register_tool(registry, spec)
    return registry


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
