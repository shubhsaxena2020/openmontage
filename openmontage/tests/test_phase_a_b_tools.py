"""Verification tests for Phase A (pose/energy/reframe) and Phase B.4 (beat) tools.

These run against the SYNTHETIC sample clip (samples/samples/*.mp4) and a generated
120-BPM click track. Honest labelling per AGENT_GUIDE:
  - motion_energy / smart_reframe / beat_drop_mapper are exercised on REAL generated
    media (a moving box clip + a real click audio waveform), so the render/extract
    outputs are genuine, not stubbed.
  - fitness_pose *detection* needs a real human; the COCO model will NOT detect the
    synthetic white box, so we assert the tool runs without crashing (ok=True,
    detected_frames==0) and verify the angle/velocity/phase/rep MATH on a synthetic
    keypoint signal (no model required). A real-human clip is required for end-to-end
    pose extraction and is out of scope on this headless host.
"""
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "openmontage"))

from tools.analysis.fitness_pose import FitnessPoseTool, _angle, _count_reps
from tools.analysis.motion_energy import MotionEnergyTool
from tools.video.smart_reframe import SmartReframeTool
from tools.audio.beat_drop_mapper import BeatDropMapperTool

SAMPLES = os.path.join(os.path.dirname(HERE), "samples", "samples")
ATHLETE = os.path.join(SAMPLES, "athlete_16x9.mp4")
BEAT = os.path.join(SAMPLES, "beat_120bpm.wav")
POSE_MODEL = "/home/ubuntu/projects/agent-6/yolov8n-pose.pt"


# ---------------------------------------------------------------- A.1 fitness_pose
def test_angle_geometry():
    assert abs(_angle((0, 0), (1, 0), (2, 0)) - 180.0) < 1e-2   # straight
    assert abs(_angle((0, 1), (0, 0), (1, 0)) - 90.0) < 1e-6    # right angle


def test_count_reps_squat_signal():
    sig = []
    for _ in range(3):
        for a in range(60, 171, 10):
            sig.append(float(a))
        for a in range(170, 59, -10):
            sig.append(float(a))
    assert _count_reps(sig, lo=80.0, hi=150.0) == 3


def test_count_reps_flat_is_zero():
    assert _count_reps([150, 150, 150], lo=80, hi=150) == 0


def test_pose_runs_on_real_clip_no_crash(sample_athlete_clip):
    # synthetic box is not a COCO human -> tool must not crash, returns ok with 0 detections
    res = FitnessPoseTool().execute(input_path=sample_athlete_clip, model=POSE_MODEL,
                                    max_frames=20)
    assert res.ok, res.error
    assert res.metrics.get("detected_frames", 0) == 0


# ---------------------------------------------------------------- A.2 motion_energy
def test_motion_energy_detects_peaks_on_moving_clip(sample_athlete_clip):
    res = MotionEnergyTool().execute(input_path=sample_athlete_clip, method="diff",
                                     max_frames=60)
    assert res.ok, res.error
    s = res.data["summary"]
    assert s["frames"] > 0
    # the box bounces -> there must be non-trivial motion energy and >=1 highlight
    assert s["max_energy"] > 0.5
    assert s["highlight_moments"] >= 1
    # peak timestamps are monotonically increasing and within clip duration
    ts = [p["t_sec"] for p in res.data["peaks"]]
    assert ts == sorted(ts)
    assert all(0 <= t <= s["frames"] / s["fps"] + 1e-6 for t in ts)


# ---------------------------------------------------------------- A.3 smart_reframe
def _write_box_json(clip, path):
    import cv2
    cap = cv2.VideoCapture(clip)
    fps = cap.get(cv2.CAP_PROP_FPS)
    boxes = []
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        H, W = fr.shape[:2]
        t = i / fps
        cy = int(H * (0.5 + 0.32 * np.sin(2 * np.pi * 0.25 * t)))
        cx = int(W * (0.5 + 0.10 * np.sin(2 * np.pi * 0.13 * t)))
        bw, bh = 160, int(260 + 80 * np.sin(2 * np.pi * 0.25 * t))
        boxes.append({"frame": i, "x": int(cx - bw / 2), "y": int(cy - bh / 2),
                      "w": bw, "h": bh})
        i += 1
    cap.release()
    with open(path, "w") as fh:
        import json
        json.dump(boxes, fh)
    return len(boxes)


def test_smart_reframe_renders_9x16_and_smooths(sample_athlete_clip, tmp_path):
    box_json = tmp_path / "boxes.json"
    n = _write_box_json(sample_athlete_clip, str(box_json))
    assert n > 0
    out = tmp_path / "out_9x16.mp4"
    res = SmartReframeTool().execute(input_path=sample_athlete_clip, out_path=str(out),
                                     boxes_json=str(box_json), alpha=0.3, deadband=8)
    assert res.ok, res.error
    # output is a real rendered 9:16 file
    assert os.path.exists(out)
    assert os.path.getsize(out) > 1000
    assert res.data["target_wh"] == [540, 960]   # 9:16
    # smoothing must reduce jitter vs the raw detected centers
    assert res.metrics["jitter_reduction"] > 0.0, res.metrics
    assert res.metrics["raw_jitter_px"] >= res.metrics["jitter_px"]


# ---------------------------------------------------------------- B.4 beat_drop_mapper
def test_beat_mapper_bpm_accuracy_on_120_click(sample_beat_audio):
    res = BeatDropMapperTool().execute(audio_path=sample_beat_audio)
    assert res.ok, res.error
    bpm = res.metrics["bpm"]
    # librosa on a clean click track should be within ~5% of the 120 BPM ground truth
    assert abs(bpm - 120.0) <= 6.0, f"BPM {bpm} too far from 120"
    assert res.data["summary"]["beats"] >= 8
    assert res.data["summary"]["duration_sec"] > 0
