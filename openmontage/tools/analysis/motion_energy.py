"""PHASE A.2 — Motion energy & peak-moment indexer.

Frame-by-frame kinetic-energy proxy: for each frame compute the per-pixel/block motion
magnitude (optical-flow or frame-difference), aggregate to a scalar "energy", then
detect peaks (high-impact highlight moments) for cut points. Output is a timestamped list
of highlight moments (peak energy windows) suitable for auto-cutting.

CPU-only: uses frame differencing + (optional) Farneback optical flow. No ML deps.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

from tools.base_tool import BaseTool, ToolResult


def _frame_energy_gray(prev_gray: np.ndarray, gray: np.ndarray, method: str) -> float:
    if method == "flow":
        try:
            import cv2
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
            return float(mag.mean())
        except Exception:
            method = "diff"
    # frame difference (mean absolute luminance delta)
    d = np.abs(gray.astype(np.int16) - prev_gray.astype(np.int16)).mean()
    return float(d)


def _detect_peaks(energy: List[float], fps: float, window: int = 5,
                  prom: float = 0.0) -> List[Dict[str, Any]]:
    """Local-maxima peaks above (mean + prom*std). Returns timestamped highlight windows."""
    arr = np.array(energy, dtype=float)
    if len(arr) == 0:
        return []
    mean, std = arr.mean(), arr.std()
    thr = mean + prom * std
    peaks: List[Dict[str, Any]] = []
    half = max(1, window // 2)
    for i in range(half, len(arr) - half):
        seg = arr[i - half:i + half + 1]
        if arr[i] >= thr and arr[i] == seg.max():
            peaks.append({
                "frame": i,
                "t_sec": round(i / fps, 3),
                "energy": round(float(arr[i]), 4),
                "window_start_t": round(max(0, i - half) / fps, 3),
                "window_end_t": round(min(len(arr) - 1, i + half) / fps, 3),
            })
    return peaks


class MotionEnergyTool(BaseTool):
    name = "motion_energy"
    category = "analysis"
    description = (
        "Frame-by-frame kinetic-energy deltas and timestamped peak-moment highlights "
        "for auto-cut points."
    )
    params = {
        "input_path": {"type": "str", "required": True, "help": "input video"},
        "method": {"type": "str", "default": "diff", "help": "diff | flow"},
        "downscale": {"type": "int", "default": 256,
                      "help": "resize width for speed (0=keep)"},
        "peak_window": {"type": "int", "default": 5, "help": "frames around a peak"},
        "peak_prominence": {"type": "float", "default": 1.0,
                            "help": "std-multiples above mean to count as highlight"},
        "out_json": {"type": "str", "default": None, "help": "write energy curve+peaks"},
        "max_frames": {"type": "int", "default": 0, "help": "0=all; cap for smoke tests"},
    }

    def run(self, **p) -> ToolResult:
        import cv2

        cap = cv2.VideoCapture(p["input_path"])
        if not cap.isOpened():
            return ToolResult(ok=False, error=f"cannot open {p['input_path']}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        prev = None
        energy: List[float] = []
        n = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if p["downscale"]:
                h = int(g.shape[0] * p["downscale"] / g.shape[1])
                g = cv2.resize(g, (p["downscale"], h))
            if prev is not None:
                energy.append(_frame_energy_gray(prev, g, p["method"]))
            prev = g
            n += 1
            if p["max_frames"] and n >= p["max_frames"]:
                break
        cap.release()

        peaks = _detect_peaks(energy, fps, window=p["peak_window"],
                              prom=p["peak_prominence"])
        summary = {
            "frames": len(energy),
            "fps": round(fps, 2),
            "mean_energy": round(float(np.mean(energy)), 4) if energy else 0.0,
            "max_energy": round(float(np.max(energy)), 4) if energy else 0.0,
            "highlight_moments": len(peaks),
        }
        artifacts: Dict[str, str] = {}
        if p["out_json"]:
            with open(p["out_json"], "w") as fh:
                json.dump({"summary": summary, "energy": energy, "peaks": peaks}, fh)
            artifacts["json"] = p["out_json"]
        return ToolResult(
            ok=True,
            data={"summary": summary, "energy": energy, "peaks": peaks},
            artifacts=artifacts,
            metrics={"highlights": len(peaks), "max_energy": summary["max_energy"]},
        )
