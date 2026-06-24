"""Asset pipeline tools for higher-level model generation workflows."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .common import ToolModel, build_tools, export_tools, register_toolset


class CreateLowpolyAssetParams(ToolModel):
    """Create a complete lowpoly asset from a curated production preset."""

    asset_type: Literal["cargo_ship", "industrial_cargo_ship"] = "cargo_ship"
    name: str = Field("CargoShip", min_length=1)
    collection: str | None = Field(None, min_length=1)
    scale: float = Field(1.0, gt=0.0, le=100.0)
    quality_target: Literal["draft", "clean", "production"] = "clean"
    container_rows: int = Field(2, ge=1, le=3)
    container_tiers: int = Field(2, ge=1, le=3)
    include_crane: bool = True
    include_metadata: bool = True
    replace_existing: bool = True


_SPECS: list[tuple[str, str, type[BaseModel]]] = [
    (
        "create_lowpoly_asset",
        "Create a complete lowpoly asset with metadata, materials, components, and quality validation.",
        CreateLowpolyAssetParams,
    ),
]

TOOLS = build_tools(_SPECS)
export_tools(globals(), TOOLS)


def register_tools(registry):
    """Register asset pipeline tools."""
    return register_toolset(registry, TOOLS)


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
