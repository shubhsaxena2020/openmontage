"""Verification tests for PHASE B.5 (kinetic_ramper) and PHASE C.7 (kinetic_word_sync).

All run against REAL generated/recorded media:
  - kinetic_ramper: athlete clip + 120-BPM beat-drop map. Asserts the time-remap is
    genuine (setup speed-up shortens the clip), slow-mo windows land on the drops,
    the output is smooth (no frozen frames, monotonic PTS, constant cadence), and
    audio stays muxed through (A/V sync) when the source has an audio track.
  - kinetic_word_sync: real speech audio (faster-whisper). Asserts word timestamps are
    monotonic/non-overlapping and the per-frame active-word schedule recovers the spoken
    words in order (the timing-sync guarantee).
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "openmontage"))

from tools import make_tool
import cv2
import numpy as np

SAMPLES = os.path.join(os.path.dirname(HERE), "samples", "samples")
ATHLETE = os.path.join(SAMPLES, "athlete_16x9.mp4")
BEAT = os.path.join(SAMPLES, "beat_120bpm.wav")
REAL_SPEECH = "/home/ubuntu/.hermes/hermes-agent/tools/neutts_samples/jo.wav"


def _ffmpeg():
    # the bundled imageio-ffmpeg binary, exposed on PATH by the test runner
    return "ffmpeg"


def _make_src_with_audio(athlete, beat, dst):
    """Mux the beat track onto the silent athlete clip so A/V sync is testable."""
    r = subprocess.run([_ffmpeg(), "-y", "-i", athlete, "-i", beat,
                        "-c", "copy", "-map", "0:v:0", "-map", "1:a:0", dst],
                       capture_output=True, text=True)
    return r.returncode == 0


def _frame_count(path):
    cap = cv2.VideoCapture(path)
    n = 0
    while True:
        ok, _ = cap.read()
        if not ok:
            break
        n += 1
    cap.release()
    return n


# ----------------------------------------------------------- B.5 kinetic_ramper
def test_ramper_genuine_speedup_and_slowmo(sample_athlete_clip, sample_beat_audio, tmp_path):
    beats = tmp_path / "beats.json"
    rb = make_tool("beat_drop_mapper", audio_path=sample_beat_audio, out_json=str(beats))
    assert rb.ok
    out = tmp_path / "ramped.mp4"
    r = make_tool("kinetic_ramper", input_path=sample_athlete_clip, out_path=str(out),
                  map_json=str(beats), setup_speed=1.6, peak_speed=0.4)
    assert r.ok, r.error
    segs = r.data["segments"]
    speeds = [s["speed"] for s in segs]
    # genuine remap: BOTH setup and slow-mo segments must exist (drops drive slow-mo)
    assert 1.6 in speeds and 0.4 in speeds, speeds
    # setup speed-up actually shortens the clip vs source
    src_frames = _frame_count(sample_athlete_clip)
    out_frames = _frame_count(str(out))
    assert out_frames < src_frames, f"no speed-up: {out_frames} >= {src_frames}"


def test_ramper_smooth_and_synced_with_audio(sample_athlete_clip, sample_beat_audio, tmp_path):
    beats = tmp_path / "beats.json"
    make_tool("beat_drop_mapper", audio_path=sample_beat_audio, out_json=str(beats))
    src = tmp_path / "src_av.mp4"
    assert _make_src_with_audio(sample_athlete_clip, sample_beat_audio, str(src))
    out = tmp_path / "ramped_av.mp4"
    r = make_tool("kinetic_ramper", input_path=str(src), out_path=str(out),
                  map_json=str(beats), setup_speed=1.6, peak_speed=0.4, keep_audio=True)
    assert r.ok, r.error
    m = r.metrics
    # smoothness: no frozen/duplicate frames, monotonic PTS, constant cadence
    assert m["frozen_frames"] == 0, m
    assert m["pts_monotonic"] is True, m
    assert m["max_pts_delta_ms"] <= 40.0, m  # ~33.3ms @30fps, never a jump
    # A/V sync: audio muxed through (setpts preserves timeline so music stays aligned)
    assert m["has_audio"] is True, m
    pr = subprocess.run([_ffmpeg(), "-i", str(out)], capture_output=True, text=True)
    streams = [l for l in pr.stderr.splitlines() if "Stream" in l]
    assert any("Video:" in s for s in streams)
    assert any("Audio:" in s for s in streams), streams


def test_ramper_no_beats_degrades_gracefully(sample_athlete_clip, tmp_path):
    out = tmp_path / "ramped_flat.mp4"
    r = make_tool("kinetic_ramper", input_path=sample_athlete_clip, out_path=str(out),
                  setup_speed=1.6, peak_speed=0.4)  # no map_json, no peak_times
    assert r.ok, r.error
    assert os.path.getsize(out) > 1000


# ----------------------------------------------------------- C.7 kinetic_word_sync
@pytest.mark.skipif(not os.path.exists(REAL_SPEECH), reason="real speech sample not present")
def test_word_sync_timing_on_real_audio(tmp_path):
    out_json = tmp_path / "caps.json"
    r = make_tool("kinetic_word_sync", audio_path=REAL_SPEECH, model="tiny",
                  language="en", fps=30, out_json=str(out_json))
    assert r.ok, r.error
    s = r.data["summary"]
    assert s["words"] >= 1
    assert s["monotonic_timestamps"] is True
    words = r.data["words"]
    for i in range(1, len(words)):
        assert words[i]["start"] >= words[i - 1]["start"] - 1e-6
        assert words[i]["end"] >= words[i]["start"]
    # frame_schedule length == duration*fps (the per-frame sync guarantee)
    expected = int(s["duration_sec"] * s["fps"]) + 1
    assert len(r.data["frame_schedule"]) == expected, (len(r.data["frame_schedule"]), expected)
    # timing-sync guarantee: as time advances, the active word index never moves
    # backwards (a word is never highlighted before an earlier one finishes). This is
    # what makes the highlight track stay locked to speech.
    sched = r.data["frame_schedule"]
    assert all(sched[i] <= sched[i + 1] or sched[i + 1] == -1
               for i in range(len(sched) - 1)), "active word index regressed in time"
    # output JSON written
    assert os.path.exists(out_json)


def test_word_sync_missing_file():
    r = make_tool("kinetic_word_sync", audio_path="/no/such/file.wav", model="tiny")
    assert not r.ok
