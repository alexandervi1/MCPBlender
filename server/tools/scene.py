"""Scene-management MCP tools for Blender."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .materials import ColorValue, _validate_color_value
from .objects import ToolDefinition, _dispatch, _register_tool

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list[JsonScalar] | dict[str, JsonScalar]


class StrictModel(BaseModel):
    """Base model for strict scene tool parameters."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class GetSceneInfoParams(StrictModel):
    """Input model for ``get_scene_info``."""

    include_collections: bool = Field(True, description="Include collection summary.")
    include_render_settings: bool = Field(True, description="Include render settings.")


class SetScenePropertyParams(StrictModel):
    """Input model for ``set_scene_property``."""

    property_path: str = Field(..., min_length=1, description="Top-level scene property or dotted path.")
    value: JsonValue = Field(..., description="JSON-serializable property value.")


class SetUnitSystemParams(StrictModel):
    """Input model for ``set_unit_system``."""

    system: Literal["METRIC", "IMPERIAL", "NONE"] = Field(..., description="Blender unit system.")
    scale: float = Field(1.0, gt=0.0, description="Unit scale multiplier.")
    length_unit: str | None = Field(None, description="Optional Blender length unit.")


class SetFrameParams(StrictModel):
    """Input model for ``set_frame``."""

    current: int | None = Field(None, ge=0, description="Current frame.")
    start: int | None = Field(None, ge=0, description="Start frame.")
    end: int | None = Field(None, ge=0, description="End frame.")

    @model_validator(mode="after")
    def _some_frame(self) -> "SetFrameParams":
        if self.current is None and self.start is None and self.end is None:
            raise ValueError("Provide at least one of current, start, or end.")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("end must be greater than or equal to start.")
        return self


class SetFrameRangeParams(StrictModel):
    """Input model for ``set_frame_range``."""

    start: int = Field(..., ge=0, description="Start frame.")
    end: int = Field(..., ge=0, description="End frame.")
    preview_start: int | None = Field(None, ge=0, description="Optional preview start frame.")
    preview_end: int | None = Field(None, ge=0, description="Optional preview end frame.")

    @model_validator(mode="after")
    def _ordered(self) -> "SetFrameRangeParams":
        if self.end < self.start:
            raise ValueError("end must be greater than or equal to start.")
        if self.preview_start is not None and self.preview_end is not None and self.preview_end < self.preview_start:
            raise ValueError("preview_end must be greater than or equal to preview_start.")
        return self


class ClearSceneParams(StrictModel):
    """Input model for ``clear_scene``."""

    keep_types: list[str] = Field(default_factory=list, description="Object types to keep, such as CAMERA or LIGHT.")
    include_collections: bool = Field(False, description="Remove empty collections as well.")


class ListCollectionsParams(StrictModel):
    """Input model for ``list_collections``."""

    include_objects: bool = Field(True, description="Include object names in each collection.")
    recursive: bool = Field(True, description="Traverse nested collections.")


class CreateCollectionParams(StrictModel):
    """Input model for ``create_collection``."""

    name: str = Field(..., min_length=1, description="Collection name.")
    parent: str | None = Field(None, description="Optional parent collection.")


class MoveToCollectionParams(StrictModel):
    """Input model for ``move_to_collection``."""

    object_names: list[str] = Field(..., min_length=1, description="Objects to move or link.")
    collection_name: str = Field(..., min_length=1, description="Target collection.")
    unlink_from_others: bool = Field(True, description="Unlink from other collections after moving.")
    create_if_missing: bool = Field(True, description="Create target collection when absent.")


class SetWorldColorParams(StrictModel):
    """Input model for ``set_world_color``."""

    color: ColorValue | None = Field(None, description="World color as hex or RGB/RGBA tuple.")
    hdri_path: str | None = Field(None, min_length=1, description="HDRI image path for world lighting.")
    strength: float = Field(1.0, ge=0.0, description="World background strength.")

    @field_validator("color")
    @classmethod
    def _color(cls, value: ColorValue | None) -> ColorValue | None:
        return None if value is None else _validate_color_value(value)

    @model_validator(mode="after")
    def _source_required(self) -> "SetWorldColorParams":
        if self.color is None and self.hdri_path is None:
            raise ValueError("Provide color or hdri_path.")
        return self


async def get_scene_info(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Return scene name, units, frame range, camera, and render engine."""

    return await _dispatch(bridge, "get_scene_info", GetSceneInfoParams, params)


async def set_scene_property(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set a top-level scene property or dotted property path."""

    return await _dispatch(bridge, "set_scene_property", SetScenePropertyParams, params)


async def set_unit_system(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set metric, imperial, or unitless scene units."""

    return await _dispatch(bridge, "set_unit_system", SetUnitSystemParams, params)


async def set_frame(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set current, start, and/or end frame."""

    return await _dispatch(bridge, "set_frame", SetFrameParams, params)


async def set_frame_range(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set scene frame start and end values."""

    return await _dispatch(bridge, "set_frame_range", SetFrameRangeParams, params)


async def clear_scene(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Remove objects from the scene with optional type preservation."""

    return await _dispatch(bridge, "clear_scene", ClearSceneParams, params)


async def list_collections(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """List collections in the Blender file."""

    return await _dispatch(bridge, "list_collections", ListCollectionsParams, params)


async def create_collection(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Create a collection, optionally under another collection."""

    return await _dispatch(bridge, "create_collection", CreateCollectionParams, params)


async def move_to_collection(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Move or link objects into a collection."""

    return await _dispatch(bridge, "move_to_collection", MoveToCollectionParams, params)


async def set_world_color(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set world background color or HDRI lighting."""

    return await _dispatch(bridge, "set_world_color", SetWorldColorParams, params)


TOOLS: dict[str, ToolDefinition] = {
    "get_scene_info": ToolDefinition("get_scene_info", "Inspect scene settings.", GetSceneInfoParams, get_scene_info),
    "set_scene_property": ToolDefinition("set_scene_property", "Set a scene property.", SetScenePropertyParams, set_scene_property),
    "set_unit_system": ToolDefinition("set_unit_system", "Configure scene units.", SetUnitSystemParams, set_unit_system),
    "set_frame": ToolDefinition("set_frame", "Set current/start/end frame.", SetFrameParams, set_frame),
    "set_frame_range": ToolDefinition("set_frame_range", "Set animation frame range.", SetFrameRangeParams, set_frame_range),
    "clear_scene": ToolDefinition("clear_scene", "Clear scene objects.", ClearSceneParams, clear_scene),
    "list_collections": ToolDefinition("list_collections", "List collections.", ListCollectionsParams, list_collections),
    "create_collection": ToolDefinition("create_collection", "Create a collection.", CreateCollectionParams, create_collection),
    "move_to_collection": ToolDefinition("move_to_collection", "Move objects to a collection.", MoveToCollectionParams, move_to_collection),
    "set_world_color": ToolDefinition("set_world_color", "Set world color or HDRI.", SetWorldColorParams, set_world_color),
}


def register_tools(registry: Any) -> Any:
    """Register all scene tools with a registry."""

    for spec in TOOLS.values():
        _register_tool(registry, spec)
    return registry


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
