"""Animation and keyframe MCP tools for Blender."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .objects import ToolDefinition, Vector3, _dispatch, _register_tool

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list[JsonScalar] | dict[str, JsonScalar]


class StrictModel(BaseModel):
    """Base model for strict animation tool parameters."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AnimationTargetParams(StrictModel):
    """Parameters for tools targeting one animated object."""

    object_name: str = Field(..., min_length=1, description="Animated object name.")


class InsertKeyframeParams(AnimationTargetParams):
    """Input model for ``insert_keyframe``."""

    data_path: str = Field(..., min_length=1, description="Animatable data path.")
    frame: int = Field(..., ge=0, description="Frame number.")
    index: int | None = Field(None, ge=0, description="Optional array index.")
    value: JsonValue | None = Field(None, description="Optional value to set before keying.")


class DeleteKeyframeParams(AnimationTargetParams):
    """Input model for ``delete_keyframe``."""

    data_path: str = Field(..., min_length=1, description="Animatable data path.")
    frame: int | None = Field(None, ge=0, description="Optional frame number.")
    index: int | None = Field(None, ge=0, description="Optional array index.")


class SetInterpolationParams(AnimationTargetParams):
    """Input model for ``set_interpolation``."""

    interpolation: Literal["LINEAR", "BEZIER", "CONSTANT"] = Field(..., description="F-curve interpolation.")
    data_path: str | None = Field(None, description="Optional data path filter.")
    frame: int | None = Field(None, ge=0, description="Optional keyframe frame filter.")


class ListKeyframesParams(AnimationTargetParams):
    """Input model for ``list_keyframes``."""

    data_path: str | None = Field(None, description="Optional data path filter.")
    include_values: bool = Field(True, description="Include keyframe values and interpolation.")


class CreateRotationAnimationParams(AnimationTargetParams):
    """Input model for ``create_rotation_animation``."""

    start_frame: int = Field(..., ge=0, description="Start frame.")
    end_frame: int = Field(..., ge=0, description="End frame.")
    axis: Literal["X", "Y", "Z"] = Field("Z", description="Rotation axis.")
    revolutions: float = Field(1.0, description="Number of complete revolutions.")
    interpolation: Literal["LINEAR", "BEZIER", "CONSTANT"] = Field("LINEAR", description="Interpolation mode.")

    @model_validator(mode="after")
    def _ordered(self) -> "CreateRotationAnimationParams":
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be greater than start_frame.")
        return self


class CreatePathAnimationParams(AnimationTargetParams):
    """Input model for ``create_path_animation``."""

    path_name: str = Field(..., min_length=1, description="Bezier or NURBS path object name.")
    start_frame: int = Field(..., ge=0, description="Start frame.")
    end_frame: int = Field(..., ge=0, description="End frame.")
    follow_curve: bool = Field(True, description="Orient object along the path.")
    use_fixed_location: bool = Field(False, description="Use fixed location on path when supported.")

    @model_validator(mode="after")
    def _ordered(self) -> "CreatePathAnimationParams":
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be greater than start_frame.")
        return self


class SetFPSParams(StrictModel):
    """Input model for ``set_fps``."""

    fps: int = Field(..., ge=1, le=240, description="Scene frames per second.")
    fps_base: float = Field(1.0, gt=0.0, description="Blender fps_base value.")


class BakeAnimationParams(StrictModel):
    """Input model for ``bake_animation``."""

    object_names: list[str] | None = Field(None, description="Objects to bake; selected objects if omitted.")
    start_frame: int = Field(..., ge=0, description="Bake start frame.")
    end_frame: int = Field(..., ge=0, description="Bake end frame.")
    step: int = Field(1, ge=1, description="Frame step.")
    visual_keying: bool = Field(True, description="Bake visual transforms.")
    clear_constraints: bool = Field(False, description="Clear constraints after baking.")
    clear_parents: bool = Field(False, description="Clear parents after baking.")
    bake_types: list[Literal["POSE", "OBJECT"]] = Field(default_factory=lambda: ["OBJECT"], description="Bake types.")

    @field_validator("object_names")
    @classmethod
    def _names(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and not value:
            raise ValueError("object_names must be omitted or contain at least one name.")
        return value

    @model_validator(mode="after")
    def _ordered(self) -> "BakeAnimationParams":
        if self.end_frame < self.start_frame:
            raise ValueError("end_frame must be greater than or equal to start_frame.")
        return self


class CreateCharacterSkeletonParams(StrictModel):
    """Input model for ``create_character_skeleton``."""

    name: str = Field("Skeleton", min_length=1, description="Skeleton object name.")
    skeleton_type: Literal["HUMANOID", "ROOT"] = Field("HUMANOID", description="Skeleton preset type.")


class BindMeshToArmatureParams(StrictModel):
    """Input model for ``bind_mesh_to_armature``."""

    mesh_name: str = Field(..., min_length=1, description="Mesh object name.")
    armature_name: str = Field(..., min_length=1, description="Armature object name.")


class PoseBoneParams(StrictModel):
    """Input model for ``pose_bone``."""

    armature_name: str = Field(..., min_length=1, description="Armature object name.")
    bone_name: str = Field(..., min_length=1, description="Bone name inside the armature.")
    rotation: list[float] | None = Field(None, description="Rotation Euler (X, Y, Z) in degrees.")
    location: list[float] | None = Field(None, description="Location translation offset [X, Y, Z].")
    scale: list[float] | None = Field(None, description="Scale factor [X, Y, Z].")

    @field_validator("rotation", "location", "scale")
    @classmethod
    def _validate_3d_vector(cls, value: list[float] | None) -> list[float] | None:
        if value is not None and len(value) != 3:
            raise ValueError("Vector must have exactly 3 elements.")
        return value


class ApplyAnimationPresetParams(StrictModel):
    """Input model for ``apply_animation_preset``."""

    object_name: str = Field(..., min_length=1, description="Target object name.")
    preset_type: Literal["BOUNCE", "WAVE", "WALK"] = Field("BOUNCE", description="Animation preset type.")
    start_frame: int = Field(1, ge=0, description="Start frame.")
    end_frame: int = Field(100, ge=1, description="End frame.")
    speed: float = Field(1.0, description="Animation speed factor.")
    intensity: float = Field(1.0, description="Animation intensity factor.")

    @model_validator(mode="after")
    def _ordered(self) -> "ApplyAnimationPresetParams":
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be greater than start_frame.")
        return self


async def insert_keyframe(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Insert an object keyframe for a data path."""

    return await _dispatch(bridge, "insert_keyframe", InsertKeyframeParams, params)


async def delete_keyframe(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Delete keyframes from an object data path."""

    return await _dispatch(bridge, "delete_keyframe", DeleteKeyframeParams, params)


async def set_interpolation(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set interpolation on matching F-curves or keyframes."""

    return await _dispatch(bridge, "set_interpolation", SetInterpolationParams, params)


async def list_keyframes(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """List keyframes for an object."""

    return await _dispatch(bridge, "list_keyframes", ListKeyframesParams, params)


async def create_rotation_animation(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Animate full rotations over a frame range."""

    return await _dispatch(bridge, "create_rotation_animation", CreateRotationAnimationParams, params)


async def create_path_animation(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Animate an object along a curve path."""

    return await _dispatch(bridge, "create_path_animation", CreatePathAnimationParams, params)


async def set_fps(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set scene frames per second."""

    return await _dispatch(bridge, "set_fps", SetFPSParams, params)


async def bake_animation(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Bake constraints or physics to keyframes."""

    return await _dispatch(bridge, "bake_animation", BakeAnimationParams, params)


async def create_character_skeleton(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Create a basic character armature/skeleton."""

    return await _dispatch(bridge, "create_character_skeleton", CreateCharacterSkeletonParams, params)


async def bind_mesh_to_armature(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Bind a mesh to an armature using automatic weights."""

    return await _dispatch(bridge, "bind_mesh_to_armature", BindMeshToArmatureParams, params)


async def pose_bone(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Translate, rotate or scale a specific bone in an armature."""

    return await _dispatch(bridge, "pose_bone", PoseBoneParams, params)


async def apply_animation_preset(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Apply a procedural animation preset to an object or armature."""

    return await _dispatch(bridge, "apply_animation_preset", ApplyAnimationPresetParams, params)


TOOLS: dict[str, ToolDefinition] = {
    "insert_keyframe": ToolDefinition("insert_keyframe", "Insert a keyframe.", InsertKeyframeParams, insert_keyframe),
    "delete_keyframe": ToolDefinition("delete_keyframe", "Delete keyframes.", DeleteKeyframeParams, delete_keyframe),
    "set_interpolation": ToolDefinition("set_interpolation", "Set F-curve interpolation.", SetInterpolationParams, set_interpolation),
    "list_keyframes": ToolDefinition("list_keyframes", "List object keyframes.", ListKeyframesParams, list_keyframes),
    "create_rotation_animation": ToolDefinition("create_rotation_animation", "Create rotation animation.", CreateRotationAnimationParams, create_rotation_animation),
    "create_path_animation": ToolDefinition("create_path_animation", "Create path animation.", CreatePathAnimationParams, create_path_animation),
    "set_fps": ToolDefinition("set_fps", "Set render FPS.", SetFPSParams, set_fps),
    "bake_animation": ToolDefinition("bake_animation", "Bake animation to keyframes.", BakeAnimationParams, bake_animation),
    "create_character_skeleton": ToolDefinition("create_character_skeleton", "Create a basic character skeleton.", CreateCharacterSkeletonParams, create_character_skeleton),
    "bind_mesh_to_armature": ToolDefinition("bind_mesh_to_armature", "Bind mesh to armature.", BindMeshToArmatureParams, bind_mesh_to_armature),
    "pose_bone": ToolDefinition("pose_bone", "Pose an armature bone.", PoseBoneParams, pose_bone),
    "apply_animation_preset": ToolDefinition("apply_animation_preset", "Apply an animation preset.", ApplyAnimationPresetParams, apply_animation_preset),
}


def register_tools(registry: Any) -> Any:
    """Register all animation tools with a registry."""

    for spec in TOOLS.values():
        _register_tool(registry, spec)
    return registry


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
