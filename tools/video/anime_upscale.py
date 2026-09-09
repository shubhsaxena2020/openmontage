"""Anime super-resolution and video/image upscaler tool.

Provides neural upscaling using Real-CUGAN, Real-ESRGAN, and Waifu2x
(Vulkan NCNN on Intel Arc) with automatic FFmpeg Lanczos CPU fallback.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class AnimeUpscale(BaseTool):
    name = "anime_upscale"
    version = "0.1.0"
    tier = ToolTier.ENHANCE
    capability = "upscale"
    provider = "realcugan-ncnn-vulkan"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL_GPU

    dependencies = ["bin:realcugan-ncnn-vulkan", "cmd:ffmpeg"]
    install_instructions = "Pre-bundled in tools/bin/realcugan-ncnn-vulkan, realesrgan-ncnn-vulkan, waifu2x-ncnn-vulkan."
    agent_skills = ["ffmpeg", "anime-upscale"]

    capabilities = [
        "anime_super_resolution",
        "realcugan_upscale",
        "realesrgan_upscale",
        "waifu2x_upscale",
        "video_upscaling",
        "image_upscaling",
    ]
    supports = {
        "offline": True,
        "vulkan_gpu": True,
        "cpu_fallback": True,
        "images_and_video": True,
    }
    best_for = [
        "anime line art sharpening",
        "upscaling 720p/1080p to 4K",
        "artifact removal on 2D illustration",
    ]

    input_schema = {
        "type": "object",
        "required": ["input_path", "output_path"],
        "properties": {
            "input_path": {"type": "string", "description": "Path to input video or image file"},
            "output_path": {"type": "string", "description": "Path for upscaled output file"},
            "scale": {"type": "integer", "default": 2, "description": "Upscale multiplier (e.g. 2, 4)"},
            "engine": {
                "type": "string",
                "enum": ["realcugan", "realesrgan", "waifu2x"],
                "default": "realcugan",
                "description": "Neural upscaling engine to utilize",
            },
            "gpu_index": {"type": "integer", "default": 0, "description": "Vulkan GPU device index (0 for Intel Arc)"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=2048, vram_mb=2048, disk_mb=1000, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=[])
    idempotency_key_fields = ["input_path", "scale", "engine", "gpu_index"]
    side_effects = ["writes upscaled file to output_path"]
    user_visible_verification = ["Check resolution is scaled by target factor and line sharpness is enhanced"]

    def get_status(self) -> ToolStatus:
        project_root = Path(__file__).resolve().parent.parent.parent
        bin_dir = project_root / "tools" / "bin"
        if (bin_dir / "realcugan-ncnn-vulkan" / "realcugan-ncnn-vulkan.exe").is_file() or shutil.which("ffmpeg"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    @staticmethod
    def _find_engine_exe(engine: str) -> tuple[Path | None, list[str]]:
        """Find executable and default arguments for the chosen upscaling engine."""
        project_root = Path(__file__).resolve().parent.parent.parent
        bin_dir = project_root / "tools" / "bin"

        if engine == "realesrgan":
            exe = bin_dir / "realesrgan-ncnn-vulkan" / "realesrgan-ncnn-vulkan.exe"
            default_args = ["-n", "realesr-animevideov3"]
        elif engine == "waifu2x":
            exe = bin_dir / "waifu2x-ncnn-vulkan" / "waifu2x-ncnn-vulkan.exe"
            default_args = ["-m", "models-cunet"]
        else:  # realcugan default
            exe = bin_dir / "realcugan-ncnn-vulkan" / "realcugan-ncnn-vulkan.exe"
            default_args = ["-n", "1", "-m", "models-se"]

        if exe.is_file():
            return exe, default_args
        which_path = shutil.which(f"{engine}-ncnn-vulkan")
        if which_path:
            return Path(which_path), default_args
        return None, default_args

    @staticmethod
    def _is_image_file(path_str: str) -> bool:
        ext = Path(path_str).suffix.lower()
        return ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}

    @staticmethod
    def _probe_fps(video_path: str) -> float:
        fps = 24.0
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "json",
                video_path,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                streams = data.get("streams", [])
                if streams:
                    r_fps = streams[0].get("r_frame_rate", "24/1")
                    num, _, den = r_fps.partition("/")
                    fps = float(num) / float(den) if den and float(den) > 0 else float(num)
        except Exception:
            pass
        return fps

    def _execute_ffmpeg_lanczos(self, input_path: str, output_path: str, scale: int, is_image: bool) -> bool:
        """CPU fallback upscaler using high-quality FFmpeg Lanczos resampling."""
        vf = f"scale=iw*{scale}:ih*{scale}:flags=lanczos"
        if is_image:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", vf, output_path]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", vf,
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-r", "60",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                output_path,
            ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return res.returncode == 0 and Path(output_path).is_file() and Path(output_path).stat().st_size > 0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        input_path_raw = inputs.get("input_path")
        output_path_raw = inputs.get("output_path")
        if not input_path_raw or not output_path_raw:
            return ToolResult(success=False, error="Missing required input 'input_path' or 'output_path'")

        input_path = str(Path(input_path_raw).resolve())
        output_path = str(Path(output_path_raw).resolve())

        if not Path(input_path).is_file():
            return ToolResult(success=False, error=f"Input file not found: {input_path}")

        scale = int(inputs.get("scale", 2))
        engine = str(inputs.get("engine", "realcugan")).lower()
        gpu_index = int(inputs.get("gpu_index", 0))

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        start_time = time.time()

        is_image = self._is_image_file(input_path)
        exe_path, extra_args = self._find_engine_exe(engine)
        engine_used = "ffmpeg-lanczos"

        if exe_path:
            try:
                if is_image:
                    # Single image upscale
                    cmd = [
                        str(exe_path),
                        "-i", input_path,
                        "-o", output_path,
                        "-s", str(scale),
                        "-g", str(gpu_index),
                        *extra_args,
                    ]
                    sub = subprocess.run(
                        cmd,
                        cwd=str(exe_path.parent),
                        capture_output=True,
                        text=True,
                        timeout=180,
                    )
                    if sub.returncode == 0 and Path(output_path).is_file():
                        engine_used = engine
                else:
                    # Video upscale via frame decomposition
                    src_fps = self._probe_fps(input_path)
                    with tempfile.TemporaryDirectory() as temp_dir:
                        in_dir = Path(temp_dir) / "in_frames"
                        out_dir = Path(temp_dir) / "out_frames"
                        in_dir.mkdir(parents=True, exist_ok=True)
                        out_dir.mkdir(parents=True, exist_ok=True)

                        # Extract frames
                        extract_cmd = [
                            "ffmpeg", "-y",
                            "-i", input_path,
                            "-qscale:v", "2",
                            str(in_dir / "%08d.png"),
                        ]
                        sub_extract = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=300)
                        input_frames = sorted(in_dir.glob("*.png"))

                        if sub_extract.returncode == 0 and input_frames:
                            # Run upscaler
                            cmd = [
                                str(exe_path),
                                "-i", str(in_dir),
                                "-o", str(out_dir),
                                "-s", str(scale),
                                "-g", str(gpu_index),
                                *extra_args,
                            ]
                            sub_upscale = subprocess.run(
                                cmd,
                                cwd=str(exe_path.parent),
                                capture_output=True,
                                text=True,
                                timeout=600,
                            )
                            out_frames = sorted(out_dir.glob("*.png"))

                            if sub_upscale.returncode == 0 and out_frames:
                                # Reassemble video
                                assemble_cmd = [
                                    "ffmpeg", "-y",
                                    "-framerate", str(src_fps),
                                    "-i", str(out_dir / "%08d.png"),
                                    "-i", input_path,
                                    "-map", "0:v",
                                    "-map", "1:a?",
                                    "-c:v", "libx264",
                                    "-preset", "medium",
                                    "-crf", "20",
                                    "-pix_fmt", "yuv420p",
                                    "-r", "60",
                                    "-c:a", "aac",
                                    "-b:a", "192k",
                                    "-movflags", "+faststart",
                                    output_path,
                                ]
                                sub_assemble = subprocess.run(assemble_cmd, capture_output=True, text=True, timeout=300)
                                if sub_assemble.returncode == 0 and Path(output_path).is_file():
                                    engine_used = engine
            except Exception:
                engine_used = "ffmpeg-lanczos"

        # Fallback to FFmpeg Lanczos if GPU engine was not used or failed
        if engine_used == "ffmpeg-lanczos":
            ok = self._execute_ffmpeg_lanczos(input_path, output_path, scale, is_image)
            if not ok:
                return ToolResult(
                    success=False,
                    error=f"Anime upscaling failed with {engine} and FFmpeg fallback.",
                    duration_seconds=round(time.time() - start_time, 2),
                )

        return ToolResult(
            success=True,
            data={
                "output_path": output_path,
                "engine": engine_used,
                "scale": scale,
                "is_image": is_image,
            },
            artifacts=[output_path],
            duration_seconds=round(time.time() - start_time, 2),
        )
