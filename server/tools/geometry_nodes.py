"""Geometry Nodes MCP tools for Blender."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .objects import ToolDefinition, _dispatch, _register_tool

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list[JsonScalar] | dict[str, JsonScalar]


class StrictModel(BaseModel):
    """Base model for strict Geometry Nodes tool parameters."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class GeoNodeTargetParams(StrictModel):
    """Parameters for Geometry Nodes tools targeting one object."""

    object_name: str = Field(..., min_length=1, description="Object with a Geometry Nodes modifier.")
    modifier_name: str | None = Field(None, description="Geometry Nodes modifier name.")


class AddGeometryNodesModifierParams(StrictModel):
    """Input model for ``add_geometry_nodes_modifier``."""

    object_name: str = Field(..., min_length=1, description="Object receiving the modifier.")
    modifier_name: str = Field("Geometry Nodes", min_length=1, description="Modifier name.")
    node_group_name: str | None = Field(None, description="Existing or new node-group name.")
    create_default_io: bool = Field(True, description="Create Group Input/Output nodes when missing.")


class CreateNodeParams(GeoNodeTargetParams):
    """Input model for ``create_node``."""

    node_type: str = Field(..., min_length=1, description="Blender node type identifier.")
    node_name: str | None = Field(None, min_length=1, description="Optional node name.")
    location: tuple[float, float] = Field((0.0, 0.0), description="Node editor location.")
    properties: dict[str, JsonValue] = Field(default_factory=dict, description="Initial node properties.")


class ConnectNodesParams(GeoNodeTargetParams):
    """Input model for ``connect_nodes``."""

    from_node: str = Field(..., min_length=1, description="Output node name.")
    from_socket: str | int = Field(..., description="Output socket name or index.")
    to_node: str = Field(..., min_length=1, description="Input node name.")
    to_socket: str | int = Field(..., description="Input socket name or index.")


class SetNodeInputParams(GeoNodeTargetParams):
    """Input model for ``set_node_input``."""

    node_name: str = Field(..., min_length=1, description="Node name.")
    input_socket: str | int = Field(..., description="Input socket name or index.")
    value: JsonValue = Field(..., description="JSON-serializable socket default value.")


class SetGeoNodeInputParams(GeoNodeTargetParams):
    """Input model for ``set_geonode_input``."""

    input_name: str = Field(..., min_length=1, description="Exposed group input name.")
    value: JsonValue = Field(..., description="JSON-serializable input value.")


class ListNodesParams(GeoNodeTargetParams):
    """Input model for ``list_nodes``."""

    include_links: bool = Field(True, description="Include node links.")
    include_socket_defaults: bool = Field(True, description="Include socket default values.")

    @model_validator(mode="after")
    def _valid(self) -> "ListNodesParams":
        return self


async def add_geometry_nodes_modifier(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Add a Geometry Nodes modifier to an object."""

    return await _dispatch(bridge, "add_geometry_nodes_modifier", AddGeometryNodesModifierParams, params)


async def create_node(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Create a node in a Geometry Nodes tree."""

    return await _dispatch(bridge, "create_node", CreateNodeParams, params)


async def connect_nodes(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Connect two Geometry Nodes sockets."""

    return await _dispatch(bridge, "connect_nodes", ConnectNodesParams, params)


async def set_node_input(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set a node input socket default value."""

    return await _dispatch(bridge, "set_node_input", SetNodeInputParams, params)


async def set_geonode_input(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set an exposed Geometry Nodes group input value."""

    return await _dispatch(bridge, "set_geonode_input", SetGeoNodeInputParams, params)


async def list_nodes(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """List nodes and links in a Geometry Nodes tree."""

    return await _dispatch(bridge, "list_nodes", ListNodesParams, params)


TOOLS: dict[str, ToolDefinition] = {
    "add_geometry_nodes_modifier": ToolDefinition("add_geometry_nodes_modifier", "Add a Geometry Nodes modifier.", AddGeometryNodesModifierParams, add_geometry_nodes_modifier),
    "create_node": ToolDefinition("create_node", "Create a Geometry Nodes node.", CreateNodeParams, create_node),
    "connect_nodes": ToolDefinition("connect_nodes", "Connect Geometry Nodes sockets.", ConnectNodesParams, connect_nodes),
    "set_node_input": ToolDefinition("set_node_input", "Set a node input value.", SetNodeInputParams, set_node_input),
    "set_geonode_input": ToolDefinition("set_geonode_input", "Set a group input value.", SetGeoNodeInputParams, set_geonode_input),
    "list_nodes": ToolDefinition("list_nodes", "List Geometry Nodes nodes.", ListNodesParams, list_nodes),
}


def register_tools(registry: Any) -> Any:
    """Register all Geometry Nodes tools with a registry."""

    for spec in TOOLS.values():
        _register_tool(registry, spec)
    return registry


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
