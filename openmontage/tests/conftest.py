import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "openmontage"))

from samples.generate_samples import make_athlete_clip, make_click_track  # noqa

SAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "samples", "samples")


@pytest.fixture(scope="session")
def sample_athlete_clip():
    os.makedirs(SAMPLES, exist_ok=True)
    p = os.path.join(SAMPLES, "athlete_16x9.mp4")
    if not os.path.exists(p):
        make_athlete_clip(p)
    return p


@pytest.fixture(scope="session")
def sample_beat_audio():
    os.makedirs(SAMPLES, exist_ok=True)
    p = os.path.join(SAMPLES, "beat_120bpm.wav")
    if not os.path.exists(p):
        try:
            make_click_track(p)
        except Exception:
            pytest.skip("soundfile unavailable; cannot make audio fixture")
    return p
