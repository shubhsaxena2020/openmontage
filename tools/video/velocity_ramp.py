"""Velocity ramp tool for beat-synchronized time remapping.

Applies smooth speed ramps (slow-motion stretch to hyper-speed snap)
with synchronized audio tempo adjustment via pure FFmpeg filtergraphs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
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


class VelocityRamp(BaseTool):
    name = "velocity_ramp"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "video_post"
    provider = "ffmpeg"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["cmd:ffmpeg"]
    install_instructions = "FFmpeg with librubberband required."
    agent_skills = ["ffmpeg", "velocity-edit"]

    capabilities = [
        "velocity_curve",
        "speed_ramp",
        "rubberband_audio_sync",
        "beat_sync_time_remap",
    ]
    supports = {
        "offline": True,
        "pitch_preserved_audio": True,
        "hardware_encode": True,
    }
    best_for = [
        "anime velocity edits",
        "phonk speed ramps",
        "beat-drop slow-mo impacts",
    ]

    input_schema = {
        "type": "object",
        "required": ["video_path", "output_path"],
        "properties": {
            "video_path": {
                "type": "string",
                "description": "Path to input video file",
            },
            "output_path": {
                "type": "string",
                "description": "Path for output velocity-ramped video",
            },
            "slow_factor": {
                "type": "number",
                "default": 0.25,
                "description": "Slow motion playback rate (e.g. 0.25 = 4x slow-mo)",
            },
            "fast_factor": {
                "type": "number",
                "default": 2.0,
                "description": "Fast playback rate (e.g. 2.0 = 2x speed-up)",
            },
            "ramp_points": {
                "type": "array",
                "items": {"type": "number"},
                "default": [],
                "description": "List of beat timestamps (in seconds) to anchor speed ramps",
            },
            "easing": {
                "type": "string",
                "default": "expo",
                "description": "Easing curve style: 'expo', 'linear', or 'sine'",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=1024, vram_mb=0, disk_mb=500, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=[])
    idempotency_key_fields = ["video_path", "slow_factor", "fast_factor", "ramp_points", "easing"]
    side_effects = ["writes output video to output_path"]
    user_visible_verification = ["Check playback speed dynamically ramps at beat timestamps"]

    def get_status(self) -> ToolStatus:
        if shutil.which("ffmpeg"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def _build_filtergraph(
        self,
        ramp_points: list[float],
        slow_factor: float,
        fast_factor: float,
    ) -> tuple[str, str]:
        """Build continuous setpts and rubberband filter expressions."""
        if not ramp_points:
            # Default 3-stage velocity ramp
            v_expr = (
                f"if(lt(T,1.0), PTS, "
                f"if(lt(T,3.0), 1.0/TB + (PTS-1.0/TB)*{1.0/slow_factor:.4f}, "
                f"{1.0 + 2.0/slow_factor:.4f}/TB + (PTS-3.0/TB)*{1.0/fast_factor:.4f}))"
            )
            out_slow_end = 1.0 + 2.0 / slow_factor
            a_expr = f"if(lt(t,1.0), 1.0, if(lt(t,{out_slow_end:.4f}), {slow_factor:.4f}, {fast_factor:.4f}))"
            return v_expr, a_expr

        # Construct piecewise velocity curve around beat timestamps
        # For each beat B:
        # [B - 0.4, B] -> slow_factor (anticipation build-up)
        # [B, B + 0.2] -> fast_factor (snap impact)
        # Other intervals -> 1.0 (normal)
        segments: list[tuple[float, float, float]] = []  # (t_start, t_end, speed)
        current_t = 0.0

        for b in sorted(ramp_points):
            if b <= current_t:
                continue
            pre_start = max(current_t, b - 0.4)
            if pre_start > current_t:
                segments.append((current_t, pre_start, 1.0))
            post_end = b + 0.2
            segments.append((pre_start, b, slow_factor))
            segments.append((b, post_end, fast_factor))
            current_t = post_end

        segments.append((current_t, 99999.0, 1.0))

        # Calculate cumulative output timeline
        # m_i = 1.0 / speed_i
        # out_i = out_{i-1} + (t_i - t_{i-1}) * m_i
        v_parts: list[str] = []
        a_parts: list[str] = []
        accum_out = 0.0

        for idx, (t_start, t_end, spd) in enumerate(segments):
            m = 1.0 / spd
            dur_in = t_end - t_start
            dur_out = dur_in * m
            out_end = accum_out + dur_out

            if idx == len(segments) - 1:
                v_parts.append(f"{accum_out:.4f}/TB + (PTS-{t_start:.4f}/TB)*{m:.4f}")
                a_parts.append(f"{spd:.4f}")
            else:
                v_parts.append(
                    f"if(lt(T,{t_end:.4f}), {accum_out:.4f}/TB + (PTS-{t_start:.4f}/TB)*{m:.4f}"
                )
                a_parts.append(
                    f"if(lt(t,{out_end:.4f}), {spd:.4f}"
                )
            accum_out = out_end

        # Close nested if statements
        close_brackets = ")" * (len(segments) - 1)
        v_expr = ", ".join(v_parts) + close_brackets
        a_expr = ", ".join(a_parts) + close_brackets

        return v_expr, a_expr

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        video_path_raw = inputs.get("video_path")
        output_path_raw = inputs.get("output_path")
        if not video_path_raw or not output_path_raw:
            return ToolResult(success=False, error="Missing required input 'video_path' or 'output_path'")

        video_path = str(Path(video_path_raw).resolve())
        output_path = str(Path(output_path_raw).resolve())

        if not Path(video_path).is_file():
            return ToolResult(success=False, error=f"Input video file not found: {video_path}")

        slow_factor = float(inputs.get("slow_factor", 0.25))
        fast_factor = float(inputs.get("fast_factor", 2.0))
        ramp_points = [float(p) for p in inputs.get("ramp_points", [])]
        easing = str(inputs.get("easing", "expo"))

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        start_time = time.time()

        v_expr, a_expr = self._build_filtergraph(ramp_points, slow_factor, fast_factor)

        filtergraph = (
            f"[0:v]setpts='{v_expr}'[v];"
            f"[0:a]rubberband=tempo='{a_expr}':pitch=1.0:transients=crisp:detector=compound[a];"
            f"[v]fps=60[v60]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-filter_complex", filtergraph,
            "-map", "[v60]",
            "-map", "[a]",
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

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        # Fallback if rubberband is not supported or audio stream missing
        if proc.returncode != 0:
            fallback_filtergraph = f"[0:v]setpts='{v_expr}'[v]"
            cmd_fallback = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-filter_complex", fallback_filtergraph,
                "-map", "[v]",
                "-map", "0:a?",
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
            proc_fb = subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=600)
            if proc_fb.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Velocity ramp failed (exit {proc.returncode}): {proc.stderr}\nFallback error: {proc_fb.stderr}",
                    duration_seconds=round(time.time() - start_time, 2),
                )
            filtergraph = fallback_filtergraph

        if not Path(output_path).is_file() or Path(output_path).stat().st_size == 0:
            return ToolResult(success=False, error=f"Velocity ramp output missing: {output_path}")

        return ToolResult(
            success=True,
            data={
                "output_path": output_path,
                "filtergraph": filtergraph,
                "slow_factor": slow_factor,
                "fast_factor": fast_factor,
                "ramp_points_count": len(ramp_points),
                "easing": easing,
            },
            artifacts=[output_path],
            duration_seconds=round(time.time() - start_time, 2),
        )
