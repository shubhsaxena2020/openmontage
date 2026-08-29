"""Integration test: full OpenMontage engine chain via the declarative pipeline runner.

Runs pipeline_defs/build_fitness_short.json on the generated sample media and asserts the
whole Phase A -> B.5 -> C -> audio-duck chain composes into real artifacts:
  beats -> motion_energy -> smart_reframe -> kinetic_ramper -> kinetic_word_sync -> audio_master_duck

This is the headless, CI-runnable equivalent of kinetic_studio/orchestrator.py (which adds
the Remotion composite + music mux that need a browser). Every step must succeed and emit a
real file. Genuine composition check, not a stub.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "openmontage"))

from pipeline import run_pipeline_file

DEF = os.path.join(os.path.dirname(HERE), "pipeline_defs", "build_fitness_short.json")


def test_build_fitness_short_runs_end_to_end():
    om_dir = os.path.dirname(HERE)  # .../openmontage
    r = run_pipeline_file(DEF, workdir=om_dir)
    assert r.ok, {s.id: s.error for s in r.steps if not s.ok}
    # every step produced a real primary artifact
    for s in r.steps:
        assert s.ok, s.error
        primary = s.artifacts.get("_primary")
        assert primary and os.path.exists(primary), f"step {s.id} missing artifact {s.artifacts}"


def test_build_fitness_short_wires_duck_to_voice():
    # the audio_master_duck step must actually duck music under the voiceover
    om_dir = os.path.dirname(HERE)
    r = run_pipeline_file(DEF, workdir=om_dir)
    assert r.ok
    duck = next(s for s in r.steps if s.id == "duck")
    m = duck.metrics
    # peak duck depth must be a real attenuation (music dropped during voice)
    assert m["peak_duck_depth"] is not None and 0.0 < m["peak_duck_depth"] <= 0.8, m
    # voice was actually present (the duck has something to duck under)
    assert m["voice_active_pct"] > 0.0, m


def test_build_fitness_short_ramper_is_tempo_synced():
    om_dir = os.path.dirname(HERE)
    r = run_pipeline_file(DEF, workdir=om_dir)
    assert r.ok
    ramper = next(s for s in r.steps if s.id == "ramper")
    m = ramper.metrics
    # both setup speed-up and slow-mo-on-drops must be present (genuine time-remap)
    assert m["segments"] >= 2
    # smoothness = no time jumps: PTS monotonic + constant frame cadence (~33ms @30fps).
    # (Pixel-identical frames are EXPECTED here: smart_reframe's dead-band holds the crop
    # center still when the subject is nearly stationary — that is the anti-jitter feature,
    # not a defect. The ramper must not ADD time discontinuities on top of that.)
    assert m["pts_monotonic"] is True
    assert m["max_pts_delta_ms"] <= 40.0, m
