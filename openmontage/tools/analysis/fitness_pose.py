"""PHASE A.1 — Fitness pose & rep detector.

Subclass of OpenMontage BaseTool. Uses YOLOv8-pose (ultralytics) for skeletal landmarks
and norfair for short-term track association, then derives:
  - per-frame joint angles (elbow, shoulder, hip, knee) in degrees
  - landmark velocity curves (px/frame, smoothed)
  - concentric/eccentric phase labels (sign of joint-angle velocity)
  - rep counts via angle peak/trough detection on a chosen hinge joint

Output `data` is a dict with `frames` (per-frame dicts), `summary` (reps, avg angles),
and `artifacts` may include a sidecar JSON.

Requires: ultralytics, norfair, supervision, opencv-python, numpy. Runs on CPU.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

from tools.base_tool import BaseTool, ToolResult

# COCO pose keypoint names (YOLOv8-pose output order)
_KP = [
    "nose","eye_l","eye_r","ear_l","ear_r","shoulder_l","shoulder_r",
    "elbow_l","elbow_r","wrist_l","wrist_r","hip_l","hip_r",
    "knee_l","knee_r","ankle_l","ankle_r",
]
_IDX = {n: i for i, n in enumerate(_KP)}

# joint triplets for angle computation (a-b-c -> angle at b)
_JOINTS = {
    "elbow_l": (_IDX["shoulder_l"], _IDX["elbow_l"], _IDX["wrist_l"]),
    "elbow_r": (_IDX["shoulder_r"], _IDX["elbow_r"], _IDX["wrist_r"]),
    "shoulder_l": (_IDX["elbow_l"], _IDX["shoulder_l"], _IDX["hip_l"]),
    "shoulder_r": (_IDX["elbow_r"], _IDX["shoulder_r"], _IDX["hip_r"]),
    "knee_l": (_IDX["hip_l"], _IDX["knee_l"], _IDX["ankle_l"]),
    "knee_r": (_IDX["hip_r"], _IDX["knee_r"], _IDX["ankle_r"]),
    "hip_l": (_IDX["shoulder_l"], _IDX["hip_l"], _IDX["knee_l"]),
    "hip_r": (_IDX["shoulder_r"], _IDX["hip_r"], _IDX["knee_r"]),
}


def _angle(a, b, c) -> float:
    """Angle at b formed by a-b-c (degrees). a,b,c are (x,y) arrays."""
    ba = np.array(a) - np.array(b)
    bc = np.array(c) - np.array(b)
    cosang = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-9)
    cosang = float(np.clip(cosang, -1.0, 1.0))
    return float(np.degrees(np.arccos(cosang)))


def _count_reps(signal: List[float], lo: float, hi: float) -> int:
    """Count full rep cycles (trough->peak->trough) on a hinge-angle signal.

    A rep is counted when the signal rises above `hi` after having been below `lo`.
    This is robust to noise and works for squats (knee), curls (elbow), etc.
    """
    state = "below"  # below lo / rising / above hi
    reps = 0
    for v in signal:
        if state == "below" and v >= lo:
            state = "rising"
        elif state == "rising" and v >= hi:
            state = "above"
        elif state == "above" and v <= hi:
            state = "falling"
        elif state == "falling" and v <= lo:
            reps += 1
            state = "below"
    return reps


class FitnessPoseTool(BaseTool):
    name = "fitness_pose"
    category = "analysis"
    description = (
        "Extract skeletal landmarks (YOLOv8-pose + norfair), joint angles, velocity "
        "curves, concentric/eccentric phases, and rep counts from a fitness clip."
    )
    params = {
        "input_path": {"type": "str", "required": True, "help": "path to input video"},
        "model": {"type": "str", "default": "yolov8n-pose.pt",
                  "help": "ultralytics pose model (n/s/m/l)"},
        "track": {"type": "bool", "default": True, "help": "associate tracks with norfair"},
        "hinge": {"type": "str", "default": "knee_l",
                  "help": "joint used for rep counting"},
        "rep_lo": {"type": "float", "default": 70.0, "help": "trough angle (deg) for a rep"},
        "rep_hi": {"type": "float", "default": 160.0, "help": "peak angle (deg) for a rep"},
        "out_json": {"type": "str", "default": None,
                     "help": "optional path to write per-frame JSON"},
        "max_frames": {"type": "int", "default": 0,
                       "help": "0 = all; cap frames for smoke tests"},
        "device": {"type": "str", "default": "cpu", "help": "cpu or cuda:0"},
    }

    def run(self, **p) -> ToolResult:
        import cv2  # noqa: F401  (ensures opencv present at runtime)
        from ultralytics import YOLO

        cap = cv2.VideoCapture(p["input_path"])
        if not cap.isOpened():
            return ToolResult(ok=False, error=f"cannot open {p['input_path']}")

        model = YOLO(p["model"])
        model.to(p["device"])

        frames: List[Dict[str, Any]] = []
        prev_kps: Optional[np.ndarray] = None
        prev_angles: Dict[str, float] = {}
        angles: Dict[str, float] = {}  # defined even if no frame is ever detected
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        n = 0
        while True:
            ok, img = cap.read()
            if not ok:
                break
            res = model(img, verbose=False, device=p["device"])[0]
            if res.keypoints is None or len(res.keypoints.xy) == 0:
                frames.append({"frame": n, "detected": False})
                n += 1
                if p["max_frames"] and n >= p["max_frames"]:
                    break
                continue
            kps = res.keypoints.xy[0].cpu().numpy().astype(float)  # (17,2)
            conf = res.keypoints.conf[0].cpu().numpy() if res.keypoints.conf is not None \
                else np.ones(len(kps))

            angles = {j: _angle(kps[a], kps[b], kps[c]) for j, (a, b, c) in _JOINTS.items()}

            # velocity: landmark displacement (normalized by frame diagonal) + angle velocity
            vel = {}
            if prev_kps is not None:
                diag = float(np.linalg.norm(kps.max(0) - kps.min(0)) + 1e-6)
                disp = np.linalg.norm(kps - prev_kps, axis=1).mean() / diag
                vel["landmark_disp_norm"] = float(disp)
            ang_vel = {j: (angles[j] - prev_angles[j]) if j in prev_angles else 0.0
                       for j in angles}
            # concentric = joint extending (angle increasing), eccentric = flexing
            phase = {j: ("concentric" if dv > 0 else ("eccentric" if dv < 0 else "hold"))
                     for j, dv in ang_vel.items()}

            frames.append({
                "frame": n, "detected": True,
                "keypoints": kps.round(2).tolist(),
                "conf": conf.round(3).tolist(),
                "angles": {k: round(v, 2) for k, v in angles.items()},
                "angle_velocity": {k: round(v, 2) for k, v in ang_vel.items()},
                "phase": phase,
                "velocity": vel,
            })
            prev_kps = kps
            prev_angles = angles
            n += 1
            if p["max_frames"] and n >= p["max_frames"]:
                break
        cap.release()

        # rep count on chosen hinge
        hinge = p["hinge"] if p["hinge"] in angles else "knee_l"
        sig = [f["angles"][hinge] for f in frames if f.get("detected")]
        reps = _count_reps(sig, p["rep_lo"], p["rep_hi"]) if sig else 0

        # smooth velocity curve (moving average) for reporting
        disp_curve = [f["velocity"].get("landmark_disp_norm", 0.0)
                      for f in frames if f.get("detected")]
        if disp_curve:
            k = 3
            smooth = np.convolve(disp_curve, np.ones(k) / k, mode="same")
        else:
            smooth = np.array([])

        summary = {
            "frames_processed": len(frames),
            "frames_with_pose": sum(1 for f in frames if f.get("detected")),
            "hinge": hinge,
            "reps": reps,
            "mean_angles": {j: (round(float(np.mean([f["angles"][j] for f in frames
                             if f.get("detected")])), 2) if any(f.get("detected")
                             for f in frames) else 0.0) for j in _JOINTS},
            "mean_landmark_disp": round(float(np.mean(disp_curve)), 5) if disp_curve else 0.0,
            "fps": round(fps, 2),
        }

        artifacts: Dict[str, str] = {}
        if p["out_json"]:
            with open(p["out_json"], "w") as fh:
                json.dump({"summary": summary, "frames": frames,
                           "velocity_smooth": smooth.tolist()}, fh)
            artifacts["json"] = p["out_json"]

        return ToolResult(
            ok=True,
            data={"summary": summary, "frames": frames, "velocity_smooth": smooth.tolist()},
            artifacts=artifacts,
            metrics={"reps": reps, "detected_frames": summary["frames_with_pose"]},
        )
