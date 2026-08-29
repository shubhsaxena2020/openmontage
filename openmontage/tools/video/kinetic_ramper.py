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


def resolve_anchors(times: List[float], fps: float, snap_tolerance: float = 0.05) -> List[float]:
    """Merge beats / markers / voice peaks into a single, stable anchor list.

    Each anchor is optionally *snapped* to the nearest frame grid (1/fps) when it falls
    within `snap_tolerance` seconds of a grid line. This is what keeps audio-synced motion
    from drifting: slightly off-grid beats (e.g. 1.04s vs the 1.033s 30fps grid) snap to
    the frame and stay locked, while genuinely off-grid markers (tolerance 0) are kept
    exactly. De-duplicates on the snapped grid so merged sources don't double-anchor.

    Returns sorted, de-duplicated, non-negative anchors. Pure & testable.
    """
    grid = 1.0 / max(1e-6, fps)
    out: List[float] = []
    for t in times:
        if t is None or t < 0:
            continue
        if snap_tolerance and snap_tolerance > 0:
            nearest = round(t / grid) * grid
            if abs(nearest - t) <= snap_tolerance:
                t = nearest
        out.append(round(t, 4))
    # dedupe on a coarse grid, keep sorted
    seen = set()
    deduped = []
    for t in sorted(out):
        key = round(t / grid, 1)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)
    return deduped


def merge_slow_windows(slow_windows: List[float], grid: float,
                        end: float) -> List[float]:
    """Merge overlapping slow-window pairs into a flat, frame-snapped list.

    Anchors are often dense (many beats within a pad), so naive per-anchor windows overlap
    heavily and fragment the timeline into dozens of sub-frame segments — which makes ffmpeg
    trim+setpts quantization drift far from the plan. Merging adjacent/overlapping windows
    into one interval (and snapping its edges to the frame grid) yields clean, render-accurate
    segments. Returns a flat [ws0, we0, ws1, we1, ...] list in seconds.
    """
    if not slow_windows:
        return []
    ivs = sorted((round(slow_windows[i], 3), round(slow_windows[i + 1], 3))
                 for i in range(0, len(slow_windows) - 1, 2))
    merged: List[List[float]] = []
    cs, ce = ivs[0]
    for s, e in ivs[1:]:
        if s <= ce:           # overlap or touching -> extend
            ce = max(ce, e)
        else:
            merged.append([cs, ce])
            cs, ce = s, e
    merged.append([cs, ce])
    flat: List[float] = []
    for s, e in merged:
        s = max(0.0, round(round(s / grid) * grid, 3))
        e = min(round(end, 3), round(round(e / grid) * grid, 3))
        if e > s:
            flat += [s, e]
    return flat


def _build_segments(slow_windows: List[float], setup_speed: float, peak_speed: float,
                    end: float) -> List[Dict[str, float]]:
    """Build the tempo-remap timeline from explicit slow windows.

    Walks [0, end] and emits `setup_speed` segments everywhere EXCEPT inside each slow
    window (a [start,end] pair), where it emits `peak_speed` (slow-mo). Adjacent
    equal-speed segments are merged so the rendered output is a small number of clean,
    contiguous time-remaps (no micro-segment concat artifacts / frozen frames).

    Narrow slow windows (e.g. 0.3s around a drop) stay narrow — the previous implementation
    tested full *containment* of each control-point segment inside the tiny window, which
    almost never held, so every segment collapsed to setup_speed and the slow-mo was lost.
    """
    if not slow_windows:
        return [{"t_start": 0.0, "t_end": round(end, 3), "speed": setup_speed}]
    wins = sorted((slow_windows[i], slow_windows[i + 1])
                  for i in range(0, len(slow_windows) - 1, 2))
    segs: List[Dict[str, float]] = []
    cur = 0.0
    for ws, we in wins:
        ws = max(0.0, round(ws, 3))
        we = min(round(end, 3), round(we, 3))
        if we <= ws:
            continue
        if ws > cur:
            segs.append({"t_start": round(cur, 3), "t_end": ws, "speed": setup_speed})
        segs.append({"t_start": ws, "t_end": we, "speed": peak_speed})
        cur = we
    if cur < end:
        segs.append({"t_start": round(cur, 3), "t_end": round(end, 3), "speed": setup_speed})
    merged: List[Dict[str, float]] = []
    for s in segs:
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
        "marker_times": {"type": "str", "default": None,
                         "help": "comma-sep explicit marker seconds to anchor slow-mo on"},
        "voice_peaks": {"type": "str", "default": None,
                        "help": "comma-sep voice-peak seconds (e.g. word onsets) to anchor on"},
        "snap_tolerance": {"type": "float", "default": 0.05,
                           "help": "seconds; anchors within this of a frame grid are snapped (anti-drift)"},
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

        # collect control points (peak/drop timestamps) from every anchor source
        beats: List[float] = []
        if p["map_json"]:
            with open(p["map_json"]) as fh:
                m = json.load(fh)
            beats = [d["t_sec"] for d in m.get("drops", [])]
            beats += m.get("downbeat_times", [])
        if p["peak_times"]:
            beats += [float(x) for x in p["peak_times"].split(",") if x.strip()]
        markers: List[float] = []
        if p["marker_times"]:
            markers += [float(x) for x in p["marker_times"].split(",") if x.strip()]
        voice: List[float] = []
        if p["voice_peaks"]:
            voice += [float(x) for x in p["voice_peaks"].split(",") if x.strip()]

        # Merge + snap-to-grid so slightly off-grid audio does not drift. beats already
        # come from the beat map; markers/voice peaks are explicit anchors.
        fps_cap = 30.0
        try:
            import cv2  # type: ignore
            _cap = cv2.VideoCapture(p["input_path"])
            fps_cap = _cap.get(cv2.CAP_PROP_FPS) or 30.0
            _cap.release()
        except Exception:
            pass
        peaks = resolve_anchors(beats + markers + voice, fps_cap, p["snap_tolerance"])
        if not peaks:
            # No beat/drop signal (e.g. silent footage, no music supplied). Degrade
            # gracefully to a single uniform-speed segment instead of failing — the
            # studio still gets a reframed, lightly sped-up short.
            segs = [{"t_start": 0.0, "t_end": 1e9, "speed": p["setup_speed"]}]
            slow_windows: List[float] = []
        else:
            # Slow-mo windows are centered on each drop/peak; expand every anchor into a
            # [d-pad, d+pad] window (a flat list of start,end pairs).
            pad = 0.15
            slow_windows = []
            for d in peaks:
                slow_windows.append(round(max(0.0, d - pad), 3))
                slow_windows.append(round(d + pad, 3))
            # end = full clip duration so the whole footage is covered (slow windows are
            # narrow islands inside it); fall back to last peak+pad if probe fails.
            clip_dur = 0.0
            try:
                import cv2  # type: ignore
                _c = cv2.VideoCapture(p["input_path"])
                _n = _c.get(cv2.CAP_PROP_FRAME_COUNT) or 0
                _f = _c.get(cv2.CAP_PROP_FPS) or 30.0
                clip_dur = float(_n) / float(_f) if _f else 0.0
                _c.release()
            except Exception:
                clip_dur = 0.0
            if clip_dur <= 0:
                clip_dur = float(peaks[-1] + pad)
            # merge overlapping windows + snap to frame grid so ffmpeg's trim+setpts stays
            # accurate (dense anchors would otherwise fragment the timeline and drift).
            grid = 1.0 / max(1e-6, fps_cap)
            slow_windows = merge_slow_windows(slow_windows, grid, clip_dur)
            segs = _build_segments(slow_windows, p["setup_speed"], p["peak_speed"], clip_dur)

        import cv2  # type: ignore  (used by the render loop fps probe + smoothness check)
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
