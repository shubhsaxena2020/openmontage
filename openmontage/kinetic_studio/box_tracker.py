"""Box tracker for smart_reframe.

smart_reframe needs a per-frame bounding box for the athlete. We produce it two ways:
  1. From fitness_pose output (pose.json) if the model detected a person (real gym
     footage on the laptop -> accurate torso box).
  2. Fallback: a frame-difference centroid tracker (works on the VPS synthetic clip and
     any clip without reliable pose). Produces a smoothed box around the moving region.

Output: list of {frame, x, y, w, h} (top-left + size, in source pixels), JSON-serialisable
for the smart_reframe `boxes_json` param.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import numpy as np


def boxes_from_pose(pose_json: str, pad: int = 40) -> Optional[List[Dict[str, Any]]]:
    """Build boxes from a fitness_pose output file. Returns None if no detections."""
    with open(pose_json) as fh:
        data = json.load(fh)
    frames = data.get("frames", [])
    boxes: List[Dict[str, Any]] = []
    for f in frames:
        if not f.get("detected"):
            continue
        kp = np.array(f["keypoints"])  # (17,2) in source px
        xs, ys = kp[:, 0], kp[:, 1]
        x0, x1 = float(xs.min()), float(xs.max())
        y0, y1 = float(ys.min()), float(ys.max())
        boxes.append({
            "frame": f["frame"],
            "x": max(0, x0 - pad), "y": max(0, y0 - pad),
            "w": (x1 - x0) + 2 * pad, "h": (y1 - y0) + 2 * pad,
        })
    return boxes or None


def boxes_from_motion(video_path: str, fps: float = 30.0, pad: int = 60,
                      min_box: int = 200) -> List[Dict[str, Any]]:
    """Frame-difference centroid tracker -> per-frame box around the moving region."""
    import cv2
    cap = cv2.VideoCapture(video_path)
    prev = None
    boxes: List[Dict[str, Any]] = []
    n = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev is not None:
            diff = cv2.absdiff(gray, prev)
            _, mask = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            mask = cv2.dilate(mask, None, iterations=2)
            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if cnts:
                big = max(cnts, key=cv2.contourArea)
                if cv2.contourArea(big) > 50:
                    x, y, w, h = cv2.boundingRect(big)
                    cx, cy = x + w / 2, y + h / 2
                    bw = max(w + 2 * pad, min_box)
                    bh = max(h + 2 * pad, min_box)
                    bx = max(0, int(cx - bw / 2))
                    by = max(0, int(cy - bh / 2))
                    boxes.append({"frame": n, "x": bx, "y": by, "w": int(bw), "h": int(bh)})
        prev = gray
        n += 1
    cap.release()
    return boxes


def build_boxes(video_path: str, pose_json: Optional[str] = None,
                fps: float = 30.0) -> List[Dict[str, Any]]:
    """Prefer pose-derived boxes; fall back to motion tracker."""
    if pose_json:
        b = boxes_from_pose(pose_json)
        if b:
            return b
    return boxes_from_motion(video_path, fps=fps)


if __name__ == "__main__":
    import sys
    out = build_boxes(sys.argv[1])
    print(json.dumps(out[:3]))
    print(f"total boxes: {len(out)}")
