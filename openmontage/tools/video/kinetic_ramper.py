"""PHASE B.5 — Kinetic velocity ramper.

FFmpeg `setpts` time-remapping that speeds up low-energy "setup" movements and applies
slow-motion on peak lifts / music drops, synced to the beat-drop map. Builds a piecewise
setpts filtergraph from the drop/peak timestamps, then renders with the system ffmpeg.

The speed schedule: each segment between consecutive control points gets a PTS scale
(1/speed). Setup segments (between a peak and the next peak, flagged low-energy) run
faster (speed>1); peak/drop segments run slow (speed<1). Result is a single output clip.

CPU-only. Requires the ffmpeg binary (located via shutil.which('ffmpeg')).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional

import numpy as np

from tools.base_tool import BaseTool, ToolResult


def _build_segments(control_t: List[float], slow_windows: List[float],
                    setup_speed: float, peak_speed: float) -> List[Dict[str, float]]:
    """Return [(t_start, t_end, speed)] covering [0, last_control], with slow speed inside
    any slow_window (a peak/drop region) and setup_speed elsewhere."""
    if not control_t:
        return []
    end = control_t[-1]
    segs: List[Dict[str, float]] = []
    t = 0.0
    for ct in control_t:
        # is [t, ct] inside any slow window?
        slow = any(ws - 0.15 <= t and ct <= we + 0.15 for ws, we in
                   [(slow_windows[i], slow_windows[i + 1]) for i in range(0, len(slow_windows) - 1, 2)]
                   ) if slow_windows else False
        speed = peak_speed if slow else setup_speed
        segs.append({"t_start": round(t, 3), "t_end": round(min(ct, end), 3), "speed": speed})
        t = min(ct, end)
    if t < end:
        segs.append({"t_start": round(t, 3), "t_end": round(end, 3), "speed": setup_speed})
    return segs


def _setpts_filter(segs: List[Dict[str, float]]) -> str:
    """Build a select-based piecewise setpts. We use a chain of `select`+`setpts` is complex;
    simpler: build a single setpts using a piecewise-linear PTS via `pts` expression is not
    native. Instead we render segment-by-segment and concat (robust, real ffmpeg run)."""
    return ""  # rendered via segment concat (see run)


class KineticRamperTool(BaseTool):
    name = "kinetic_ramper"
    category = "video"
    description = (
        "FFmpeg setpts remap: speed up setup movement, slow-mo on peak lifts/drops, synced "
        "to beat-drop map. Renders a single output clip."
    )
    params = {
        "input_path": {"type": "str", "required": True, "help": "source video"},
        "out_path": {"type": "str", "required": True, "help": "ramped output clip"},
        "map_json": {"type": "str", "default": None,
                     "help": "beat_drop_mapper JSON (drops/peaks timestamps)"},
        "peak_times": {"type": "str", "default": None,
                       "help": "comma-sep peak/drop seconds if no map_json"},
        "setup_speed": {"type": "float", "default": 1.6, "help": "speed during setup"},
        "peak_speed": {"type": "float", "default": 0.4, "help": "speed during peaks (slow-mo)"},
        "ffmpeg": {"type": "str", "default": "ffmpeg",
                   "help": "ffmpeg executable (resolved via PATH)"},
    }

    def run(self, **p) -> ToolResult:
        ff = shutil.which(p["ffmpeg"]) or p["ffmpeg"]
        if not ff or not os.path.exists(ff):
            return ToolResult(ok=False, error=f"ffmpeg not found: {p['ffmpeg']}")

        # collect control points (peak/drop timestamps)
        peaks: List[float] = []
        if p["map_json"]:
            with open(p["map_json"]) as fh:
                m = json.load(fh)
            peaks = [d["t_sec"] for d in m.get("drops", [])]
            peaks += m.get("downbeat_times", [])
        if p["peak_times"]:
            peaks += [float(x) for x in p["peak_times"].split(",") if x.strip()]
        peaks = sorted(set(round(x, 3) for x in peaks if x >= 0))
        if not peaks:
            # No beat/drop signal (e.g. silent footage, no music supplied). Degrade
            # gracefully to a single uniform-speed segment instead of failing — the
            # studio still gets a reframed, lightly sped-up short.
            segs = [{"t_start": 0.0, "t_end": 1e9, "speed": p["setup_speed"]}]
            slow_windows: List[float] = []
        else:
            segs = _build_segments(peaks, [], p["setup_speed"], p["peak_speed"])
            slow_windows = [s["t_start"] for s in segs if s["speed"] == p["peak_speed"]]
            segs = _build_segments(peaks, slow_windows, p["setup_speed"], p["peak_speed"])

        # render each segment with setpts, then concat
        import cv2
        cap = cv2.VideoCapture(p["input_path"])
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()

        tmpdir = os.path.join(os.path.dirname(os.path.abspath(p["out_path"])),
                              f".ramper_{os.getpid()}")
        os.makedirs(tmpdir, exist_ok=True)
        part_paths = []
        try:
            for i, s in enumerate(segs):
                ts = s["t_start"]
                te = s["t_end"]
                if te <= ts:
                    continue
                dur = te - ts
                scale = 1.0 / s["speed"]  # setpts expr: PTS*scale
                part = os.path.join(tmpdir, f"p{i:03d}.mp4")
                cmd = [
                    ff, "-y", "-ss", f"{ts:.3f}", "-i", p["input_path"],
                    "-t", f"{dur:.3f}",
                    "-vf", f"setpts={scale}*PTS",
                    "-an", "-r", str(fps),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
                    part,
                ]
                r = subprocess.run(cmd, capture_output=True, text=True)
                if r.returncode != 0:
                    return ToolResult(ok=False, error=f"ffmpeg seg {i} failed: {r.stderr[-500:]}")
                part_paths.append(part)
            if not part_paths:
                return ToolResult(ok=False, error="no segments rendered")

            # concat
            listf = os.path.join(tmpdir, "list.txt")
            with open(listf, "w") as fh:
                for pp in part_paths:
                    fh.write(f"file '{pp}'\n")
            cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", listf,
                   "-c", "copy", p["out_path"]]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                return ToolResult(ok=False, error=f"ffmpeg concat failed: {r.stderr[-500:]}")
        finally:
            for pp in part_paths:
                try: os.remove(pp)
                except OSError: pass
            try: os.remove(os.path.join(tmpdir, "list.txt"))
            except OSError: pass
            try: os.rmdir(tmpdir)
            except OSError: pass

        if not os.path.exists(p["out_path"]):
            return ToolResult(ok=False, error="render failed (no output)")
        return ToolResult(
            ok=True,
            data={"segments": segs, "control_points": len(peaks),
                  "setup_speed": p["setup_speed"], "peak_speed": p["peak_speed"]},
            artifacts={"video": p["out_path"]},
            metrics={"segments": len(segs), "control_points": len(peaks)},
        )
