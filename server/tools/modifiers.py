"""Modifier-stack MCP tools for Blender."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .objects import ToolDefinition, _dispatch, _register_tool

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list[JsonScalar] | dict[str, JsonScalar]


class StrictModel(BaseModel):
    """Base model for strict modifier tool parameters."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ModifierTargetParams(StrictModel):
    """Parameters for a named modifier on an object."""

    object_name: str = Field(..., min_length=1, description="Object containing the modifier.")
    modifier_name: str = Field(..., min_length=1, description="Modifier name.")


class AddModifierParams(StrictModel):
    """Input model for ``add_modifier``."""

    object_name: str = Field(..., min_length=1, description="Object receiving the modifier.")
    modifier_type: str = Field(..., min_length=1, description="Blender modifier type, such as SUBSURF.")
    name: str | None = Field(None, min_length=1, description="Optional modifier name.")
    properties: dict[str, JsonValue] = Field(default_factory=dict, description="Initial modifier properties.")


class SetModifierPropertyParams(ModifierTargetParams):
    """Input model for ``set_modifier_property``."""

    property_name: str = Field(..., min_length=1, description="Modifier property name.")
    value: JsonValue = Field(..., description="JSON-serializable property value.")


class ApplyModifierParams(ModifierTargetParams):
    """Input model for ``apply_modifier``."""

    as_shapekey: bool = Field(False, description="Apply as shape key when supported.")
    keep_modifier: bool = Field(False, description="Keep a copy of the modifier after applying when supported.")


class RemoveModifierParams(ModifierTargetParams):
    """Input model for ``remove_modifier``."""


class ListModifiersParams(StrictModel):
    """Input model for ``list_modifiers``."""

    object_name: str = Field(..., min_length=1, description="Object to inspect.")
    include_properties: bool = Field(True, description="Include public modifier properties.")


class ReorderModifierParams(ModifierTargetParams):
    """Input model for ``reorder_modifier``."""

    direction: Literal["UP", "DOWN", "TOP", "BOTTOM", "INDEX"] = Field(..., description="Stack move direction.")
    index: int | None = Field(None, ge=0, description="Target stack index for direction INDEX.")


class ApplyDisplacementMapParams(StrictModel):
    """Input model for ``apply_displacement_map``."""

    object_name: str = Field(..., min_length=1, description="Object to receive the displacement map.")
    texture_type: Literal["CLOUDS", "VORONOI", "MUSGRAVE", "DISTORTED_NOISE", "MAGIC", "MARBLE", "WOOD"] = Field(
        "CLOUDS", description="Procedural texture type."
    )
    strength: float = Field(0.5, description="Displacement strength/factor.")
    mid_level: float = Field(0.5, description="Texture mid level.")


async def add_modifier(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Add a Blender modifier to an object."""

    return await _dispatch(bridge, "add_modifier", AddModifierParams, params)


async def set_modifier_property(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set a property on an existing modifier."""

    return await _dispatch(bridge, "set_modifier_property", SetModifierPropertyParams, params)


async def apply_modifier(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Apply a modifier to mesh data."""

    return await _dispatch(bridge, "apply_modifier", ApplyModifierParams, params)


async def remove_modifier(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Remove a modifier from an object."""

    return await _dispatch(bridge, "remove_modifier", RemoveModifierParams, params)


async def list_modifiers(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """List modifiers on an object."""

    return await _dispatch(bridge, "list_modifiers", ListModifiersParams, params)


async def reorder_modifier(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Move a modifier within the modifier stack."""

    return await _dispatch(bridge, "reorder_modifier", ReorderModifierParams, params)


async def apply_displacement_map(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Apply procedural displacement map modifier and texture."""

    return await _dispatch(bridge, "apply_displacement_map", ApplyDisplacementMapParams, params)


TOOLS: dict[str, ToolDefinition] = {
    "add_modifier": ToolDefinition("add_modifier", "Add a modifier to an object.", AddModifierParams, add_modifier),
    "set_modifier_property": ToolDefinition("set_modifier_property", "Set a modifier property.", SetModifierPropertyParams, set_modifier_property),
    "apply_modifier": ToolDefinition("apply_modifier", "Apply a modifier.", ApplyModifierParams, apply_modifier),
    "remove_modifier": ToolDefinition("remove_modifier", "Remove a modifier.", RemoveModifierParams, remove_modifier),
    "list_modifiers": ToolDefinition("list_modifiers", "List object modifiers.", ListModifiersParams, list_modifiers),
    "reorder_modifier": ToolDefinition("reorder_modifier", "Reorder a modifier in the stack.", ReorderModifierParams, reorder_modifier),
    "apply_displacement_map": ToolDefinition("apply_displacement_map", "Apply procedural displacement map.", ApplyDisplacementMapParams, apply_displacement_map),
}


def register_tools(registry: Any) -> Any:
    """Register all modifier tools with a registry."""

    for spec in TOOLS.values():
        _register_tool(registry, spec)
    return registry


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]

