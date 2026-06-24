"""Rendering MCP tools for Blender."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .objects import ToolDefinition, _dispatch, _register_tool

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list[JsonScalar] | dict[str, JsonScalar]


class StrictModel(BaseModel):
    """Base model for strict rendering tool parameters."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SetRenderEngineParams(StrictModel):
    """Input model for ``set_render_engine``."""

    engine: Literal["CYCLES", "EEVEE", "BLENDER_EEVEE_NEXT", "WORKBENCH", "BLENDER_WORKBENCH"] = Field(
        ..., description="Render engine identifier."
    )
    device: Literal["CPU", "GPU"] | None = Field(None, description="Cycles device preference.")


class SetRenderResolutionParams(StrictModel):
    """Input model for ``set_render_resolution``."""

    width: int = Field(..., ge=1, le=32768, description="Output width in pixels.")
    height: int = Field(..., ge=1, le=32768, description="Output height in pixels.")
    percentage: int = Field(100, ge=1, le=100, description="Resolution percentage.")


class SetRenderOutputParams(StrictModel):
    """Input model for ``set_render_output``."""

    output_path: str = Field(..., min_length=1, description="Render output path.")
    file_format: Literal["PNG", "JPEG", "OPEN_EXR", "TIFF", "BMP", "TARGA", "FFMPEG", "MP4"] = Field(
        "PNG", description="Blender image or movie format."
    )
    color_mode: Literal["BW", "RGB", "RGBA"] = Field("RGBA", description="Output color mode.")
    color_depth: Literal["8", "10", "12", "16", "32"] = Field("8", description="Output color depth.")
    compression: int | None = Field(None, ge=0, le=100, description="Optional compression quality.")


class SetCyclesSamplesParams(StrictModel):
    """Input model for ``set_cycles_samples``."""

    render_samples: int = Field(..., ge=1, le=100000, description="Final render samples.")
    viewport_samples: int | None = Field(None, ge=1, le=100000, description="Viewport samples.")
    use_denoising: bool | None = Field(None, description="Enable Cycles denoising.")


class SetEeveeSettingsParams(StrictModel):
    """Input model for ``set_eevee_settings``."""

    ambient_occlusion: bool | None = Field(None, description="Enable ambient occlusion.")
    bloom: bool | None = Field(None, description="Enable bloom where supported.")
    shadows: bool | None = Field(None, description="Enable shadow settings.")
    screen_space_reflections: bool | None = Field(None, description="Enable SSR.")
    settings: dict[str, JsonValue] = Field(default_factory=dict, description="Additional EEVEE settings.")


class RenderImageParams(StrictModel):
    """Input model for ``render_image``."""

    output_path: str | None = Field(None, min_length=1, description="Optional output path override.")
    write_still: bool = Field(True, description="Write rendered image to disk.")
    use_viewport: bool = Field(False, description="Render from current viewport when supported.")
    wait: bool = Field(False, description="Wait for render completion if bridge supports it.")


class RenderAnimationParams(StrictModel):
    """Input model for ``render_animation``."""

    output_path: str | None = Field(None, min_length=1, description="Optional output path override.")
    start_frame: int | None = Field(None, ge=0, description="Optional animation start frame.")
    end_frame: int | None = Field(None, ge=0, description="Optional animation end frame.")
    wait: bool = Field(False, description="Wait for render completion if bridge supports it.")

    @model_validator(mode="after")
    def _ordered(self) -> "RenderAnimationParams":
        if self.start_frame is not None and self.end_frame is not None and self.end_frame < self.start_frame:
            raise ValueError("end_frame must be greater than or equal to start_frame.")
        return self


class SetRenderCameraParams(StrictModel):
    """Input model for ``set_render_camera``."""

    camera_name: str = Field(..., min_length=1, description="Camera object name.")


class AddRenderPassParams(StrictModel):
    """Input model for ``add_render_pass``."""

    pass_name: str = Field(..., min_length=1, description="Render pass name, such as Z or NORMAL.")
    enabled: bool = Field(True, description="Enable or disable the pass.")
    view_layer: str | None = Field(None, description="Optional view layer name.")


class SetColorManagementParams(StrictModel):
    """Input model for ``set_color_management``."""

    display_device: str | None = Field(None, description="Color-management display device.")
    view_transform: str | None = Field(None, description="View transform, such as Filmic.")
    look: str | None = Field(None, description="Look preset.")
    exposure: float | None = Field(None, description="Exposure value.")
    gamma: float | None = Field(None, gt=0.0, description="Gamma value.")

    @field_validator("display_device", "view_transform", "look")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("String values must not be blank.")
        return value


class SetRendererEffectsParams(StrictModel):
    """Input model for ``set_renderer_effects``."""

    bloom: bool = Field(True, description="Enable bloom effect.")
    ambient_occlusion: bool = Field(True, description="Enable ambient occlusion.")
    raytracing: bool = Field(True, description="Enable raytracing (EEVEE Next/Cycles).")


class RenderViewportToBase64Params(StrictModel):
    """Input model for ``render_viewport_to_base64``."""


async def set_render_engine(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set the active render engine."""

    return await _dispatch(bridge, "set_render_engine", SetRenderEngineParams, params)


async def set_render_resolution(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set render resolution and percentage."""

    return await _dispatch(bridge, "set_render_resolution", SetRenderResolutionParams, params)


async def set_render_output(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set render output path and format settings."""

    return await _dispatch(bridge, "set_render_output", SetRenderOutputParams, params)


async def set_cycles_samples(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set Cycles render and viewport sample counts."""

    return await _dispatch(bridge, "set_cycles_samples", SetCyclesSamplesParams, params)


async def set_eevee_settings(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set EEVEE ambient occlusion, bloom, shadow, and SSR settings."""

    return await _dispatch(bridge, "set_eevee_settings", SetEeveeSettingsParams, params)


async def render_image(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Trigger an image render."""

    return await _dispatch(bridge, "render_image", RenderImageParams, params)


async def render_animation(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Trigger an animation render. If output_path is a video/gif, compile it autonomously."""
    import os
    import glob
    import tempfile
    
    params_dict = dict(params or {})
    output_path = params_dict.get("output_path")
    
    if not output_path:
        return await _dispatch(bridge, "render_animation", RenderAnimationParams, params_dict)
        
    ext = os.path.splitext(output_path)[1].lower()
    if ext not in {".mp4", ".gif", ".avi", ".mov", ".mkv"}:
        return await _dispatch(bridge, "render_animation", RenderAnimationParams, params_dict)
        
    # Compile autonomously
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_pattern = os.path.join(temp_dir, "frame_").replace("\\", "/")
        
        try:
            # Force output to PNG sequence inside the temp directory
            await bridge.call_tool("set_render_output", {
                "output_path": temp_pattern,
                "file_format": "PNG",
                "color_mode": "RGBA"
            })
        except Exception:
            pass
            
        render_params = {
            "start_frame": params_dict.get("start_frame"),
            "end_frame": params_dict.get("end_frame"),
            "output_path": temp_pattern
        }
        
        render_result = await _dispatch(bridge, "render_animation", RenderAnimationParams, render_params)
        if not render_result.get("success", True):
            return render_result
            
        try:
            import imageio.v3 as iio
            
            png_files = sorted(glob.glob(os.path.join(temp_dir, "frame_*.png")))
            if not png_files:
                png_files = sorted(glob.glob(os.path.join(temp_dir, "*.png")))
                
            if not png_files:
                return {
                    "success": False,
                    "error": "RenderFailed",
                    "message": "No frames were rendered into the temporary directory.",
                    "code": 500
                }
                
            frames = [iio.imread(f) for f in png_files]
            
            fps = 24
            try:
                scene_info = await bridge.call_tool("get_scene_info", {})
                if scene_info.get("success") and "fps" in scene_info.get("result", {}):
                    fps = scene_info["result"]["fps"]
            except Exception:
                pass
                
            out_dir = os.path.dirname(os.path.abspath(output_path))
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
                
            if ext == ".gif":
                from PIL import Image
                imgs = [Image.open(f) for f in png_files]
                imgs[0].save(
                    output_path,
                    save_all=True,
                    append_images=imgs[1:],
                    duration=int(1000 / fps),
                    loop=0
                )
            else:
                try:
                    iio.imwrite(output_path, frames, fps=fps)
                except Exception:
                    iio.imwrite(output_path, frames, fps=fps, plugin="ffmpeg")
                    
            return {
                "success": True,
                "result": {
                    "status": "rendered_and_compiled",
                    "output_path": output_path,
                    "frames_count": len(png_files),
                    "fps": fps
                }
            }
            
        except Exception as exc:
            return {
                "success": False,
                "error": "VideoCompilationError",
                "message": f"Frames were rendered but compilation failed: {str(exc)}",
                "code": 500
            }


async def set_render_camera(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set the camera used for rendering."""

    return await _dispatch(bridge, "set_render_camera", SetRenderCameraParams, params)


async def add_render_pass(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Enable or disable a render pass on a view layer."""

    return await _dispatch(bridge, "add_render_pass", AddRenderPassParams, params)


async def set_color_management(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set color-management display, view transform, exposure, and gamma."""

    return await _dispatch(bridge, "set_color_management", SetColorManagementParams, params)


async def set_renderer_effects(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Set renderer effects dynamically, adapting to active Blender version."""

    return await _dispatch(bridge, "set_renderer_effects", SetRendererEffectsParams, params)


async def render_viewport_to_base64(bridge: Any, params: Mapping[str, Any] | None = None) -> Any:
    """Render viewport using OpenGL and return Base64 image data."""

    return await _dispatch(bridge, "render_viewport_to_base64", RenderViewportToBase64Params, params)


TOOLS: dict[str, ToolDefinition] = {
    "set_render_engine": ToolDefinition("set_render_engine", "Set render engine.", SetRenderEngineParams, set_render_engine),
    "set_render_resolution": ToolDefinition("set_render_resolution", "Set render resolution.", SetRenderResolutionParams, set_render_resolution),
    "set_render_output": ToolDefinition("set_render_output", "Set render output settings.", SetRenderOutputParams, set_render_output),
    "set_cycles_samples": ToolDefinition("set_cycles_samples", "Set Cycles samples.", SetCyclesSamplesParams, set_cycles_samples),
    "set_eevee_settings": ToolDefinition("set_eevee_settings", "Set EEVEE settings.", SetEeveeSettingsParams, set_eevee_settings),
    "render_image": ToolDefinition("render_image", "Render a still image.", RenderImageParams, render_image),
    "render_animation": ToolDefinition("render_animation", "Render an animation.", RenderAnimationParams, render_animation),
    "set_render_camera": ToolDefinition("set_render_camera", "Set render camera.", SetRenderCameraParams, set_render_camera),
    "add_render_pass": ToolDefinition("add_render_pass", "Enable a render pass.", AddRenderPassParams, add_render_pass),
    "set_color_management": ToolDefinition("set_color_management", "Set color management.", SetColorManagementParams, set_color_management),
    "set_renderer_effects": ToolDefinition("set_renderer_effects", "Set renderer effects dynamically.", SetRendererEffectsParams, set_renderer_effects),
    "render_viewport_to_base64": ToolDefinition("render_viewport_to_base64", "Render viewport to base64.", RenderViewportToBase64Params, render_viewport_to_base64),
}


def register_tools(registry: Any) -> Any:
    """Register all rendering tools with a registry."""

    for spec in TOOLS.values():
        _register_tool(registry, spec)
    return registry


__all__ = ["TOOLS", "register_tools", *TOOLS.keys()]
