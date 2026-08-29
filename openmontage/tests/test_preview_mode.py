"""Item 4 — preview / proxy mode tests.

Preview mode is a fast draft pass: it drops the render to a low proxy resolution, skips the
heavy Remotion HUD composite, and (in CI/headless) still completes. The tests assert the
proxy dimensions are computed, the studio composite is bypassed, and a real preview run on
the athlete clip produces a valid low-res short without Remotion.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "openmontage"))

from kinetic_studio.config import KineticStudioConfig
from kinetic_studio.orchestrator import KineticStudio

SAMPLES = os.path.join(os.path.dirname(HERE), "samples", "samples")
ATHLETE = os.path.join(SAMPLES, "athlete_16x9.mp4")


def test_preview_drops_to_proxy_resolution():
    cfg = KineticStudioConfig()
    cfg.output.width, cfg.output.height = 1080, 1920
    full = KineticStudio(cfg, workdir="/tmp/_pv_full")
    assert full.render_dims() == {"width": 1080, "height": 1920}

    cfg.preview = True
    prev = KineticStudio(cfg, workdir="/tmp/_pv_prev")
    dims = prev.render_dims()
    # width keeps 9:16 aspect; height clamps to the 360 proxy cap
    assert dims["height"] == 360
    assert abs(dims["width"] / dims["height"] - (1080 / 1920)) < 0.01


def test_preview_skips_studio_composite():
    cfg = KineticStudioConfig()
    cfg.preview = True
    prev = KineticStudio(cfg, workdir="/tmp/_pv_prev2")
    assert prev.should_render_studio() is False
    # headless env var also forces skip even when not preview
    cfg.preview = False
    full = KineticStudio(cfg, workdir="/tmp/_pv_full2")
    assert full.should_render_studio() is True
    os.environ["KINETIC_HEADLESS"] = "1"
    try:
        assert full.should_render_studio() is False
    finally:
        os.environ.pop("KINETIC_HEADLESS", None)


def test_preview_run_is_low_res_and_skips_remotion():
    cfg = KineticStudioConfig()
    cfg.preview = True
    ks = KineticStudio(cfg, workdir="/tmp/_pv_run")
    res = ks.run(ATHLETE, out_name="preview_short.mp4")
    assert res.ok, res.steps
    # the final short is the ramped (proxy) video — no Remotion composite step succeeded
    studio_steps = [s for s in res.steps if s["step"] == "studio_composite"]
    assert studio_steps and studio_steps[0]["ok"] is False, "preview must skip Remotion"
    out = res.final_video
    assert out and os.path.exists(out)
    # verify the proxy resolution via ffprobe-less cv2 read
    import cv2
    cap = cv2.VideoCapture(out)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    assert h <= 360, f"preview output not low-res: {h}"
