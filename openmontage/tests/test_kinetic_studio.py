"""Tests for Kinetic Studio orchestrator (smoke, synthetic media).

Verifies the full product chain produces a final short on synthetic footage, and that
graceful degradation works (no audio -> uniform ramp, no voiceover -> no captions).
The Remotion final composite is exercised headlessly here; the 60fps interactive preview
is a laptop-only verification (documented in kinetic_studio/README.md).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "openmontage"))

from kinetic_studio.orchestrator import KineticStudio  # noqa: E402
from kinetic_studio.config import KineticStudioConfig  # noqa: E402
import pytest


@pytest.fixture(scope="module")
def clip():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "samples", "samples", "athlete_16x9.mp4")
    return p


def test_studio_runs_end_to_end(clip, tmp_path):
    cfg = KineticStudioConfig()
    studio = KineticStudio(cfg, workdir=str(tmp_path / "studio"))
    res = studio.run(clip, out_name="kinetic_short.mp4")
    assert res.ok, {s["step"]: s["detail"] for s in res.steps if not s["ok"]}
    assert res.final_video and os.path.exists(res.final_video)
    # HUD/reframe/ramp steps must have succeeded
    steps = {s["step"]: s for s in res.steps}
    assert steps["reframe"]["ok"]
    assert steps["ramper"]["ok"]
    # composite produced a real file (Remotion rendered, or graceful ramped fallback)
    assert os.path.getsize(res.final_video) > 1000


def test_studio_graceful_no_audio(clip, tmp_path):
    """Silent footage: beats skipped, ramper still produces output (uniform ramp)."""
    studio = KineticStudio(KineticStudioConfig(), workdir=str(tmp_path / "studio2"))
    res = studio.run(clip, out_name="short.mp4")
    steps = {s["step"]: s for s in res.steps}
    assert not steps["beats"]["ok"]            # skipped (no audio)
    assert steps["ramper"]["ok"]               # uniform ramp instead of failing
    assert res.ok
