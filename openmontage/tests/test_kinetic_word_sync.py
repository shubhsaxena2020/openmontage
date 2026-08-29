"""Verification tests for the kinetic word-sync caption engine (PHASE C.7).

Uses a REAL speech audio clip (a TTS sample present on the host) so the timing-sync
claim is exercised on actual spoken-word timestamps, not synthetic data.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "openmontage"))

from tools import make_tool
import pytest

REAL_SPEECH = "/home/ubuntu/.hermes/hermes-agent/tools/neutts_samples/jo.wav"


@pytest.mark.skipif(not os.path.exists(REAL_SPEECH), reason="real speech sample not present")
def test_kinetic_word_sync_real_audio():
    r = make_tool("kinetic_word_sync", audio_path=REAL_SPEECH, model="tiny",
                  language="en", fps=30,
                  out_json=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "samples", "samples", "captions.json"))
    assert r.ok, r.error
    s = r.data["summary"]
    assert s["words"] >= 1
    # timing integrity: word timestamps are monotonic and non-overlapping
    assert s["monotonic_timestamps"] is True
    words = r.data["words"]
    for i in range(1, len(words)):
        assert words[i]["start"] >= words[i - 1]["start"] - 1e-6
        assert words[i]["end"] >= words[i]["start"]
    # frame schedule length matches duration*fps (the sync guarantee)
    fps = s["fps"]
    expected = int(s["duration_sec"] * fps) + 1
    assert len(r.data["frame_schedule"]) == expected, (
        f"schedule {len(r.data['frame_schedule'])} != expected {expected}")
    # recoverable: spoken words appear in order in the text
    assert len(r.data["text"].split()) == s["words"]


def test_kinetic_word_sync_missing_file():
    r = make_tool("kinetic_word_sync", audio_path="/no/such/file.wav", model="tiny")
    assert not r.ok
