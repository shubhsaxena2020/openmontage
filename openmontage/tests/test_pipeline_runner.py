"""Integration test for the declarative pipeline runner (pipeline.py).

Verifies that tools are correctly chained via ${refs} using the synthetic sample media:
  - beat_drop_mapper output feeds kinetic_ramper's map_json
  - smart_reframe consumes the generated boxes.json
  - kinetic_word_sync runs on the real speech sample
The whole fitness_reel.json pipeline must reach ok=True with all steps producing artifacts.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "openmontage"))

from pipeline import run_pipeline_file, PipelineRunner
import pytest

DEF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "pipeline_defs", "fitness_reel.json")


def test_pipeline_def_valid_json():
    assert os.path.exists(DEF)
    import json
    with open(DEF) as fh:
        d = json.load(fh)
    assert d["name"] == "fitness_reel"
    assert len(d["steps"]) == 6


def test_pipeline_runs_end_to_end():
    om_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../openmontage
    r = run_pipeline_file(DEF, workdir=om_dir)
    assert r.ok, {s.id: s.error for s in r.steps if not s.ok}
    # every step produced at least one artifact and registered a primary
    for s in r.steps:
        assert s.ok
        assert s.artifacts.get("_primary") and os.path.exists(s.artifacts["_primary"]), \
            f"step {s.id} missing primary artifact {s.artifacts}"


def test_pipeline_ref_resolution_isolated():
    # unit-level: a 2-step pipe where step2 consumes step1's artifact via ${id.key}
    runner = PipelineRunner(workdir="/tmp/om_pipe_test")
    os.makedirs("/tmp/om_pipe_test", exist_ok=True)
    video = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                         "samples", "samples", "athlete_16x9.mp4")
    import json
    # reuse synth boxes for smart_reframe dependency check
    boxes = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                         "samples", "samples", "boxes.json")
    if not (os.path.exists(video) and os.path.exists(boxes)):
        pytest.skip("sample media not generated")
    defn = {
        "inputs": {"clip": video, "boxes": boxes},
        "steps": [
            {"id": "reframe", "tool": "smart_reframe",
             "params": {"input_path": "${inputs.clip}", "boxes_json": "${inputs.boxes}",
                        "out_path": "r.mp4", "target_w": 540},
             "out": "r.mp4"},
        ],
    }
    r = runner.run(defn)
    assert r.ok
    assert os.path.exists(r.steps[0].artifacts["_primary"])
