"""Item 3 — audio-sync anchor tests.

The ramper must anchor motion to beats, explicit markers, AND voice peaks, and the sync
must not drift on slightly off-grid audio. These tests prove the anchor resolution is
stable and frame-locked (pure function), plus an end-to-end fixture through the ramper.
"""
import os

import pytest

from tools.video.kinetic_ramper import resolve_anchors


def test_resolve_anchors_snaps_off_grid_within_tolerance():
    fps = 30.0
    grid = 1.0 / fps  # 0.0333s
    # 1.04s is within 0.05 of the 1.0333 grid line -> snaps; 2.5 is already on grid
    out = resolve_anchors([1.04, 2.5], fps, snap_tolerance=0.05)
    assert out == pytest.approx([round(1.04 / grid) * grid, 2.5], abs=1e-3)


def test_resolve_anchors_keeps_off_grid_when_tolerance_zero():
    # tolerance 0 => never snap; anchors kept exactly (for deliberate off-grid markers)
    out = resolve_anchors([1.04, 2.5], 30.0, snap_tolerance=0.0)
    assert out == pytest.approx([1.04, 2.5], abs=1e-4)


def test_resolve_anchors_merges_and_dedupes_sources():
    # beats + markers + voice peaks, some colliding on the grid -> single stable list
    beats = [1.0, 2.0]
    markers = [1.01, 3.0]          # 1.01 snaps to ~1.0 grid and dedupes with beat 1.0
    voice = [2.02, 4.0]            # 2.02 snaps to ~2.0 grid and dedupes with beat 2.0
    out = resolve_anchors(beats + markers + voice, 30.0, snap_tolerance=0.05)
    # 1.0 and 2.0 each appear once; 3.0 and 4.0 present
    assert out.count(pytest.approx(1.0, abs=0.01)) == 1
    assert out.count(pytest.approx(2.0, abs=0.01)) == 1
    assert 3.0 in out and 4.0 in out


def test_resolve_anchors_no_cumulative_drift():
    # re-resolving the output must be idempotent -> proves no drift over repeated passes
    raw = [0.5, 1.04, 1.55, 2.5, 3.03, 4.0]
    first = resolve_anchors(raw, 30.0, snap_tolerance=0.05)
    second = resolve_anchors(first, 30.0, snap_tolerance=0.05)
    assert first == pytest.approx(second, abs=1e-3)


def test_ramper_uses_markers_and_voice_peaks_end_to_end():
    om = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    clip = os.path.join(om, "openmontage", "samples", "samples", "athlete_16x9.mp4")
    from tools import make_tool
    out = "/tmp/_anchor_ramped.mp4"
    if os.path.exists(out):
        os.remove(out)
    r = make_tool("kinetic_ramper", input_path=clip,
                  marker_times="0.5,2.0", voice_peaks="1.0,3.0",
                  out_path=out, setup_speed=1.6, peak_speed=0.4, snap_tolerance=0.05)
    assert r.ok, r.error
    # the output must be a real, monotonic, frame-stable clip
    assert r.metrics["pts_monotonic"] is True
    assert r.metrics["segments"] >= 2
    assert os.path.exists(out)
    os.remove(out)
