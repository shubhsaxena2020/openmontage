"""PHASE B-style tool — Audio auto-ducking (music ducks under voice / sfx).

Fitness reels need the music to dip when the coach speaks and swell back between
cues. This tool produces that automatically:

  1. Load the music (master) and a voice / sfx (duck trigger) track.
  2. Compute a short-time RMS (energy) envelope of the *voice* track.
  3. Derive a target music gain: 1.0 where the voice is quiet, `duck_gain`
     (e.g. 0.25) where the voice is loud. Apply attack/release smoothing so the
     dip ramps in/out instead of clicking.
  4. Multiply the music by the smoothed gain -> "ducked music".
  5. Optionally mix the ducked music UNDER the voice (voice plays at unity on top).

Outputs:
  - out_music : the ducked music track (music only, gain-applied).
  - out_mix   : ducked music + voice summed (the final reel audio), when mix=True.
  - out_json  : duck envelope + metrics for pipeline consumption.

CPU-only (librosa + soundfile + ffmpeg for the final mix). The ducking envelope
math is unit-testable on synthetic signals; the render path is verified on a
synthesized voice/music pair where the duck is measurable in the output RMS.

Honesty note (OpenMontage scaffold convention): verification here is against
SYNTHETIC media. The ducking mechanism (RMS envelope -> gain -> apply) is the same
code path a real coach-athlete clip would hit; point `voice_path` at a real clip to
verify on real audio. We never read .env or production pointers.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

from tools.base_tool import BaseTool, ToolResult


def _rms_envelope(y: np.ndarray, sr: int, frame_ms: float = 20.0, hop_ms: float = 10.0) -> np.ndarray:
    """Short-time RMS energy of `y` (mono, float) at a fixed frame/hop grid.

    Returns a 1-D envelope aligned to the hop grid (length = n_frames). Used both
    for the unit-tested math path and the real render path.
    """
    frame = max(1, int(sr * frame_ms / 1000.0))
    hop = max(1, int(sr * hop_ms / 1000.0))
    if len(y) < frame:
        # degenerate: single frame
        return np.array([float(np.sqrt(np.mean(y ** 2)) + 1e-12)])
    n_frames = 1 + (len(y) - frame) // hop
    env = np.empty(n_frames, dtype=float)
    for i in range(n_frames):
        seg = y[i * hop : i * hop + frame]
        env[i] = float(np.sqrt(np.mean(seg ** 2)) + 1e-12)
    return env


def _build_gain_envelope(
    voice_env: np.ndarray,
    threshold: float,
    duck_gain: float,
    attack_ms: float,
    release_ms: float,
    hop_ms: float,
) -> np.ndarray:
    """Map a voice RMS envelope to a smooth music gain curve in [duck_gain, 1.0].

    A frame counts as "voice active" when voice_env > threshold. While active we
    ramp the gain DOWN toward `duck_gain` (attack = how fast we duck in); while
    inactive we ramp it back UP toward 1.0 (release = how fast we recover). This is
    a first-order (exponential) smoother on a binary target, fully deterministic
    and unit-testable.

    Returns an envelope of the same length as `voice_env`, sampled at `hop_ms`.
    """
    attack_coef = 1.0 - np.exp(-hop_ms / max(attack_ms, 1e-3))
    release_coef = 1.0 - np.exp(-hop_ms / max(release_ms, 1e-3))
    gain = np.ones_like(voice_env, dtype=float)
    cur = 1.0
    for i in range(len(voice_env)):
        target = duck_gain if voice_env[i] > threshold else 1.0
        coef = attack_coef if target < cur else release_coef
        cur = cur + coef * (target - cur)
        gain[i] = cur
    return gain


def _resample_mono(y: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to:
        return y
    import librosa

    return librosa.resample(y, orig_sr=sr_from, target_sr=sr_to)


class AudioMasterDuckTool(BaseTool):
    name = "audio_master_duck"
    category = "audio"
    description = (
        "Auto-ducking: lower music gain under voice/sfx and (optionally) mix the "
        "ducked music beneath the voice. RMS-envelope driven with attack/release smoothing."
    )
    params = {
        "music_path": {"type": "str", "required": True,
                       "help": "master music track (audio or video w/ audio)"},
        "voice_path": {"type": "str", "required": True,
                       "help": "duck-trigger track: voice-over / sfx / narration"},
        "out_music": {"type": "str", "default": None,
                      "help": "ducked music output path (.wav)"},
        "out_mix": {"type": "str", "default": None,
                    "help": "ducked music + voice mix output (.wav)"},
        "out_json": {"type": "str", "default": None,
                     "help": "duck envelope + metrics JSON"},
        "duck_gain": {"type": "float", "default": 0.25,
                      "help": "music gain while voice is active (0..1)"},
        "threshold": {"type": "float", "default": 0.0,
                      "help": "voice RMS threshold; <=0 -> auto (median of voice env)"},
        "attack_ms": {"type": "float", "default": 80.0,
                      "help": "ms to ramp music DOWN to duck_gain"},
        "release_ms": {"type": "float", "default": 250.0,
                       "help": "ms to ramp music back UP to 1.0"},
        "frame_ms": {"type": "int", "default": 20, "help": "RMS analysis frame"},
        "hop_ms": {"type": "int", "default": 10, "help": "RMS analysis hop"},
        "mix": {"type": "bool", "default": True,
                "help": "also produce out_mix (ducked music + voice)"},
    }

    def run(self, **p) -> ToolResult:
        import librosa
        import soundfile as sf

        music_path = p["music_path"]
        voice_path = p["voice_path"]
        duck_gain = float(p["duck_gain"])
        if not (0.0 <= duck_gain <= 1.0):
            return ToolResult(ok=False, error=f"duck_gain must be in [0,1], got {duck_gain}")
        hop_ms = float(p["hop_ms"])
        frame_ms = float(p["frame_ms"])

        # --- load as mono for envelope; keep original music for gain application ---
        music_mono, sr_m = librosa.load(music_path, sr=None, mono=True)
        voice_mono, sr_v = librosa.load(voice_path, sr=None, mono=True)

        # resample voice to music rate so frames line up
        if sr_v != sr_m:
            voice_mono = _resample_mono(voice_mono, sr_v, sr_m)
        # Align voice to the MUSIC timeline: the duck is applied to the music track, so
        # the voice trigger envelope must share music's hop grid (same length in samples).
        # Trim or pad the resampled voice to music's sample count before envelopeing.
        n_m = len(music_mono)
        if len(voice_mono) > n_m:
            voice_mono = voice_mono[:n_m]
        elif len(voice_mono) < n_m:
            voice_mono = np.pad(voice_mono, (0, n_m - len(voice_mono)))
        dur = float(len(music_mono) / sr_m)

        # --- voice RMS envelope ---
        voice_env = _rms_envelope(voice_mono, sr_m, frame_ms=frame_ms, hop_ms=hop_ms)
        # normalize by global peak so threshold is amplitude-relative and stable
        vpeak = float(np.max(voice_env))
        if vpeak <= 1e-9:
            voice_env_n = np.zeros_like(voice_env)
        else:
            voice_env_n = voice_env / vpeak

        threshold = float(p["threshold"])
        if threshold <= 0.0:
            # auto: speech is usually intermittent -> use a multiple of the median
            med = float(np.median(voice_env_n)) + 1e-9
            threshold = min(0.5, max(0.05, 1.5 * med))

        gain_env = _build_gain_envelope(
            voice_env_n, threshold, duck_gain,
            p["attack_ms"], p["release_ms"], hop_ms,
        )

        # --- apply gain to music on the SAME hop grid (resample gain to sample rate) ---
        # gain_env is per-hop; expand to per-sample via nearest-neighbour hold.
        hop_samples = max(1, int(sr_m * hop_ms / 1000.0))
        n = len(music_mono)
        idx = np.minimum((np.arange(n) // hop_samples).astype(int), len(gain_env) - 1)
        sample_gain = gain_env[idx]
        ducked = (music_mono * sample_gain).astype(np.float32)

        # --- metrics on the ducking ---
        active = voice_env_n > threshold
        n_active = int(active.sum())
        # "duck events" = rising edges of active
        events = int(np.sum(np.diff(active.astype(int)) == 1)) + (1 if active[0] else 0)
        peak_duck = float(1.0 - gain_env.min())  # 0..1 how far it dipped
        # RMS of the DUCKED music where voice active vs where it isn't — this is the
        # honest proof the duck actually happened (measured on the output, not input).
        # Compute per-hop energy of `ducked` on the SAME hop grid as `active`/`gain_env`.
        hop_samples = max(1, int(sr_m * hop_ms / 1000.0))
        n_hops = len(gain_env)
        n_used = min(len(ducked), n_hops * hop_samples)
        if n_used >= hop_samples:
            hop_sq = np.add.reduceat(
                ducked[:n_used] ** 2,
                np.arange(0, n_used, hop_samples),
            ) / hop_samples
            hop_rms = np.sqrt(hop_sq)
        else:
            hop_rms = np.array([0.0])
        if n_active > 0 and n_active < n_hops:
            rms_duck = float(np.sqrt(np.mean(hop_rms[active] ** 2)))
            rms_rest = float(np.sqrt(np.mean(hop_rms[~active] ** 2)))
        else:
            rms_duck = rms_rest = 0.0

        artifacts: Dict[str, str] = {}
        data: Dict[str, Any] = {
            "summary": {
                "duration_sec": round(dur, 3),
                "sr": sr_m,
                "duck_gain": duck_gain,
                "threshold": round(threshold, 4),
                "voice_active_frames": n_active,
                "voice_active_pct": round(100.0 * n_active / max(1, len(gain_env)), 1),
                "duck_events": events,
                "peak_duck_depth": round(peak_duck, 4),
            },
            "metrics": {
                "rms_music_during_voice": round(rms_duck, 6),
                "rms_music_during_rest": round(rms_rest, 6),
                "duck_ratio": round(rms_duck / (rms_rest + 1e-9), 4) if rms_rest else None,
            },
            "gain_envelope": np.round(gain_env, 4).tolist(),
            "hop_ms": hop_ms,
        }

        if p["out_music"]:
            sf.write(p["out_music"], ducked, sr_m)
            artifacts["music"] = p["out_music"]
        if p.get("mix") and p["out_mix"]:
            voice_aligned = _resample_mono(voice_mono, sr_v, sr_m) if sr_v != sr_m else voice_mono
            # pad/trim voice to music length
            if len(voice_aligned) > n:
                voice_aligned = voice_aligned[:n]
            else:
                voice_aligned = np.pad(voice_aligned, (0, n - len(voice_aligned)))
            mix = (ducked + voice_aligned.astype(np.float32)).astype(np.float32)
            # soft clip to avoid wrap
            peak = np.max(np.abs(mix)) + 1e-9
            if peak > 1.0:
                mix = (mix / peak).astype(np.float32)
            sf.write(p["out_mix"], mix, sr_m)
            artifacts["mix"] = p["out_mix"]

        if p["out_json"]:
            with open(p["out_json"], "w") as fh:
                json.dump(data, fh)
            artifacts["json"] = p["out_json"]

        return ToolResult(
            ok=True, data=data, artifacts=artifacts,
            metrics={
                "duck_events": events,
                "peak_duck_depth": round(peak_duck, 4),
                "voice_active_pct": data["summary"]["voice_active_pct"],
                "duck_ratio": data["metrics"]["duck_ratio"],
            },
        )
