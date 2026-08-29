"""Generate synthetic sample media for OpenMontage tool verification.

Honest note: OpenMontage's fitness_pose needs a REAL human for YOLOv8-pose to detect
keypoints. We have no such clip, so this generator makes:
  - samples/athlete_16x9.mp4 : 1280x720, a white "athlete" box that moves vertically
    (bounces) and horizontally — exercises motion_energy (energy spikes) and
    smart_reframe (bbox tracking + anti-jitter smoothing).
  - samples/beat_120bpm.wav  : a 120 BPM click track (known ground truth) for beat accuracy.

The pose *math* (angles/reps) is verified separately via a unit test on a synthetic
keypoint signal (tools/tests/test_fitness_pose.py).
"""
import os
import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "samples")
os.makedirs(OUT, exist_ok=True)


def make_athlete_clip(path, W=1280, H=720, fps=30, seconds=6):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(path, fourcc, fps, (W, H))
    n = int(fps * seconds)
    for i in range(n):
        t = i / fps
        frame = np.full((H, W, 3), 20, dtype=np.uint8)  # dark bg
        # vertical bounce (deep squat-like) -> box height changes to mimic extension
        cy = int(H * (0.5 + 0.32 * np.sin(2 * np.pi * 0.25 * t)))  # 0.25 Hz => ~1.5 reps
        cx = int(W * (0.5 + 0.10 * np.sin(2 * np.pi * 0.13 * t)))
        bw, bh = 160, int(260 + 80 * np.sin(2 * np.pi * 0.25 * t))
        x0, y0 = int(cx - bw / 2), int(cy - bh / 2)
        x1, y1 = int(cx + bw / 2), int(cy + bh / 2)
        cv2.rectangle(frame, (x0, y0), (x1, y1), (235, 235, 235), -1)
        # a "head" dot so there is a distinct top feature
        cv2.circle(frame, (cx, y0 - 18), 26, (235, 200, 120), -1)
        vw.write(frame)
    vw.release()
    return path


def make_click_track(path, bpm=120, seconds=8, sr=22050):
    n = int(sr * seconds)
    y = np.zeros(n, dtype=np.float32)
    beat = 60.0 / bpm
    pos = 0.0
    while pos < seconds:
        i = int(pos * sr)
        # short broadband click
        y[i:i + 200] += 0.8 * np.hanning(200) * np.sin(2 * np.pi * 1000 * np.arange(200) / sr)
        pos += beat
    y /= (np.max(np.abs(y)) + 1e-9)
    import soundfile as sf
    sf.write(path, y, sr)
    return path


def copy_real_speech(path, candidates=None):
    """Copy a real speech sample into the samples dir for caption-sync verification.

    OpenMontage has no real coaching clip on this host; we use a real TTS speech sample
    that ships with the Hermes neutts tooling (genuine spoken words, not synthetic) so the
    kinetic_word_sync timing-sync test exercises real word timestamps. Returns the path if
    copied, else None (caller should skip / provide its own speech file).
    """
    if candidates is None:
        candidates = [
            "/home/ubuntu/.hermes/hermes-agent/tools/neutts_samples/jo.wav",
        ]
    for c in candidates:
        if os.path.exists(c):
            import shutil
            shutil.copy(c, path)
            return path
    return None


if __name__ == "__main__":
    p1 = make_athlete_clip(os.path.join(OUT, "athlete_16x9.mp4"))
    print("wrote", p1)
    try:
        p2 = make_click_track(os.path.join(OUT, "beat_120bpm.wav"))
        print("wrote", p2)
    except ImportError:
        print("soundfile missing; audio will be generated in the test via numpy+imageio")
    p3 = copy_real_speech(os.path.join(OUT, "speech.wav"))
    print("wrote", p3 if p3 else "speech.wav (no real sample found; skipped)")
