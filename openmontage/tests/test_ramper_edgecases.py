"""Phase B.7 — kinetic ramper edge-case unit tests (pure, no ffmpeg/video).

Targets the render-independent helpers in tools/video/kinetic_ramper.py:
  - _build_segments: tempo-remap timeline from slow windows (empty -> uniform; merge)
  - merge_slow_windows: overlap merge + frame-grid clamp
These run in milliseconds, so they belong in the fast unit-test tier (no GPU/CPU render).
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.video.kinetic_ramper import (  # noqa: E402
    _build_segments,
    merge_slow_windows,
    resolve_anchors,
)


def test_build_segments_empty_windows_is_single_uniform_setup():
    # No slow windows -> the whole clip is one uniform setup-speed segment.
    segs = _build_segments([], setup_speed=1.6, peak_speed=0.4, end=6.0)
    assert len(segs) == 1
    s = segs[0]
    assert s["t_start"] == 0.0
    assert math.isclose(s["t_end"], 6.0)
    assert math.isclose(s["speed"], 1.6)


def test_build_segments_tiny_window_keeps_slowmo_not_lost():
    # The historical bug: a 0.3s window used full *containment* checks and dropped the
    # slow-mo. The current impl uses window overlap, so the narrow slow window survives.
    segs = _build_segments([0.85, 1.15], setup_speed=1.6, peak_speed=0.4, end=3.0)
    speeds = [s["speed"] for s in segs]
    assert 0.4 in speeds, "slow-mo window must be preserved"
    # setup before + slow inside + setup after
    assert speeds[0] == 1.6
    assert any(math.isclose(sp, 0.4) for sp in speeds)


def test_build_segments_merges_adjacent_equal_speed():
    # Two separate slow windows close enough that the gap between them is setup-speed;
    # adjacent equal-speed setup segments should merge into fewer contiguous segments.
    segs = _build_segments([0.5, 0.8, 2.0, 2.3], setup_speed=1.6, peak_speed=0.4, end=4.0)
    # expect: setup(0-0.5), slow(0.5-0.8), setup(0.8-2.0), slow(2.0-2.3), setup(2.3-4.0)
    assert len(segs) == 5
    for a, b in zip(segs, segs[1:]):
        assert a["t_end"] == b["t_start"], "segments must be contiguous"


def test_build_segments_clamps_window_to_end():
    # A slow window past the clip end must be clamped, not extended.
    segs = _build_segments([2.8, 5.0], setup_speed=1.6, peak_speed=0.4, end=3.0)
    for s in segs:
        assert s["t_start"] >= 0.0
        assert s["t_end"] <= 3.0 + 1e-6
    # the slow window is clamped into [2.8, 3.0]
    slow = [s for s in segs if math.isclose(s["speed"], 0.4)]
    assert slow and math.isclose(slow[0]["t_end"], 3.0, abs_tol=1e-3)


def test_build_segments_zero_length_window_skipped():
    # A degenerate window where start>=end must be skipped (no empty segment).
    segs = _build_segments([1.0, 1.0], setup_speed=1.6, peak_speed=0.4, end=3.0)
    # only the uniform setup segment remains
    assert len(segs) == 1
    assert math.isclose(segs[0]["speed"], 1.6)


def test_merge_slow_windows_clamps_and_drops_empty():
    grid = 1.0 / 30.0
    # a window that starts before 0 and ends before its start -> dropped; end clamps to clip
    flat = merge_slow_windows([-0.5, 0.2, 2.5, 1.0], grid, end=3.0)
    assert len(flat) % 2 == 0, "flat list must be pairs"
    # every interval valid and within [0, end]
    for i in range(0, len(flat), 2):
        assert flat[i] >= 0.0
        assert flat[i + 1] <= 3.0 + 1e-6
        assert flat[i + 1] > flat[i], "empty/negative intervals dropped"


def test_merge_slow_windows_merges_overlapping():
    grid = 1.0 / 30.0
    # two overlapping windows should become one contiguous interval
    flat = merge_slow_windows([1.0, 1.5, 1.3, 2.0], grid, end=5.0)
    assert flat == [1.0, 2.0], f"expected merged [1.0,2.0], got {flat}"


def test_overshoot_peak_speed_gt_1_still_produces_window_segments():
    # "overshoot" = peak_speed requested faster than realtime (speed>1). The plan must
    # still emit one segment per slow window and never invert the timeline (speed>0 always).
    segs = _build_segments([1.0, 1.3], setup_speed=1.6, peak_speed=1.4, end=4.0)
    speeds = [s["speed"] for s in segs]
    assert all(sp > 0 for sp in speeds), "no inverted/zero-speed segments"
    assert 1.4 in speeds, "overshoot window honored"


def test_resolve_anchors_snaps_off_grid_and_dedupes():
    # 1.04s is within 0.05s of the 30fps grid (1.033s) -> snapped; duplicate of the
    # snapped value is deduped. Confirms audio-sync anti-drift merge (B8 helper).
    a = resolve_anchors([1.04, 1.033, 2.0], fps=30.0, snap_tolerance=0.05)
    # 1.04 is off-grid but within tolerance, so it must snap to a 30fps grid multiple
    # (1/30 = 0.03333...); the duplicate (1.033, also on the grid) must be deduped.
    grid = 1.0 / 30.0
    assert len(a) == 2, f"expected 2 anchors after dedupe, got {a}"
    assert a[0] == round(round(1.04 / grid) * grid, 4), f"1.04 should snap to grid, got {a}"
    assert abs(a[0] - 1.04) <= 0.05, "snapped within tolerance"
    assert a[1] == 2.0


def test_resolve_anchors_negative_and_none_dropped():
    a = resolve_anchors([-1.0, None, 0.5], fps=30.0, snap_tolerance=0.05)
    assert all(t >= 0 for t in a)
    assert 0.5 in a
