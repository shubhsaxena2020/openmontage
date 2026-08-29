import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "openmontage"))

# NOTE: importing `samples.generate_samples` here would pull in `cv2` (OpenCV) at
# collection time, which cannot load on a headless box without libxcb (and is wholly
# irrelevant to audio/subtitle tests). Import it lazily inside the fixtures that
# actually need generated video/audio so the rest of the suite collects cleanly.
SAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "samples", "samples")


@pytest.fixture(scope="session")
def sample_athlete_clip():
    from samples.generate_samples import make_athlete_clip

    os.makedirs(SAMPLES, exist_ok=True)
    p = os.path.join(SAMPLES, "athlete_16x9.mp4")
    if not os.path.exists(p):
        make_athlete_clip(p)
    return p


@pytest.fixture(scope="session")
def sample_beat_audio():
    from samples.generate_samples import make_click_track

    os.makedirs(SAMPLES, exist_ok=True)
    p = os.path.join(SAMPLES, "beat_120bpm.wav")
    if not os.path.exists(p):
        try:
            make_click_track(p)
        except Exception:
            pytest.skip("soundfile/cv2 unavailable; cannot make audio fixture")
    return p
