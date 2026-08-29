"""Items 5-10 — batch processing tests.

Covers: manifest fan-out, per-item reporting, retry w/ bounded backoff (and a testable retry
count), artifact validation (early reject bad inputs), parallel worker pool (clobber-free),
and structured progress reporting. All run on the VPS via the orchestrator's graceful-degrade
path (no Remotion needed). Uses the real athlete sample clip.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "openmontage"))

from kinetic_studio.config import KineticStudioConfig
from kinetic_studio import batch as batchmod
from kinetic_studio.batch import (load_manifest, validate_job, run_batch,
                                  JobValidationError, BatchProgress)

SAMPLES = os.path.join(os.path.dirname(HERE), "samples", "samples")
ATHLETE = os.path.join(SAMPLES, "athlete_16x9.mp4")


def _manifest(tmp, n=2):
    items = [{"clip": ATHLETE, "out_name": f"clip{i}.mp4"} for i in range(n)]
    path = os.path.join(tmp, "manifest.json")
    with open(path, "w") as fh:
        json.dump(items, fh)
    return path


def test_load_manifest_parses_list(tmp_path):
    p = _manifest(tmp_path, 3)
    m = load_manifest(p)
    assert isinstance(m, list) and len(m) == 3
    # missing 'clip' rejected
    bad = os.path.join(tmp_path, "bad.json")
    json.dump([{"music": "x.mp3"}], open(bad, "w"))
    with pytest.raises(JobValidationError):
        load_manifest(bad)


def test_validate_job_rejects_bad_inputs(tmp_path):
    # missing file
    with pytest.raises(JobValidationError):
        validate_job({"clip": "/no/such/clip.mp4"})
    # unsupported extension
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(JobValidationError):
        validate_job({"clip": str(f)})
    # empty file
    g = tmp_path / "b.mp4"
    g.write_bytes(b"")
    with pytest.raises(JobValidationError):
        validate_job({"clip": str(g)})
    # good clip passes and resolves an absolute path
    r = validate_job({"clip": ATHLETE})
    assert os.path.exists(r["clip"])


def test_validate_job_checks_music_and_voiceover(tmp_path):
    # music referenced but missing -> reject early
    with pytest.raises(JobValidationError):
        validate_job({"clip": ATHLETE, "music": "/no/such/track.mp3"})
    # missing voiceover rejected
    with pytest.raises(JobValidationError):
        validate_job({"clip": ATHLETE, "voiceover": "vo.mp3"})


def test_batch_fanout_reports_per_item(tmp_path):
    p = _manifest(tmp_path, 2)
    m = load_manifest(p)
    prog = run_batch(m, KineticStudioConfig(), str(tmp_path / "out"), workers=1)
    assert prog.total == 2
    assert prog.completed == 2
    assert prog.succeeded == 2, prog.items
    assert prog.failed == 0
    # each item has a status record with output path, and the file exists
    outs = [it["output"] for it in prog.items if it.get("status") == "ok"]
    assert len(outs) == 2
    for o in outs:
        assert os.path.exists(o)


def test_batch_early_rejects_invalid_and_continues(tmp_path):
    # 1 valid + 1 invalid (missing clip). Invalid is rejected up front; valid still runs.
    items = [{"clip": ATHLETE, "out_name": "good.mp4"},
             {"clip": "/no/such.mp4", "out_name": "bad.mp4"}]
    prog = run_batch(items, KineticStudioConfig(), str(tmp_path / "out"), workers=1)
    assert prog.total == 2
    assert prog.succeeded == 1
    assert prog.failed == 1
    failed = [it for it in prog.items if it.get("status") == "failed"]
    assert any("validation" in (it.get("error") or "") for it in failed)


def test_batch_clobber_free_on_duplicate_out_names(tmp_path):
    # two jobs would both write clip.mp4 -> second gets a unique suffix, both succeed
    items = [{"clip": ATHLETE, "out_name": "clip.mp4"},
             {"clip": ATHLETE, "out_name": "clip.mp4"}]
    prog = run_batch(items, KineticStudioConfig(), str(tmp_path / "out"), workers=1)
    assert prog.succeeded == 2
    outs = {os.path.basename(it["output"]) for it in prog.items if it.get("status") == "ok"}
    assert len(outs) == 2, outs  # distinct filenames


def test_batch_retry_counts_and_recovers(tmp_path, monkeypatch):
    # Force the orchestrator's run to fail on first N attempts, succeed after.
    from kinetic_studio import orchestrator as orch
    calls = {"n": 0}
    real_run = orch.KineticStudio.run

    def flaky(self, *a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            class _R:
                ok = False
                final_video = None
                steps = []
                audio_used = None
            return _R()
        return real_run(self, *a, **k)

    monkeypatch.setattr(orch.KineticStudio, "run", flaky)
    p = _manifest(tmp_path, 1)
    m = load_manifest(p)
    prog = run_batch(m, KineticStudioConfig(), str(tmp_path / "out"),
                     workers=1, max_retries=3, retry_base=0.01)
    assert prog.succeeded == 1, prog.items
    # the successful record must reflect the >=3 attempts (2 fails + 1 success)
    rec = [it for it in prog.items if it.get("status") == "ok"][0]
    assert rec["attempts"] >= 3, rec  # 2 failed + 1 success => 3 attempts


def test_batch_retry_exhausts_then_fails(tmp_path, monkeypatch):
    from kinetic_studio import orchestrator as orch
    calls = {"n": 0}
    real_run = orch.KineticStudio.run

    def always_fail(self, *a, **k):
        calls["n"] += 1
        class _R:
            ok = False; final_video = None; steps = []; audio_used = None
        return _R()

    monkeypatch.setattr(orch.KineticStudio, "run", always_fail)
    p = _manifest(tmp_path, 1)
    m = load_manifest(p)
    prog = run_batch(m, KineticStudioConfig(), str(tmp_path / "out"),
                     workers=1, max_retries=2, retry_base=0.01)
    assert prog.succeeded == 0 and prog.failed == 1
    rec = [it for it in prog.items if it.get("status") == "failed"][0]
    assert rec["attempts"] == 2, rec  # exactly max_retries attempts


def test_batch_parallel_workers(tmp_path):
    # workers>1 must still produce all outputs correctly (parallel fan-out).
    # Disable the CPU-heavy pose step so 2 concurrent processes don't OOM the host.
    cfg = KineticStudioConfig()
    cfg.pose.enabled = False
    items = [{"clip": ATHLETE, "out_name": f"p{i}.mp4"} for i in range(2)]
    prog = run_batch(items, cfg, str(tmp_path / "out"), workers=2)
    assert prog.succeeded == 2, prog.items
    for it in prog.items:
        if it.get("status") == "ok":
            assert os.path.exists(it["output"])


def test_batch_structured_progress(tmp_path):
    captured = []
    p = _manifest(tmp_path, 2)
    m = load_manifest(p)
    prog = run_batch(m, KineticStudioConfig(), str(tmp_path / "out"),
                     workers=1, on_progress=lambda pr: captured.append(pr.to_dict()))
    # progress emitted at least at completion, with the right structure
    assert captured
    last = captured[-1]
    assert {"total", "completed", "succeeded", "failed", "items"} <= set(last)
    assert last["total"] == 2 and last["completed"] == 2
    # every item record carries a status
    assert all("status" in it for it in last["items"])
