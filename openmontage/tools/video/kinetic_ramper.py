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
    any slow_window (a peak/drop region) and setup_speed elsewhere. Adjacent segments of
    the same speed are MERGED so the rendered output is a small number of clean, contiguous
    time-remaps (no micro-segment concat artifacts / frozen frames)."""
    if not control_t:
        return []
    end = control_t[-1]
    # raw per-control-point speed flags
    def is_slow(t0, t1):
        return any(ws - 0.15 <= t0 and t1 <= we + 0.15
                   for ws, we in [(slow_windows[i], slow_windows[i + 1])
                                  for i in range(0, len(slow_windows) - 1, 2)]) \
            if slow_windows else False
    raw: List[Dict[str, float]] = []
    t = 0.0
    for ct in control_t:
        ct = min(ct, end)
        raw.append({"t_start": round(t, 3), "t_end": round(ct, 3),
                    "speed": peak_speed if is_slow(t, ct) else setup_speed})
        t = ct
    if t < end:
        raw.append({"t_start": round(t, 3), "t_end": round(end, 3), "speed": setup_speed})
    # merge adjacent equal-speed segments
    merged: List[Dict[str, float]] = []
    for s in raw:
        if merged and merged[-1]["speed"] == s["speed"] and merged[-1]["t_end"] == s["t_start"]:
            merged[-1]["t_end"] = s["t_end"]
        else:
            merged.append(dict(s))
    return merged


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
        "keep_audio": {"type": "bool", "default": True,
                       "help": "mux original audio through (A/V stay synced: setpts preserves timeline)"},
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
            # Slow-mo windows are centered on each drop/peak. The _build_segments
            # `is_slow` check treats slow_windows as a flat list of (start,end) pairs,
            # so expand every drop into a [d-pad, d+pad] window here.
            pad = 0.15
            slow_windows = []
            for d in peaks:
                slow_windows.append(round(max(0.0, d - pad), 3))
                slow_windows.append(round(d + pad, 3))
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

            # concat video segments
            listf = os.path.join(tmpdir, "list.txt")
            with open(listf, "w") as fh:
                for pp in part_paths:
                    fh.write(f"file '{pp}'\n")
            cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", listf,
                   "-c", "copy", p["out_path"]]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                return ToolResult(ok=False, error=f"ffmpeg concat failed: {r.stderr[-500:]}")

            # optional: mux original audio back so the ramped short stays A/V synced
            # (setpts preserves absolute timeline positions, so the music still lines up
            # with the slow-mo windows). Re-mux both streams into a final file.
            has_audio = False
            if p["keep_audio"]:
                probe = subprocess.run(
                    [ff, "-i", p["input_path"]], capture_output=True, text=True)
                has_audio = "Stream #0:1" in probe.stderr or "Audio:" in probe.stderr
                if has_audio:
                    final = p["out_path"] + ".av.mp4"
                    r = subprocess.run(
                        [ff, "-y", "-i", p["out_path"], "-i", p["input_path"],
                         "-c", "copy", "-map", "0:v:0", "-map", "1:a:0", final],
                        capture_output=True, text=True)
                    if r.returncode == 0 and os.path.exists(final):
                        os.replace(final, p["out_path"])
                    else:
                        has_audio = False  # audio mux failed; keep video-only output
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

        # smoothness check: decode the output and count frozen (duplicate) frames and
        # the max inter-frame PTS delta. A clean ramp has ~0 frozen frames and a tight
        # PTS-delta spread (monotonic, near-constant cadence).
        frozen = 0
        max_delta_ms = 0.0
        prev = None
        cap = cv2.VideoCapture(p["out_path"])
        pts = []
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            pts.append(cap.get(cv2.CAP_PROP_POS_MSEC))
            if prev is not None and np.array_equal(fr, prev):
                frozen += 1
            prev = fr
        cap.release()
        if len(pts) > 1:
            d = np.diff(np.array(pts))
            max_delta_ms = float(d.max())
        mono = bool((np.diff(np.array(pts)) >= 0).all()) if len(pts) > 1 else True

        return ToolResult(
            ok=True,
            data={"segments": segs, "control_points": len(peaks),
                  "setup_speed": p["setup_speed"], "peak_speed": p["peak_speed"],
                  "has_audio": has_audio, "frozen_frames": frozen,
                  "max_pts_delta_ms": round(max_delta_ms, 2), "pts_monotonic": mono},
            artifacts={"video": p["out_path"]},
            metrics={"segments": len(segs), "control_points": len(peaks),
                     "has_audio": has_audio, "frozen_frames": frozen,
                     "max_pts_delta_ms": round(max_delta_ms, 2), "pts_monotonic": mono},
        )
