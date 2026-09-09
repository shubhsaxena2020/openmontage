"""AI and algorithmic video frame interpolation tool.

Boosts video frame rates to 60fps/120fps for silky slow-motion velocity edits
using RIFE v4 (Vulkan NCNN on Intel Arc) with automatic CPU minterpolate fallback.
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


class FrameInterpolate(BaseTool):
    name = "frame_interpolate"
    version = "0.1.0"
    tier = ToolTier.ENHANCE
    capability = "frame_interpolation"
    provider = "rife-ncnn-vulkan"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL_GPU

    dependencies = ["bin:rife-ncnn-vulkan", "cmd:ffmpeg"]
    install_instructions = "Pre-bundled in tools/bin/rife-ncnn-vulkan-2024 or system FFmpeg."
    agent_skills = ["ffmpeg", "velocity-edit", "frame-interpolation"]

    capabilities = [
        "frame_interpolation",
        "slow_motion_smoothing",
        "fps_upscaling",
        "rife_v4",
    ]
    supports = {
        "offline": True,
        "vulkan_gpu": True,
        "cpu_fallback": True,
    }
    best_for = [
        "60fps anime velocity slow-mo",
        "eliminating stutter from 12/24fps anime cuts",
    ]

    input_schema = {
        "type": "object",
        "required": ["video_path", "output_path"],
        "properties": {
            "video_path": {"type": "string", "description": "Path to input video file"},
            "output_path": {"type": "string", "description": "Path for interpolated video"},
            "target_fps": {"type": "integer", "default": 60, "description": "Target framerate (e.g. 60, 120)"},
            "gpu_index": {"type": "integer", "default": 0, "description": "Vulkan GPU device index (0 for Intel Arc)"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=2048, vram_mb=2048, disk_mb=1000, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=[])
    idempotency_key_fields = ["video_path", "target_fps", "gpu_index"]
    side_effects = ["writes output video to output_path"]
    user_visible_verification = ["Verify output video framerate is 60fps/120fps with smooth intermediate motion"]

    def get_status(self) -> ToolStatus:
        if self._find_rife_exe() or shutil.which("ffmpeg"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    @staticmethod
    def _find_rife_exe() -> Path | None:
        """Find rife-ncnn-vulkan executable in project bins."""
        project_root = Path(__file__).resolve().parent.parent.parent
        candidates = [
            project_root / "tools" / "bin" / "rife-ncnn-vulkan-2024" / "rife-ncnn-vulkan.exe",
            project_root / "tools" / "bin" / "rife-ncnn-vulkan" / "rife-ncnn-vulkan.exe",
        ]
        for cand in candidates:
            if cand.is_file():
                return cand
        which_path = shutil.which("rife-ncnn-vulkan")
        return Path(which_path) if which_path else None

    @staticmethod
    def _probe_video(video_path: str) -> tuple[float, float]:
        """Probe fps and duration using ffprobe."""
        fps = 24.0
        duration = 0.0
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate,duration",
                "-of", "json",
                video_path,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                streams = data.get("streams", [])
                if streams:
                    s = streams[0]
                    r_fps = s.get("r_frame_rate", "24/1")
                    num, _, den = r_fps.partition("/")
                    fps = float(num) / float(den) if den and float(den) > 0 else float(num)
                    duration = float(s.get("duration", 0.0))
        except Exception:
            pass
        return fps, duration

    def _execute_minterpolate(self, video_path: str, output_path: str, target_fps: int) -> bool:
        """Fallback CPU interpolation using FFmpeg minterpolate."""
        vf = f"minterpolate=fps={target_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return res.returncode == 0 and Path(output_path).is_file() and Path(output_path).stat().st_size > 0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        video_path_raw = inputs.get("video_path")
        output_path_raw = inputs.get("output_path")
        if not video_path_raw or not output_path_raw:
            return ToolResult(success=False, error="Missing required input 'video_path' or 'output_path'")

        video_path = str(Path(video_path_raw).resolve())
        output_path = str(Path(output_path_raw).resolve())

        if not Path(video_path).is_file():
            return ToolResult(success=False, error=f"Input video file not found: {video_path}")

        target_fps = min(int(inputs.get("target_fps", 60)), 60)
        gpu_index = int(inputs.get("gpu_index", 0))

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        start_time = time.time()

        rife_exe = self._find_rife_exe()
        engine_used = "minterpolate"

        if rife_exe:
            try:
                src_fps, _ = self._probe_video(video_path)
                with tempfile.TemporaryDirectory() as temp_dir:
                    in_dir = Path(temp_dir) / "in_frames"
                    out_dir = Path(temp_dir) / "out_frames"
                    in_dir.mkdir(parents=True, exist_ok=True)
                    out_dir.mkdir(parents=True, exist_ok=True)

                    # 1. Extract frames from input video
                    extract_cmd = [
                        "ffmpeg", "-y",
                        "-i", video_path,
                        "-qscale:v", "2",
                        str(in_dir / "%08d.png"),
                    ]
                    sub_extract = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=300)
                    input_frames = sorted(in_dir.glob("*.png"))

                    if sub_extract.returncode == 0 and input_frames:
                        total_in = len(input_frames)
                        target_count = int(round(total_in * (target_fps / max(src_fps, 1.0))))
                        if target_count <= total_in:
                            target_count = total_in * 2

                        # 2. Run RIFE NCNN Vulkan
                        rife_cmd = [
                            str(rife_exe),
                            "-i", str(in_dir),
                            "-o", str(out_dir),
                            "-m", "rife-v4.18",
                            "-n", str(target_count),
                            "-g", str(gpu_index),
                        ]
                        sub_rife = subprocess.run(
                            rife_cmd,
                            cwd=str(rife_exe.parent),
                            capture_output=True,
                            text=True,
                            timeout=600,
                        )

                        out_frames = sorted(out_dir.glob("*.png"))
                        if sub_rife.returncode == 0 and out_frames:
                            # 3. Reassemble frames with FFmpeg
                            assemble_cmd = [
                                "ffmpeg", "-y",
                                "-framerate", str(target_fps),
                                "-i", str(out_dir / "%08d.png"),
                                "-i", video_path,
                                "-map", "0:v",
                                "-map", "1:a?",
                                "-c:v", "libx264",
                                "-preset", "medium",
                                "-crf", "20",
                                "-pix_fmt", "yuv420p",
                                "-r", str(target_fps),
                                "-c:a", "aac",
                                "-b:a", "192k",
                                "-movflags", "+faststart",
                                output_path,
                            ]
                            sub_assemble = subprocess.run(assemble_cmd, capture_output=True, text=True, timeout=300)
                            if sub_assemble.returncode == 0 and Path(output_path).is_file():
                                engine_used = "rife-ncnn"
            except Exception:
                engine_used = "minterpolate"

        # Fallback to FFmpeg minterpolate if RIFE was not used or failed
        if engine_used != "rife-ncnn":
            ok = self._execute_minterpolate(video_path, output_path, target_fps)
            if not ok:
                return ToolResult(
                    success=False,
                    error=f"Frame interpolation failed with both RIFE and FFmpeg minterpolate.",
                    duration_seconds=round(time.time() - start_time, 2),
                )
            engine_used = "minterpolate"

        return ToolResult(
            success=True,
            data={
                "output_path": output_path,
                "engine": engine_used,
                "target_fps": target_fps,
            },
            artifacts=[output_path],
            duration_seconds=round(time.time() - start_time, 2),
        )
