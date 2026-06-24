"""Import and export MCP tools for Blender."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .objects import ToolDefinition, _dispatch, _register_tool

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list[JsonScalar] | dict[str, JsonScalar]
FileFormat = Literal["OBJ", "FBX", "GLTF", "GLB", "STL", "PLY", "ABC", "USD", "SVG", "DXF"]


class StrictModel(BaseModel):
    """Base model for strict import/export tool parameters."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ImportFileParams(StrictModel):
    """Input model for ``import_file``."""

    file_path: str = Field(..., min_length=1, description="File path to import.")
    file_format: FileFormat | Literal["AUTO"] = Field("AUTO", description="Input file format.")
    collection_name: str | None = Field(None, description="Optional target collection.")
    options: dict[str, JsonValue] = Field(default_factory=dict, description="Importer-specific options.")


class ExportFileParams(StrictModel):
    """Input model for ``export_file``."""

    file_path: str = Field(..., min_length=1, description="Output file path.")
    file_format: FileFormat | Literal["AUTO"] = Field("AUTO", description="Output file format.")
    selected_only: bool = Field(False, description="Export selected objects only.")
    apply_modifiers: bool = Field(True, description="Apply modifiers during export when supported.")
    triangulate: bool = Field(False, description="Triangulate exported mesh geometry.")
    options: dict[str, JsonValue] = Field(default_factory=dict, description="Exporter-specific options.")


class ImportImageAsPlaneParams(StrictModel):
    """Input model for ``import_image_as_plane``."""

    image_path: str = Field(..., min_length=1, description="Image path.")
    name: str | None = Field(None, min_length=1, description="Optional plane object name.")
    location: tuple[float, float, float] = Field((0.0, 0.0, 0.0), description="Plane location.")
    rotation: tuple[float, float, float] = Field((0.0, 0.0, 0.0), description="Plane Euler rotation.")
    size: float = Field(1.0, gt=0.0, description="Plane size.")
    use_alpha: bool = Field(True, description="Use image alpha channel.")
    shader: Literal["PRINCIPLED", "SHADELESS", "EMISSION"] = Field("PRINCIPLED", description="Material shader preset.")


class BlendLibraryParams(StrictModel):
    """Input model for ``link_blend_file`` and ``append_blend_file``."""

    blend_path: str = Field(..., min_length=1, description=".blend file path.")
    data_type: Literal["objects", "materials", "collections", "meshes", "cameras", "lights", "node_groups"] = Field(
        ..., description="Type of datablock to load."
    )
    names: list[str] = Field(..., min_length=1, description="Datablock names to link or append.")
    collection_name: str | None = Field(None, description="Optional collection for linked/appended objects.")
    instance_collections: bool = Field(False, description="Instance linked collections instead of linking contents.")

    @model_validator(mode="after")
    def _names_not_blank(self) -> "BlendLibraryParams":
        if any(not name.strip() for name in self.names):
            raise ValueError("names must not contain blank strings.")
        return self


async def import_file(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Import a supported 3D file format."""

    return await _dispatch(bridge, "import_file", ImportFileParams, params)


async def export_file(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Export the scene or selected objects to a supported 3D format."""

    return await _dispatch(bridge, "export_file", ExportFileParams, params)


async def import_image_as_plane(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Import an image and create a textured plane."""

    return await _dispatch(bridge, "import_image_as_plane", ImportImageAsPlaneParams, params)


async def link_blend_file(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Link datablocks from another .blend file."""

    return await _dispatch(bridge, "link_blend_file", BlendLibraryParams, params)


async def append_blend_file(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Append datablocks from another .blend file."""

    return await _dispatch(bridge, "append_blend_file", BlendLibraryParams, params)


TOOLS: dict[str, ToolDefinition] = {
    "import_file": ToolDefinition("import_file", "Import a 3D file.", ImportFileParams, import_file),
    "export_file": ToolDefinition("export_file", "Export a 3D file.", ExportFileParams, export_file),
    "import_image_as_plane": ToolDefinition("import_image_as_plane", "Import an image as a plane.", ImportImageAsPlaneParams, import_image_as_plane),
    "link_blend_file": ToolDefinition("link_blend_file", "Link data from a .blend file.", BlendLibraryParams, link_blend_file),
    "append_blend_file": ToolDefinition("append_blend_file", "Append data from a .blend file.", BlendLibraryParams, append_blend_file),
}


def register_tools(registry: Any) -> Any:
    """Register all import/export tools with a registry."""

    for spec in TOOLS.values():
        _register_tool(registry, spec)
    return registry


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
