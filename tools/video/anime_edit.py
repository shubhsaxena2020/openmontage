"""End-to-end anime and velocity edit orchestration tool.

Combines beat detection, AI frame interpolation, neural anime upscaling,
speed-ramping velocity curves, stylized visual effects, and DSP audio mastering
into a single automated production pipeline.
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

from tools.audio.dsp_master import DspMaster
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
from tools.video.anime_fx import AnimeFX
from tools.video.anime_upscale import AnimeUpscale
from tools.video.beat_sync import BeatSync
from tools.video.frame_interpolate import FrameInterpolate
from tools.video.velocity_ramp import VelocityRamp


class AnimeEdit(BaseTool):
    name = "anime_edit"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "video_composition"
    provider = "openmontage"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["cmd:ffmpeg", "pip:librosa"]
    install_instructions = "Pre-configured with local tools and FFmpeg."
    agent_skills = ["velocity-edit", "beat-sync", "anime-fx", "ffmpeg"]

    capabilities = [
        "end_to_end_velocity_edit",
        "beat_sync_montage",
        "phonk_edit_pipeline",
        "amv_styling",
        "headless_audio_video_remap",
    ]
    supports = {
        "offline": True,
        "vulkan_gpu": True,
        "cpu_graceful_fallback": True,
        "custom_luts": True,
    }
    best_for = [
        "automated anime velocity edits",
        "phonk beat-drop montages",
        "AMV highlight reels",
    ]

    input_schema = {
        "type": "object",
        "required": ["video_path", "audio_path", "output_path"],
        "properties": {
            "video_path": {"type": "string", "description": "Path to source video clip"},
            "audio_path": {"type": "string", "description": "Path to soundtrack / phonk audio"},
            "output_path": {"type": "string", "description": "Path for final edited video"},
            "style": {
                "type": "string",
                "enum": ["velocity", "phonk", "amv", "subtle"],
                "default": "velocity",
                "description": "Visual and kinematic editing preset",
            },
            "interpolate": {
                "type": "boolean",
                "default": False,
                "description": "Enable AI 60fps frame interpolation (RIFE v4)",
            },
            "upscale": {
                "type": "boolean",
                "default": False,
                "description": "Enable neural anime upscaling (Real-CUGAN / Real-ESRGAN)",
            },
            "target_resolution": {
                "type": "string",
                "default": "source",
                "description": 'Target video resolution such as "1080x1920" or "source".',
            },
            "isolate_subject": {
                "type": "boolean",
                "default": False,
                "description": "Enable neural foreground subject isolation",
            },
            "lut": {
                "type": ["string", "null"],
                "default": None,
                "description": "Custom 3D LUT name or file path",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=4096, vram_mb=2048, disk_mb=2000, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=[])
    idempotency_key_fields = [
        "video_path",
        "audio_path",
        "style",
        "interpolate",
        "upscale",
        "target_resolution",
        "lut",
    ]
    side_effects = ["writes final edited video to output_path"]
    user_visible_verification = ["Review output video for beat synchronization, speed curves, and visual styling"]

    def get_status(self) -> ToolStatus:
        if shutil.which("ffmpeg"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    @staticmethod
    def _probe_video_resolution(video_path: str) -> tuple[int, int]:
        width = 0
        height = 0
        try:
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                video_path,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if proc.returncode == 0:
                payload = json.loads(proc.stdout)
                streams = payload.get("streams", [])
                if streams:
                    width = int(streams[0].get("width", 0) or 0)
                    height = int(streams[0].get("height", 0) or 0)
        except Exception:
            pass
        return width, height

    @classmethod
    def _resolve_target_resolution(cls, target_resolution: str, video_path: str) -> str:
        value = (target_resolution or "source").strip().lower()
        if value == "source":
            width, height = cls._probe_video_resolution(video_path)
            if width > 0 and height > 0:
                return f"{width}x{height}"
            return "source"

        parts = value.split("x", 1)
        if len(parts) == 2:
            try:
                width = int(parts[0])
                height = int(parts[1])
                if width > 0 and height > 0:
                    return f"{width}x{height}"
            except ValueError:
                pass
        return "source"

    @staticmethod
    def _probe_output_duration(output_path: str) -> float:
        try:
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                output_path,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if proc.returncode == 0:
                return float(proc.stdout.strip())
        except Exception:
            pass
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        video_path_raw = inputs.get("video_path")
        audio_path_raw = inputs.get("audio_path")
        output_path_raw = inputs.get("output_path")

        if not video_path_raw or not audio_path_raw or not output_path_raw:
            return ToolResult(
                success=False,
                error="Missing required inputs 'video_path', 'audio_path', or 'output_path'",
            )

        video_path = str(Path(video_path_raw).resolve())
        audio_path = str(Path(audio_path_raw).resolve())
        output_path = str(Path(output_path_raw).resolve())

        if not Path(video_path).is_file():
            return ToolResult(success=False, error=f"Video file not found: {video_path}")
        if not Path(audio_path).is_file():
            return ToolResult(success=False, error=f"Audio file not found: {audio_path}")

        style = str(inputs.get("style", "velocity")).lower()
        do_interpolate = bool(inputs.get("interpolate", False))
        do_upscale = bool(inputs.get("upscale", False))
        lut = inputs.get("lut")
        target_resolution = self._resolve_target_resolution(
            str(inputs.get("target_resolution", "source")), video_path
        )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        start_time = time.time()

        stages_run: list[str] = []
        stages_skipped: list[str] = []
        effects_applied: list[str] = []
        engines_used: list[str] = []

        bpm = 120.0
        beat_times: list[float] = []
        downbeat_times: list[float] = []
        suggested_cuts: list[float] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            current_video = video_path

            # --- Stage 1: Beat Tracking ---
            try:
                beat_sync_tool = BeatSync()
                bs_res = beat_sync_tool.execute({"audio_path": audio_path})
                if bs_res.success and bs_res.data:
                    bpm = bs_res.data.get("bpm", 120.0)
                    beat_times = bs_res.data.get("beat_times", [])
                    downbeat_times = bs_res.data.get("downbeat_times", [])
                    suggested_cuts = bs_res.data.get("suggested_cut_times", [])
                    stages_run.append("beat_sync")
                else:
                    stages_skipped.append("beat_sync (fallback defaults)")
            except Exception as exc:
                stages_skipped.append(f"beat_sync ({exc})")

            # --- Stage 2: AI Frame Interpolation (Optional) ---
            if do_interpolate:
                interp_out = str(temp_path / "stage2_interpolated.mp4")
                try:
                    interp_tool = FrameInterpolate()
                    fi_res = interp_tool.execute({
                        "video_path": current_video,
                        "output_path": interp_out,
                        "target_fps": 60,
                    })
                    if fi_res.success and Path(interp_out).is_file():
                        current_video = interp_out
                        stages_run.append("frame_interpolate")
                        engines_used.append(fi_res.data.get("engine", "rife-ncnn"))
                    else:
                        stages_skipped.append("frame_interpolate")
                except Exception as exc:
                    stages_skipped.append(f"frame_interpolate ({exc})")
            else:
                stages_skipped.append("frame_interpolate (disabled)")

            # --- Stage 3: Neural Anime Upscaling (Optional) ---
            if do_upscale:
                upscale_out = str(temp_path / "stage3_upscaled.mp4")
                try:
                    upscale_tool = AnimeUpscale()
                    au_res = upscale_tool.execute({
                        "input_path": current_video,
                        "output_path": upscale_out,
                        "scale": 2,
                        "engine": "realcugan",
                    })
                    if au_res.success and Path(upscale_out).is_file():
                        current_video = upscale_out
                        stages_run.append("anime_upscale")
                        engines_used.append(au_res.data.get("engine", "realcugan"))
                    else:
                        stages_skipped.append("anime_upscale")
                except Exception as exc:
                    stages_skipped.append(f"anime_upscale ({exc})")
            else:
                stages_skipped.append("anime_upscale (disabled)")

            # --- Stage 4: Velocity Speed Ramping ---
            ramp_out = str(temp_path / "stage4_velocity.mp4")
            ramp_points = downbeat_times[:8] if downbeat_times else beat_times[::2][:8]
            try:
                ramp_tool = VelocityRamp()
                vr_res = ramp_tool.execute({
                    "video_path": current_video,
                    "output_path": ramp_out,
                    "slow_factor": 0.25 if style in ("velocity", "phonk") else 0.5,
                    "fast_factor": 2.0 if style in ("velocity", "phonk") else 1.5,
                    "ramp_points": ramp_points,
                    "easing": "expo",
                })
                if vr_res.success and Path(ramp_out).is_file():
                    current_video = ramp_out
                    stages_run.append("velocity_ramp")
                else:
                    stages_skipped.append("velocity_ramp")
            except Exception as exc:
                stages_skipped.append(f"velocity_ramp ({exc})")

            # --- Stage 5: Anime FX Compositor ---
            fx_out = str(temp_path / "stage5_anime_fx.mp4")
            flash_times = downbeat_times[:8] if downbeat_times else beat_times[::2][:8]

            # Style Presets
            if style == "phonk":
                fx_kwargs = {
                    "chromatic_aberration": True,
                    "rgb_split": True,
                    "glow": True,
                    "screen_shake": True,
                    "film_grain": True,
                    "impact_flash": True,
                    "flash_times": flash_times,
                    "lut": lut or "cyberpunk_neon",
                }
            elif style == "amv":
                fx_kwargs = {
                    "glow": True,
                    "film_grain": True,
                    "vignette": True,
                    "letterbox": True,
                    "impact_flash": False,
                    "lut": lut or "cinematic_teal_orange",
                }
            elif style == "subtle":
                fx_kwargs = {
                    "film_grain": True,
                    "vignette": True,
                    "lut": lut or "vintage_warm_film",
                }
            else:  # "velocity" default
                fx_kwargs = {
                    "chromatic_aberration": True,
                    "glow": True,
                    "zoom_punch": True,
                    "screen_shake": True,
                    "film_grain": True,
                    "impact_flash": True,
                    "flash_times": flash_times,
                    "lut": lut or "anime_vibrant",
                }

            try:
                fx_tool = AnimeFX()
                fx_res = fx_tool.execute({
                    "video_path": current_video,
                    "output_path": fx_out,
                    "target_resolution": target_resolution,
                    **fx_kwargs,
                })
                if fx_res.success and Path(fx_out).is_file():
                    current_video = fx_out
                    stages_run.append("anime_fx")
                    effects_applied.extend(fx_res.data.get("effects_applied", []))
                else:
                    stages_skipped.append("anime_fx")
            except Exception as exc:
                stages_skipped.append(f"anime_fx ({exc})")

            # --- Stage 6: Audio DSP Mastering ---
            mastered_audio_out = str(temp_path / "stage6_mastered.wav")
            try:
                dsp_tool = DspMaster()
                dsp_res = dsp_tool.execute({
                    "audio_path": audio_path,
                    "output_path": mastered_audio_out,
                    "bass_gain_db": 6.0 if style in ("velocity", "phonk") else 3.0,
                    "do_compress": True,
                    "do_limit": True,
                    "target_lufs": -9.0,
                })
                if dsp_res.success and Path(mastered_audio_out).is_file():
                    audio_final = mastered_audio_out
                    stages_run.append("dsp_master")
                else:
                    audio_final = audio_path
                    stages_skipped.append("dsp_master")
            except Exception as exc:
                audio_final = audio_path
                stages_skipped.append(f"dsp_master ({exc})")

            # --- Stage 7: Final Muxing & Conforming ---
            mux_cmd = [
                "ffmpeg", "-y",
                "-i", current_video,
                "-i", audio_final,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-r", "60",
                "-movflags", "+faststart",
                "-shortest",
                output_path,
            ]
            try:
                sub_mux = subprocess.run(mux_cmd, capture_output=True, text=True, timeout=300)
                if sub_mux.returncode != 0 or not Path(output_path).is_file() or Path(output_path).stat().st_size == 0:
                    raise RuntimeError(
                        f"ffmpeg mux failed (exit {sub_mux.returncode}): {sub_mux.stderr.strip()}"
                    )
                stages_run.append("final_mux")
            except Exception as exc:
                stages_skipped.append(f"final_mux ({exc})")
                for source_path in (current_video, video_path):
                    if Path(source_path).is_file():
                        shutil.copy(source_path, output_path)
                        break

        elapsed_s = round(time.time() - start_time, 2)
        duration_s = self._probe_output_duration(output_path)

        return ToolResult(
            success=True,
            data={
                "output_path": output_path,
                "bpm": bpm,
                "num_beats": len(beat_times),
                "stages_run": stages_run,
                "stages_skipped": stages_skipped,
                "effects_applied": effects_applied,
                "engines_used": engines_used,
                "duration_s": duration_s,
                "elapsed_s": elapsed_s,
            },
            artifacts=[output_path],
            duration_seconds=elapsed_s,
        )
