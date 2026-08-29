"""Kinetic Studio motion presets.

A small, reusable library of named motion "looks". Each preset describes the *shape* of
the motion so common ramping / zoom / transition patterns can be reused across clips
instead of being hand-tuned every time. Presets are pure data + a pure builder, so they
are fully testable on the VPS (no Remotion / ffmpeg needed to prove the curve shape).

A preset has three facets:
  - ramp:     setup_speed / peak_speed passed to the kinetic ramper
  - zoom:     a subtle Ken-Burns style scale pulse (keyframed), pivot + peak amount
  - transition: an intro (and matching outro) wipe/fade with a frame duration

build_motion_plan() turns a preset + clip geometry into a concrete, frame-accurate plan
that the renderer (Remotion) or the ramper can consume.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Each preset: ramp speeds, zoom pulse, intro transition.
# peak_speed < 1 => slow-motion on drops; setup_speed > 1 => speed-up on setup.
PRESETS: Dict[str, Dict] = {
    "cinematic": {
        "description": "Smooth, gentle ramping with a soft zoom — classic promo feel.",
        "ramp": {"setup_speed": 1.25, "peak_speed": 0.6},
        "zoom": {"mode": "pulse", "amount": 0.06, "pivot": "center"},
        "transition": {"type": "fade", "dur_frames": 18},
    },
    "energetic": {
        "description": "Aggressive speed-up on setup, hard slow-mo on drops — high energy.",
        "ramp": {"setup_speed": 1.8, "peak_speed": 0.35},
        "zoom": {"mode": "punch", "amount": 0.12, "pivot": "subject"},
        "transition": {"type": "wipe", "dur_frames": 10},
    },
    "freeze": {
        "description": "Near-full freeze on every drop (extreme slow-mo) for dramatic lifts.",
        "ramp": {"setup_speed": 1.5, "peak_speed": 0.12},
        "zoom": {"mode": "pulse", "amount": 0.04, "pivot": "center"},
        "transition": {"type": "fade", "dur_frames": 14},
    },
    "subtle": {
        "description": "Minimal ramping — mostly realtime with light beat emphasis.",
        "ramp": {"setup_speed": 1.1, "peak_speed": 0.85},
        "zoom": {"mode": "none", "amount": 0.0, "pivot": "center"},
        "transition": {"type": "fade", "dur_frames": 12},
    },
}


def list_presets() -> List[str]:
    return sorted(PRESETS.keys())


def get_preset(name: str) -> Dict:
    if name not in PRESETS:
        raise KeyError(f"unknown motion preset: {name!r} (have {list_presets()})")
    return PRESETS[name]


def motion_curve(name: str, n_frames: int) -> List[float]:
    """Per-frame *speed factor* (1/speed) for the whole clip, derived purely from the
    preset's ramp params. With no drop signal we model a single setup segment at
    setup_speed and a mid-clip peak window at peak_speed, so the curve shape is
    deterministic and testable. Returns speeds (higher = faster)."""
    p = get_preset(name)["ramp"]
    setup = float(p["setup_speed"])
    peak = float(p["peak_speed"])
    if n_frames <= 0:
        return []
    # peak window sits in the middle third of the clip
    peak_start = max(0, n_frames // 3)
    peak_end = min(n_frames, 2 * n_frames // 3)
    curve = []
    for f in range(n_frames):
        if peak_start <= f < peak_end:
            curve.append(peak)
        else:
            curve.append(setup)
    return curve


def build_motion_plan(name: str, fps: int, n_frames: int,
                      drop_times: Optional[List[float]] = None,
                      width: int = 1080, height: int = 1920) -> Dict:
    """Concrete, frame-accurate motion plan for a preset.

    Returns:
      ramp_segments:  list of {t_start,t_end,speed} (speed>1 faster, <1 slow) — fed to
                      the kinetic ramper (or used directly by the renderer).
      zoom_keyframes: list of {frame, scale} for a Ken-Burns pulse/punch.
      transition:     {type, dur_frames, at: 'intro'|'outro'|'both'}.
    Pure: no rendering, no ffmpeg.
    """
    if name not in PRESETS:
        raise KeyError(f"unknown motion preset: {name!r}")
    p = PRESETS[name]
    ramp = p["ramp"]
    setup = float(ramp["setup_speed"])
    peak = float(ramp["peak_speed"])

    # ramp segments: build from drop times if provided, else the mid-clip peak window
    if drop_times:
        segs = []
        pts = sorted(set(round(t, 3) for t in drop_times if t >= 0))
        last = 0.0
        for dt in pts:
            segs.append({"t_start": last, "t_end": round(dt, 3), "speed": setup})
            segs.append({"t_start": round(dt, 3), "t_end": round(dt + 0.3, 3), "speed": peak})
            last = round(dt + 0.3, 3)
        if last < (n_frames / max(1, fps)):
            segs.append({"t_start": last, "t_end": round(n_frames / max(1, fps), 3), "speed": setup})
    else:
        mid = n_frames / max(1, fps) / 2.0
        segs = [
            {"t_start": 0.0, "t_end": round(mid, 3), "speed": setup},
            {"t_start": round(mid, 3), "t_end": round(mid + 0.3, 3), "speed": peak},
            {"t_start": round(mid + 0.3, 3), "t_end": round(n_frames / max(1, fps), 3), "speed": setup},
        ]

    # zoom keyframes (Ken-Burns). 'pulse' eases in/out; 'punch' snaps then settles.
    zmode = p["zoom"]["mode"]
    zamt = float(p["zoom"]["amount"])
    zoom_keyframes = []
    if zmode == "none" or zamt <= 0:
        zoom_keyframes = [{"frame": 0, "scale": 1.0}, {"frame": max(0, n_frames - 1), "scale": 1.0}]
    else:
        q = max(1, n_frames // 4)
        if zmode == "pulse":
            zoom_keyframes = [
                {"frame": 0, "scale": 1.0},
                {"frame": q, "scale": 1.0 + zamt},
                {"frame": 2 * q, "scale": 1.0},
                {"frame": 3 * q, "scale": 1.0 + zamt},
                {"frame": max(0, n_frames - 1), "scale": 1.0},
            ]
        else:  # punch
            zoom_keyframes = [
                {"frame": 0, "scale": 1.0},
                {"frame": max(1, q // 2), "scale": 1.0 + zamt},
                {"frame": q, "scale": 1.0 + zamt * 0.4},
                {"frame": max(0, n_frames - 1), "scale": 1.0},
            ]

    transition = {"type": p["transition"]["type"],
                  "dur_frames": int(p["transition"]["dur_frames"]),
                  "at": "both"}

    return {
        "preset": name,
        "fps": int(fps),
        "n_frames": int(n_frames),
        "width": int(width),
        "height": int(height),
        "ramp_segments": segs,
        "zoom_keyframes": zoom_keyframes,
        "transition": transition,
    }
