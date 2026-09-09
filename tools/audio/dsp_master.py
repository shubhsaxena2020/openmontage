"""DSP audio mastering tool for bass boost, punchy compression, and loudness limiting.

Uses Spotify's Pedalboard DSP engine when available, with automatic FFmpeg
equalizer/compressor/limiter/loudnorm fallback for broadcast/phonk loudness.
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


class DspMaster(BaseTool):
    name = "dsp_master"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "audio_mastering"
    provider = "pedalboard"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["pip:pedalboard", "pip:soundfile", "cmd:ffmpeg"]
    install_instructions = "pip install pedalboard soundfile"
    agent_skills = ["audio-mastering", "ffmpeg"]

    capabilities = [
        "bass_boost",
        "dynamic_compression",
        "brickwall_limiting",
        "loudness_normalization",
        "phonk_mastering",
    ]
    supports = {
        "offline": True,
        "simd_acceleration": True,
        "ffmpeg_fallback": True,
    }
    best_for = [
        "phonk and drift bass boosting",
        "velocity edit audio impact master",
        "punchy 808 transients",
    ]

    input_schema = {
        "type": "object",
        "required": ["audio_path", "output_path"],
        "properties": {
            "audio_path": {"type": "string", "description": "Path to input audio file"},
            "output_path": {"type": "string", "description": "Path for mastered audio file"},
            "bass_gain_db": {"type": "number", "default": 6.0, "description": "Bass shelf boost in dB (110 Hz)"},
            "do_compress": {"type": "boolean", "default": True, "description": "Apply dynamic range compression"},
            "do_limit": {"type": "boolean", "default": True, "description": "Apply brickwall peak limiter"},
            "target_lufs": {"type": "number", "default": -9.0, "description": "Target integrated loudness in LUFS"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2, ram_mb=512, vram_mb=0, disk_mb=100, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=[])
    idempotency_key_fields = ["audio_path", "bass_gain_db", "do_compress", "do_limit", "target_lufs"]
    side_effects = ["writes mastered audio to output_path"]
    user_visible_verification = ["Listen to output audio for punchy bass response and balanced loudness without distortion"]

    def get_status() -> ToolStatus:
        try:
            import pedalboard
            return ToolStatus.AVAILABLE
        except ImportError:
            if shutil.which("ffmpeg"):
                return ToolStatus.AVAILABLE
            return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        audio_path_raw = inputs.get("audio_path")
        output_path_raw = inputs.get("output_path")
        if not audio_path_raw or not output_path_raw:
            return ToolResult(success=False, error="Missing required input 'audio_path' or 'output_path'")

        audio_path = str(Path(audio_path_raw).resolve())
        output_path = str(Path(output_path_raw).resolve())

        if not Path(audio_path).is_file():
            return ToolResult(success=False, error=f"Input audio file not found: {audio_path}")

        bass_gain_db = float(inputs.get("bass_gain_db", 6.0))
        do_compress = bool(inputs.get("do_compress", True))
        do_limit = bool(inputs.get("do_limit", True))
        target_lufs = float(inputs.get("target_lufs", -9.0))

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        start_time = time.time()

        chain: list[str] = []

        # Attempt pedalboard mastering
        pedalboard_ok = False
        try:
            import soundfile as sf
            from pedalboard import Compressor, HighShelfFilter, Limiter, LowShelfFilter, Pedalboard

            audio_data, sr = sf.read(audio_path)
            plugins = []

            if bass_gain_db != 0:
                plugins.append(LowShelfFilter(cutoff_frequency_hz=110.0, gain_db=bass_gain_db))
                chain.append(f"LowShelfFilter(110Hz, +{bass_gain_db}dB)")

            if do_compress:
                plugins.append(Compressor(threshold_db=-18.0, ratio=4.0, attack_ms=5.0, release_ms=50.0))
                chain.append("Compressor(thresh=-18dB, ratio=4)")

            if do_limit:
                plugins.append(Limiter(threshold_db=-1.0, release_ms=100.0))
                chain.append("Limiter(thresh=-1dB)")

            board = Pedalboard(plugins)
            effected = board(audio_data, sr)
            sf.write(output_path, effected, sr)

            if Path(output_path).is_file() and Path(output_path).stat().st_size > 0:
                pedalboard_ok = True
        except Exception:
            pedalboard_ok = False

        # Fallback to FFmpeg mastering
        if not pedalboard_ok:
            chain = []
            af_filters = []
            if bass_gain_db != 0:
                af_filters.append(f"equalizer=f=70:t=q:w=1:g={bass_gain_db}")
                chain.append(f"ffmpeg_equalizer(+{bass_gain_db}dB)")

            if do_compress:
                af_filters.append("acompressor=threshold=-18dB:ratio=4:attack=5:release=50")
                chain.append("ffmpeg_compressor")

            if do_limit:
                af_filters.append("alimiter=limit=0.95")
                chain.append("ffmpeg_limiter")

            af_filters.append(f"loudnorm=I={target_lufs}:TP=-1:LRA=7")
            chain.append(f"ffmpeg_loudnorm({target_lufs}LUFS)")

            af_str = ",".join(af_filters)
            cmd = [
                "ffmpeg", "-y",
                "-i", audio_path,
                "-af", af_str,
                output_path,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0 or not Path(output_path).is_file():
                return ToolResult(
                    success=False,
                    error=f"DSP mastering failed: {proc.stderr}",
                    duration_seconds=round(time.time() - start_time, 2),
                )

        return ToolResult(
            success=True,
            data={
                "output_path": output_path,
                "chain": chain,
                "bass_gain_db": bass_gain_db,
                "target_lufs": target_lufs,
            },
            artifacts=[output_path],
            duration_seconds=round(time.time() - start_time, 2),
        )
