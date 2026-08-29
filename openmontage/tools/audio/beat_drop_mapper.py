"""PHASE B.4 — Music beat / drop mapping engine.

Uses librosa to extract:
  - global BPM (+ confidence)
  - beat and downbeat timestamps
  - high-energy "drops" (segments where broadband energy/RMS jumps after a lull)
  - spectral flux peaks (transient onsets)
Output is a timestamped map (JSON) consumed by kinetic_ramper and cut tools.

CPU-only (librosa). Verified against a synthesized track of known BPM in tests.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

from tools.base_tool import BaseTool, ToolResult


def _detect_drops(times: np.ndarray, energy: np.ndarray, pre: float = 0.6,
                  post: float = 0.6, rel_thr: float = 1.25) -> List[Dict[str, Any]]:
    """Energy increases sharply after a quiet pre-window -> a 'drop'."""
    sr_t = times  # already in seconds
    drops = []
    for i in range(len(energy)):
        lo = max(0, i - int(pre / (sr_t[1] - sr_t[0]) if len(sr_t) > 1 else 1))
        hi = min(len(energy), i + int(post / (sr_t[1] - sr_t[0]) if len(sr_t) > 1 else 1))
        pre_e = energy[lo:i].mean() if i > lo else energy[i]
        if pre_e > 1e-6 and energy[i] >= rel_thr * pre_e and energy[i] >= energy[lo:i].max():
            drops.append({"t_sec": round(float(sr_t[i]), 3),
                          "energy": round(float(energy[i]), 4)})
    return drops


class BeatDropMapperTool(BaseTool):
    name = "beat_drop_mapper"
    category = "audio"
    description = (
        "librosa-based BPM, downbeats, high-energy drops and spectral-flux onset map for "
        "music-driven pacing/auto-cut."
    )
    params = {
        "audio_path": {"type": "str", "required": True, "help": "input audio/video"},
        "out_json": {"type": "str", "default": None, "help": "write beat/drop map"},
        "hop_length": {"type": "int", "default": 512},
        "drop_rel_thr": {"type": "float", "default": 1.25,
                         "help": "relative energy jump to flag a drop"},
        "max_frames": {"type": "int", "default": 0, "help": "0=all"},
    }

    def run(self, **p) -> ToolResult:
        import librosa

        y, sr = librosa.load(p["audio_path"], sr=None, mono=True)
        if p["max_frames"]:
            y = y[: int(p["max_frames"])]

        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=p["hop_length"])
        bpm = float(np.atleast_1d(tempo)[0])
        beat_times = librosa.frames_to_time(beats, sr=sr, hop_length=p["hop_length"])

        # downbeats: every 4th beat (assume 4/4); robust enough for fitness/EDM
        downbeat_times = beat_times[::4].tolist() if len(beat_times) > 4 else beat_times.tolist()

        # RMS energy envelope
        S, _ = librosa.effects.trim(y)
        rms = librosa.feature.rms(y=y, hop_length=p["hop_length"])[0]
        rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr,
                                            hop_length=p["hop_length"])
        # normalize
        rms_n = rms / (rms.max() + 1e-9)
        drops = _detect_drops(rms_times, rms_n, rel_thr=p["drop_rel_thr"])

        # spectral flux (onset strength)
        onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=p["hop_length"])
        onset_frames = librosa.onset.onset_detect(onset_envelope=onset, sr=sr,
                                                   hop_length=p["hop_length"])
        onset_times = librosa.frames_to_time(onset_frames, sr=sr,
                                              hop_length=p["hop_length"]).tolist()

        duration = float(len(y) / sr)
        summary = {
            "bpm": round(bpm, 2),
            "beats": len(beat_times),
            "downbeats": len(downbeat_times),
            "drops": len(drops),
            "onsets": len(onset_times),
            "duration_sec": round(duration, 3),
        }
        data = {
            "summary": summary,
            "beat_times": np.round(beat_times, 3).tolist(),
            "downbeat_times": [round(t, 3) for t in downbeat_times],
            "drops": drops,
            "onset_times": [round(t, 3) for t in onset_times],
            "rms": np.round(rms_n, 4).tolist(),
            "rms_times": np.round(rms_times, 3).tolist(),
        }
        artifacts: Dict[str, str] = {}
        if p["out_json"]:
            with open(p["out_json"], "w") as fh:
                json.dump(data, fh)
            artifacts["json"] = p["out_json"]
        return ToolResult(
            ok=True, data=data, artifacts=artifacts,
            metrics={"bpm": round(bpm, 2), "drops": len(drops)},
        )
