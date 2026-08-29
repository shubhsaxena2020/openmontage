"""Unit tests for fitness_pose math (angles, rep counting) + graceful no-detection.

These don't require a real human clip: the joint-angle and rep-counting logic is tested
on synthetic keypoint signals, and the tool is asserted to return ok=True (not crash)
when no person is detected.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "openmontage"))

import numpy as np
from tools.analysis.fitness_pose import _angle, _count_reps, FitnessPoseTool
import pytest


def test_angle_straight():
    # a-b-c colinear -> 180 deg (arccos float error near 180; allow 1e-2)
    assert abs(_angle((0, 0), (1, 0), (2, 0)) - 180.0) < 1e-2


def test_angle_right():
    # a=(0,1) b=(0,0) c=(1,0) -> 90 deg
    assert abs(_angle((0, 1), (0, 0), (1, 0)) - 90.0) < 1e-6


def test_count_reps_squat_signal():
    # knee angle: extended (~170) at top, flexed (~60) at bottom. Simulate 3 squats.
    sig = []
    for _ in range(3):
        for a in range(60, 171, 10):  # down
            sig.append(float(a))
        for a in range(170, 59, -10):  # up
            sig.append(float(a))
    reps = _count_reps(sig, lo=80.0, hi=150.0)
    assert reps == 3, f"expected 3 reps, got {reps}"


def test_count_reps_flat_signal_zero():
    assert _count_reps([150, 150, 150, 150], lo=80, hi=150) == 0


def test_run_no_detection_ok(sample_athlete_clip):
    res = FitnessPoseTool().execute(input_path=sample_athlete_clip, model="yolov8n-pose.pt",
                                    max_frames=30)
    # synthetic box is not a human: tool must not crash; ok=True, 0 detections
    assert res.ok, res.error
    assert res.metrics.get("detected_frames", 0) == 0
