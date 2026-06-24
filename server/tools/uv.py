"""UV mapping MCP tools for Blender."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .objects import ToolDefinition, _dispatch, _register_tool


class StrictModel(BaseModel):
    """Base model for strict UV tool parameters."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class UVTargetParams(StrictModel):
    """Parameters for tools targeting one mesh object's UV data."""

    object_name: str = Field(..., min_length=1, description="Mesh object name.")
    uv_map: str | None = Field(None, description="Optional UV map name.")


class UnwrapUVParams(UVTargetParams):
    """Input model for ``unwrap_uv``."""

    method: Literal["SMART", "ANGLE_BASED", "CONFORMAL", "CUBE", "CYLINDER", "SPHERE"] = Field(
        "SMART", description="UV unwrap or projection method."
    )
    angle_limit: float = Field(66.0, ge=1.0, le=89.0, description="Smart UV angle limit in degrees.")
    island_margin: float = Field(0.03, ge=0.0, le=1.0, description="UV island margin.")
    area_weight: float = Field(0.0, ge=0.0, le=1.0, description="Smart UV area weight.")
    correct_aspect: bool = Field(True, description="Correct texture aspect ratio.")
    selected_only: bool = Field(False, description="Operate only on selected faces.")


class PackUVsParams(UVTargetParams):
    """Input model for ``pack_uvs``."""

    margin: float = Field(0.03, ge=0.0, le=1.0, description="Island margin.")
    rotate: bool = Field(True, description="Allow island rotation.")
    scale: bool = Field(True, description="Allow island scaling.")


class ScaleUVsParams(UVTargetParams):
    """Input model for ``scale_uvs``."""

    scale: tuple[float, float] = Field(..., description="UV scale on U and V axes.")
    pivot: tuple[float, float] = Field((0.5, 0.5), description="UV pivot coordinate.")

    @model_validator(mode="after")
    def _non_zero(self) -> "ScaleUVsParams":
        if self.scale[0] == 0 or self.scale[1] == 0:
            raise ValueError("UV scale components must be non-zero.")
        return self


class SelectUVIslandParams(UVTargetParams):
    """Input model for ``select_uv_island``."""

    face_index: int | None = Field(None, ge=0, description="Seed face index.")
    island_index: int | None = Field(None, ge=0, description="Island index when known.")
    extend: bool = Field(False, description="Extend selection instead of replacing it.")

    @model_validator(mode="after")
    def _seed_required(self) -> "SelectUVIslandParams":
        if self.face_index is None and self.island_index is None:
            raise ValueError("Provide face_index or island_index.")
        return self


class ExportUVLayoutParams(UVTargetParams):
    """Input model for ``export_uv_layout``."""

    output_path: str = Field(..., min_length=1, description="Output image path.")
    size: tuple[int, int] = Field((2048, 2048), description="Output image size.")
    opacity: float = Field(0.25, ge=0.0, le=1.0, description="Face fill opacity.")
    mode: Literal["PNG", "EPS", "SVG"] = Field("PNG", description="Export format.")
    modified: bool = Field(False, description="Use modified mesh data.")

    @model_validator(mode="after")
    def _size_positive(self) -> "ExportUVLayoutParams":
        if self.size[0] <= 0 or self.size[1] <= 0:
            raise ValueError("size must contain positive dimensions.")
        return self


async def unwrap_uv(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Unwrap or project UV coordinates on a mesh."""

    return await _dispatch(bridge, "unwrap_uv", UnwrapUVParams, params)


async def pack_uvs(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Pack UV islands into the 0-1 UV space."""

    return await _dispatch(bridge, "pack_uvs", PackUVsParams, params)


async def scale_uvs(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Scale UV coordinates around a pivot."""

    return await _dispatch(bridge, "scale_uvs", ScaleUVsParams, params)


async def select_uv_island(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Select a UV island by face or island index."""

    return await _dispatch(bridge, "select_uv_island", SelectUVIslandParams, params)


async def export_uv_layout(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Export the UV layout to an image or vector file."""

    return await _dispatch(bridge, "export_uv_layout", ExportUVLayoutParams, params)


TOOLS: dict[str, ToolDefinition] = {
    "unwrap_uv": ToolDefinition("unwrap_uv", "Unwrap or project mesh UVs.", UnwrapUVParams, unwrap_uv),
    "pack_uvs": ToolDefinition("pack_uvs", "Pack UV islands.", PackUVsParams, pack_uvs),
    "scale_uvs": ToolDefinition("scale_uvs", "Scale UV coordinates.", ScaleUVsParams, scale_uvs),
    "select_uv_island": ToolDefinition("select_uv_island", "Select a UV island.", SelectUVIslandParams, select_uv_island),
    "export_uv_layout": ToolDefinition("export_uv_layout", "Export a UV layout.", ExportUVLayoutParams, export_uv_layout),
}


def register_tools(registry: Any) -> Any:
    """Register all UV tools with a registry."""

    for spec in TOOLS.values():
        _register_tool(registry, spec)
    return registry


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
