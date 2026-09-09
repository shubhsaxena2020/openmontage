"""Beat synchronization and audio transient analysis tool.

Extracts BPM, beat timestamps, downbeats, and onset times using Librosa
and optional deep-learning beat tracking (beat_this / audio_separator).
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

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


class BeatSync(BaseTool):
    name = "beat_sync"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "audio_analysis"
    provider = "librosa"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["pip:librosa", "pip:soundfile"]
    install_instructions = "pip install librosa soundfile beat-this audio-separator[dml]"
    agent_skills = ["audio-analysis", "beat-sync"]

    capabilities = [
        "beat_detection",
        "tempo_estimation",
        "onset_detection",
        "downbeat_tracking",
        "drum_stem_separation",
    ]
    supports = {
        "offline": True,
        "deep_learning_downbeats": True,
        "stem_isolation": True,
    }
    best_for = [
        "velocity edits",
        "beat-matched video cutting",
        "audio-driven transition timing",
    ]

    input_schema = {
        "type": "object",
        "required": ["audio_path"],
        "properties": {
            "audio_path": {
                "type": "string",
                "description": "Path to input audio or video file with audio track",
            },
            "use_drum_stem": {
                "type": "boolean",
                "default": False,
                "description": "Separate drum stem with audio-separator before tracking",
            },
            "tightness": {
                "type": "number",
                "default": 100.0,
                "description": "Tightness parameter for librosa beat tracking",
            },
            "use_deep": {
                "type": "boolean",
                "default": False,
                "description": "Enable optional deep beat tracking with a 60s timeout",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=1024, vram_mb=0, disk_mb=200, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=[])
    idempotency_key_fields = ["audio_path", "use_drum_stem", "tightness", "use_deep"]
    side_effects = []
    user_visible_verification = ["Verify BPM matches perceived audio tempo"]

    def get_status(self) -> ToolStatus:
        try:
            import librosa
            return ToolStatus.AVAILABLE
        except ImportError:
            return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def _isolate_drums(self, audio_path: str, temp_dir: str) -> str | None:
        """Attempt to extract drum stem via audio-separator CLI or library."""
        try:
            sep_cmd = shutil.which("audio-separator")
            if sep_cmd:
                cmd = [
                    sep_cmd,
                    audio_path,
                    "--output_dir", temp_dir,
                    "--model_filename", "MDX23C-8KFFT-InstVoc_HQ.ckpt",
                    "--output_format", "WAV",
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if res.returncode == 0:
                    for f in Path(temp_dir).glob("*.wav"):
                        if "drum" in f.name.lower() or "percussion" in f.name.lower():
                            return str(f)
        except Exception:
            pass
        return None

    def _decode_to_wav(self, source_path: str, temp_dir: str) -> str:
        """Decode arbitrary audio/video input to a mono 44.1kHz WAV for librosa."""
        src = Path(source_path)
        if src.suffix.lower() in {".wav", ".wave"} and src.is_file():
            return str(src)

        wav_path = Path(temp_dir) / f"{src.stem}.analysis.wav"
        cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(src),
            "-ar",
            "44100",
            "-ac",
            "1",
            str(wav_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0 or not wav_path.is_file():
            raise RuntimeError(
                f"ffmpeg decode failed for librosa input (exit {proc.returncode}): {proc.stderr.strip()}"
            )
        return str(wav_path)

    def _beat_this_downbeats(self, analysis_path: str) -> list[float]:
        """Run beat_this in a subprocess so model hangs cannot stall the tool."""
        script = r"""
import json
import sys
import numpy as np
from beat_this.inference import File2Beats

path = sys.argv[1]
tracker = File2Beats()
db_res = tracker(path)
downbeats = []
if hasattr(db_res, "downbeats"):
    downbeats = [float(t) for t in db_res.downbeats]
elif isinstance(db_res, tuple) and len(db_res) >= 2:
    downbeats = [float(t) for t in db_res[1]]
elif isinstance(db_res, np.ndarray):
    downbeats = [float(t) for t in db_res]
print(json.dumps({"downbeats": downbeats}))
"""
        proc = subprocess.run(
            [sys.executable, "-c", script, analysis_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.strip() or proc.stdout.strip() or "beat_this subprocess failed"
            raise RuntimeError(stderr)

        payload = json.loads(proc.stdout.strip() or "{}")
        return [float(t) for t in payload.get("downbeats", [])]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        audio_path_raw = inputs.get("audio_path")
        if not audio_path_raw:
            return ToolResult(success=False, error="Missing required input 'audio_path'")

        audio_path = str(Path(audio_path_raw).resolve())
        if not Path(audio_path).is_file():
            return ToolResult(success=False, error=f"Audio file not found: {audio_path}")

        use_drum_stem = bool(inputs.get("use_drum_stem", False))
        tightness = float(inputs.get("tightness", 100.0))
        use_deep = bool(inputs.get("use_deep", False))

        start_time = time.time()

        try:
            import librosa
        except ImportError as exc:
            return ToolResult(success=False, error=f"librosa is not installed: {exc}")

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                work_path = audio_path

                if use_drum_stem:
                    drum_stem = self._isolate_drums(audio_path, temp_dir)
                    if drum_stem:
                        work_path = drum_stem

                analysis_path = self._decode_to_wav(work_path, temp_dir)

                # Load audio using librosa
                y, sr = librosa.load(analysis_path, sr=44100, mono=True)
                if len(y) == 0:
                    return ToolResult(success=False, error="Loaded audio is empty")

                # 1. Beat tracking and tempo estimation
                tempo, beats = librosa.beat.beat_track(y=y, sr=sr, tightness=tightness)
                if isinstance(tempo, np.ndarray):
                    bpm = float(tempo.item(0)) if tempo.size > 0 else 120.0
                else:
                    bpm = float(tempo)

                beat_times = [round(float(t), 3) for t in librosa.frames_to_time(beats, sr=sr)]

                # 2. Onset detection via spectral flux + peak picking
                onset_env = librosa.onset.onset_strength(y=y, sr=sr)
                onset_frames = librosa.util.peak_pick(
                    onset_env,
                    pre_max=3,
                    post_max=3,
                    pre_avg=3,
                    post_avg=5,
                    delta=0.5,
                    wait=10,
                )
                onset_times = [round(float(t), 3) for t in librosa.frames_to_time(onset_frames, sr=sr)]

                # 3. Downbeat detection via optional deep tracker, with a hard timeout.
                downbeat_times: list[float] = []
                beat_engine = "librosa"
                if use_deep:
                    try:
                        def run_deep_tracker() -> list[float]:
                            return self._beat_this_downbeats(analysis_path)

                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(run_deep_tracker)
                            downbeat_times = [round(float(t), 3) for t in future.result(timeout=60)]

                        if downbeat_times:
                            beat_engine = "beat_this"
                    except Exception:
                        beat_engine = "librosa (deep timed out)"

                if not downbeat_times:
                    # Fallback: estimate 4/4 bar downbeats (every 4th beat)
                    if beat_times:
                        downbeat_times = beat_times[::4]

                # 4. Suggested cut times (prefer downbeats, or alternate beats + key onsets)
                if downbeat_times and len(downbeat_times) >= 4:
                    suggested_cut_times = downbeat_times
                elif len(beat_times) >= 2:
                    suggested_cut_times = beat_times[::2]
                else:
                    suggested_cut_times = beat_times

                result_data = {
                    "bpm": round(bpm, 2),
                    "beat_times": beat_times,
                    "downbeat_times": downbeat_times,
                    "onset_times": onset_times,
                    "suggested_cut_times": suggested_cut_times,
                    "total_beats": len(beat_times),
                    "total_onsets": len(onset_times),
                    "audio_duration_s": round(float(librosa.get_duration(y=y, sr=sr)), 3),
                    "beat_engine": beat_engine,
                }

                return ToolResult(
                    success=True,
                    data=result_data,
                    duration_seconds=round(time.time() - start_time, 2),
                )

        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Beat tracking failed: {exc}",
                duration_seconds=round(time.time() - start_time, 2),
            )
