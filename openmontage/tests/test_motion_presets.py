"""Item 2 — motion preset library tests.

Presets are selectable by name and each has a test that proves the *shape* of the motion
curve (ramp speeds + zoom keyframes) is what the preset promises.
"""
import pytest

from kinetic_studio.presets import (
    PRESETS, list_presets, get_preset, motion_curve, build_motion_plan,
)


def test_presets_are_selectable_by_name():
    names = list_presets()
    assert {"cinematic", "energetic", "freeze", "subtle"} <= set(names)
    # each name resolves to a complete spec
    for n in names:
        spec = get_preset(n)
        assert "ramp" in spec and "zoom" in spec and "transition" in spec


def test_unknown_preset_raises():
    with pytest.raises(KeyError):
        get_preset("does-not-exist")


def test_ramp_curve_shapes_differ_between_presets():
    n = 90
    energetic = motion_curve("energetic", n)
    cinematic = motion_curve("cinematic", n)
    subtle = motion_curve("subtle", n)
    # energetic is the most aggressive (highest avg setup speed, lowest peak)
    assert sum(energetic) / len(energetic) > sum(cinematic) / len(cinematic)
    # subtle barely ramps (avg speed closest to 1.0)
    assert abs(sum(subtle) / len(subtle) - 1.0) < abs(sum(cinematic) / len(cinematic) - 1.0)
    # freeze has the deepest slow-mo window (min speed smallest)
    freeze = motion_curve("freeze", n)
    assert min(freeze) < min(energetic)
    # all curves are positive and frame-complete
    for c in (energetic, cinematic, subtle, freeze):
        assert len(c) == n
        assert all(v > 0 for v in c)


def test_build_motion_plan_contains_expected_shapes():
    plan = build_motion_plan("energetic", fps=30, n_frames=90, width=1080, height=1920)
    assert plan["preset"] == "energetic"
    assert plan["fps"] == 30 and plan["n_frames"] == 90
    # ramp segments cover the clip start..end
    segs = plan["ramp_segments"]
    assert segs[0]["t_start"] == 0.0
    assert segs[-1]["t_end"] == pytest.approx(90 / 30, abs=0.01)
    # peak segment uses the preset's slow speed
    assert any(abs(s["speed"] - 0.35) < 1e-6 for s in segs)
    # zoom keyframes: punch preset has a peak > 1.0 then settles back to 1.0
    zk = plan["zoom_keyframes"]
    assert zk[0]["scale"] == 1.0 and zk[-1]["scale"] == 1.0
    assert max(z["scale"] for z in zk) > 1.0
    # transition present
    assert plan["transition"]["type"] == "wipe"
    assert plan["transition"]["dur_frames"] > 0


def test_build_motion_plan_with_drop_times():
    plan = build_motion_plan("freeze", fps=30, n_frames=150, drop_times=[1.0, 2.5])
    segs = plan["ramp_segments"]
    # two drops => at least 2 slow windows at the drop speeds
    slow = [s for s in segs if abs(s["speed"] - 0.12) < 1e-6]
    assert len(slow) >= 2
    # timeline monotonic
    ts = [s["t_start"] for s in segs] + [segs[-1]["t_end"]]
    assert ts == sorted(ts)


def test_none_preset_is_noop_zoom():
    plan = build_motion_plan("subtle", fps=30, n_frames=60)
    # subtle has zoom mode 'none' -> constant scale 1.0
    assert all(z["scale"] == 1.0 for z in plan["zoom_keyframes"])
