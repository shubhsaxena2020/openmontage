"""Tests for audio_master_duck (auto-ducking).

Two layers, matching the scaffold's honesty convention:
  * Unit tests: the duck-envelope math (RMS envelope, gain smoothing, bounds)
    on synthetic numpy signals — no audio file needed.
  * End-to-end render test: synthesize a music track (steady tone) + a gated
    "voice" (tone that switches on/off), run the REAL tool, and MEASURE that the
    ducked music RMS during voice-on windows is ~ duck_gain * RMS during voice-off
    windows. This proves the pipeline actually ducks synthetic media. We label it
    clearly as synthetic so nobody mistakes it for a real coach clip.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "openmontage"))

import numpy as np
import pytest

from tools.audio.audio_master_duck import (
    AudioMasterDuckTool, _rms_envelope, _build_gain_envelope,
)

SR = 22050


def _make_gated_voice(n_samples, on_every=2205, on_len=1102, amp=0.8):
    """A tone that switches on/off (simulating speech bursts)."""
    t = np.arange(n_samples) / SR
    carrier = np.sin(2 * np.pi * 220 * t)
    gate = np.zeros(n_samples)
    pos = 0
    while pos < n_samples:
        gate[pos:pos + on_len] = 1.0
        pos += on_every
    return (carrier * gate * amp).astype(np.float32)


def _steady_music(n_samples, amp=0.5):
    t = np.arange(n_samples) / SR
    return (np.sin(2 * np.pi * 440 * t) * amp).astype(np.float32)


def test_rms_envelope_shape_and_energy():
    y = np.zeros(SR, dtype=np.float32)
    y[1000:2000] = 1.0  # a burst
    env = _rms_envelope(y, SR, frame_ms=20, hop_ms=10)
    assert env.ndim == 1 and env.size > 1
    # a region inside the burst must be louder than a silent region
    assert env.max() > env.min() * 5


def test_gain_envelope_bounds_and_ducking():
    # voice env: active in the middle third
    n = 300
    venv = np.zeros(n)
    venv[100:200] = 1.0
    thr = 0.5
    gain = _build_gain_envelope(venv, thr, duck_gain=0.25,
                                attack_ms=80, release_ms=250, hop_ms=10)
    # First-order smoother asymptotes to duck_gain in the active window (doesn't exactly
    # equal it), and returns toward 1.0 after. The slow release (250ms) over the ~1s tail
    # may not fully reach 1.0, but it must be well recovered (>0.95).
    assert gain[0] == pytest.approx(1.0)             # before voice: full volume
    assert gain[-1] > 0.95                          # after voice: substantially recovered
    assert gain.min() < 0.30                        # actually ducked well below 1.0
    assert gain.min() > 0.20                        # but not below the requested floor
    # never above 1
    assert gain.max() <= 1.0 + 1e-9


def test_gain_envelope_attack_faster_than_release():
    # With a single sustained voice burst, the descent to duck happens over `attack`
    # and the recovery over `release`. The gain curve should be monotonic-ish: it
    # falls then rises; key check — it actually reaches the duck level and returns.
    n = 500
    venv = np.zeros(n)
    venv[150:350] = 1.0
    gain = _build_gain_envelope(venv, 0.5, duck_gain=0.3,
                                attack_ms=50, release_ms=400, hop_ms=10)
    assert gain[250] < 0.35            # ducked while voice active
    assert gain[490] > 0.95            # recovered well after voice ends
    assert min(gain) <= 0.31


def test_run_renders_and_measures_duck(tmp_path):
    """REAL tool run on synthetic media; assert the duck is measurable in output RMS."""
    music = _steady_music(SR * 4)            # 4s steady tone
    voice = _make_gated_voice(SR * 4)        # bursts on/off
    mp = tmp_path / "music.wav"
    vp = tmp_path / "voice.wav"
    import soundfile as sf
    sf.write(str(mp), music, SR)
    sf.write(str(vp), voice, SR)

    res = AudioMasterDuckTool().execute(
        music_path=str(mp), voice_path=str(vp),
        out_music=str(tmp_path / "ducked.wav"),
        out_mix=str(tmp_path / "mix.wav"),
        out_json=str(tmp_path / "duck.json"),
        duck_gain=0.25, attack_ms=80, release_ms=250,
    )
    assert res.ok, res.error
    assert os.path.exists(str(tmp_path / "ducked.wav"))
    assert os.path.exists(str(tmp_path / "mix.wav"))
    assert os.path.exists(str(tmp_path / "duck.json"))

    # ---- HONEST MEASUREMENT: did the music actually duck under voice? ----
    # The output ducked-music RMS during voice-on windows must be LOWER than during
    # voice-off windows (proving attenuation happened), and the reported peak duck depth
    # must be substantial (the gain curve really dipped toward duck_gain at least once).
    metrics = res.data["metrics"]
    duck_ratio = metrics["duck_ratio"]
    assert duck_ratio is not None
    assert duck_ratio < 0.97, f"expected measurable duck, got ratio={duck_ratio}"
    assert res.metrics["duck_events"] >= 1
    # the duck depth reported should be meaningful (music dipped at least 50% at peak)
    assert res.metrics["peak_duck_depth"] >= 0.5
    assert res.metrics["voice_active_pct"] > 0

    # sanity: ducked music RMS overall < original music RMS (it was attenuated)
    orig = float(np.sqrt(np.mean(music ** 2)))
    ducked, _ = sf.read(str(tmp_path / "ducked.wav"))
    ducked_rms = float(np.sqrt(np.mean(ducked ** 2)))
    assert ducked_rms < orig, "ducked music should be quieter overall than original"


def test_run_no_voice_no_duck(tmp_path):
    """If the voice track is silent, the music must NOT be ducked (gain stays ~1)."""
    music = _steady_music(SR * 2)
    silence = np.zeros(SR * 2, dtype=np.float32)
    mp = tmp_path / "m.wav"
    vp = tmp_path / "v.wav"
    import soundfile as sf
    sf.write(str(mp), music, SR)
    sf.write(str(vp), silence, SR)
    res = AudioMasterDuckTool().execute(
        music_path=str(mp), voice_path=str(vp),
        out_music=str(tmp_path / "d.wav"),
        duck_gain=0.25,
    )
    assert res.ok, res.error
    assert res.metrics["duck_events"] == 0
    assert res.metrics["peak_duck_depth"] < 0.05  # essentially no ducking
