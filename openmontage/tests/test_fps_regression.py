"""Item 1 — fps regression test.

Proves the renderer is driven by the *requested* fps (from config), not a baked-in 30
default. The fps-hardcoding bug (animation hooks assuming 30fps) stays closed because:
  - the Python side emits config.fps into studio_input.json (via _composition_fps), and
  - the Remotion animation hooks read `useVideoConfig().fps` (verified by grep), so the
    composition honors whatever fps the orchestrator requests.
"""
import os
import re

from kinetic_studio.config import KineticStudioConfig
from kinetic_studio.orchestrator import KineticStudio

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_composition_fps_honors_requested():
    # requested fps flows through; only None falls back to 30
    assert KineticStudio._composition_fps(60) == 60
    assert KineticStudio._composition_fps(50) == 50
    assert KineticStudio._composition_fps(0) == 30      # falsy -> fallback
    assert KineticStudio._composition_fps(None) == 30   # absent -> fallback


def test_build_studio_input_uses_config_fps_and_dims():
    cfg = KineticStudioConfig()
    cfg.output.fps = 60
    cfg.output.width = 1080
    cfg.output.height = 1920
    cfg.brand.name = "FBC Arena"
    studio = KineticStudio(cfg, workdir="/tmp/_fps_test")
    payload = studio._build_studio_input("studio_bg.mp4", None, 180)
    assert payload["fps"] == 60, payload
    assert payload["width"] == 1080 and payload["height"] == 1920
    assert payload["brand"] == "FBC Arena"
    assert payload["video"] == "studio_bg.mp4"
    # duration clamps to at least 60 frames even with no caption schedule
    assert payload["durationInFrames"] == 180


def test_remotion_hooks_read_config_fps_not_baked_default():
    """The Remotion animation components must derive fps from useVideoConfig(), so a
    60fps render paces correctly. Assert no fps-driven component hard-codes an `fps:`
    literal in its animation math and that each imports/uses useVideoConfig for fps.
    (StudioComposition.tsx is the container; the fps-driven kinetics live in the children.)"""
    tsx_dir = os.path.join(REPO, "openmontage", "remotion", "src")
    for fname in ("RepCounter.tsx", "ExerciseNameCard.tsx"):
        path = os.path.join(tsx_dir, fname)
        src = open(path, encoding="utf-8").read()
        assert "useVideoConfig" in src, f"{fname} missing useVideoConfig (bug reopened)"
        # a baked `fps: 30` default inside the component body would re-open the bug
        assert not re.search(r"fps:\s*30\b", src), \
            f"{fname} appears to hard-code fps:30 (bug reopened)"
