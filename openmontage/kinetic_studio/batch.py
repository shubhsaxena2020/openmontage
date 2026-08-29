"""Kinetic Studio batch processing.

Fan a manifest of clips out to parallel, retryable, validated Kinetic Studio runs with
structured progress reporting. Everything here is testable on the VPS (no Remotion needed):
the orchestrator degrades gracefully when the HUD composite can't render.

Manifest format (JSON list of objects), each item may override any field:
    [
      {"clip": "clips/gym1.mp4", "music": "tracks/hype.mp3",
       "voiceover": "vo/gym1.mp3", "brand": "FBC Arena", "preset": "energetic"},
      {"clip": "clips/gym2.mp4", "preset": "cinematic", "out_name": "gym2_short.mp4"}
    ]
Per-item overrides are merged over the base KineticStudioConfig: clip/music/voiceover are
inputs; brand/preset/ramp/markers etc. tweak the config.
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from kinetic_studio.config import KineticStudioConfig
from kinetic_studio.orchestrator import KineticStudio
from kinetic_studio import presets as preset_lib

SUPPORTED_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


class JobValidationError(Exception):
    pass


@dataclass
class BatchProgress:
    """Structured, machine-readable progress for a batch run."""
    total: int
    completed: int = 0
    succeeded: int = 0
    failed: int = 0
    in_progress: List[str] = field(default_factory=list)
    items: List[Dict[str, Any]] = field(default_factory=list)  # per-item status records

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total, "completed": self.completed,
            "succeeded": self.succeeded, "failed": self.failed,
            "in_progress": list(self.in_progress), "items": self.items,
        }


def load_manifest(path: str) -> List[Dict[str, Any]]:
    with open(path) as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise JobValidationError("manifest must be a JSON list of job objects")
    for i, job in enumerate(data):
        if not isinstance(job, dict) or "clip" not in job:
            raise JobValidationError(f"manifest item {i} missing 'clip'")
    return data


def validate_job(job: Dict[str, Any], root: str = "") -> Dict[str, Any]:
    """Early-reject a bad job before spending any compute.

    Checks: clip exists, is a supported video type, non-empty. music/voiceover (if given)
    must exist. Returns the resolved absolute paths. Raises JobValidationError otherwise.
    """
    def _resolve(p):
        return os.path.abspath(os.path.join(root, p)) if root else os.path.abspath(p)

    clip = job.get("clip")
    if not clip:
        raise JobValidationError("missing 'clip'")
    clip_path = _resolve(clip)
    if not os.path.exists(clip_path):
        raise JobValidationError(f"clip not found: {clip_path}")
    ext = os.path.splitext(clip_path)[1].lower()
    if ext not in SUPPORTED_VIDEO_EXT:
        raise JobValidationError(f"unsupported video type: {ext}")
    if os.path.getsize(clip_path) == 0:
        raise JobValidationError(f"clip is empty: {clip_path}")

    resolved = {"clip": clip_path}
    for key in ("music", "voiceover"):
        v = job.get(key)
        if v:
            vp = _resolve(v)
            if not os.path.exists(vp):
                raise JobValidationError(f"{key} not found: {vp}")
            if os.path.getsize(vp) == 0:
                raise JobValidationError(f"{key} is empty: {vp}")
            resolved[key] = vp
    return resolved


def _build_config(base: KineticStudioConfig, job: Dict[str, Any]) -> KineticStudioConfig:
    """Apply per-item overrides onto a copy of the base config."""
    cfg = KineticStudioConfig.from_dict(base.to_dict())  # deep copy via round-trip
    if job.get("brand"):
        cfg.brand.name = job["brand"]
    if job.get("preset"):
        if job["preset"] not in preset_lib.PRESETS:
            raise JobValidationError(f"unknown preset: {job['preset']}")
        cfg.motion.name = job["preset"]
    if job.get("preview"):
        cfg.preview = True
    if job.get("fps"):
        cfg.output.fps = int(job["fps"])
    if job.get("markers"):
        cfg.ramp.markers = [float(x) for x in job["markers"]]
    if job.get("setup_speed"):
        cfg.ramp.setup_speed = float(job["setup_speed"])
    if job.get("peak_speed"):
        cfg.ramp.peak_speed = float(job["peak_speed"])
    return cfg


def _run_one(base_cfg_dict: Dict[str, Any], job: Dict[str, Any], out_root: str,
             max_retries: int, retry_base: float) -> Dict[str, Any]:
    """Run a single job (with retry/backoff). Designed to be picklable for ProcessPool.

    Returns a structured status record. Never raises for a failed job — failures are
    captured into the record so the batch continues.
    """
    base = KineticStudioConfig.from_dict(base_cfg_dict)
    name = job.get("out_name") or (os.path.splitext(os.path.basename(job["clip"]))[0] + "_short.mp4")
    record = {"clip": job["clip"], "out_name": name, "attempts": 0, "ok": False,
              "error": None, "output": None}
    try:
        resolved = validate_job(job)
    except JobValidationError as e:
        record["error"] = f"validation: {e}"
        return record

    workdir = os.path.join(out_root, os.path.splitext(name)[0] + ".work")
    os.makedirs(workdir, exist_ok=True)
    last_err = None
    for attempt in range(1, max_retries + 1):
        record["attempts"] = attempt
        try:
            cfg = _build_config(base, job)
            ks = KineticStudio(cfg, workdir=workdir)
            res = ks.run(resolved["clip"],
                         music=resolved.get("music"),
                         voiceover=resolved.get("voiceover"),
                         out_name=name)
            out_path = os.path.join(out_root, name)
            if res.ok and res.final_video and os.path.exists(res.final_video):
                # move final short into the batch root (clobber-free collision handled by caller)
                import shutil
                # atomic-ish move; if destination exists from a prior run, keep unique
                shutil.copy2(res.final_video, out_path)
                record["ok"] = True
                record["output"] = out_path
                return record
            last_err = "run reported not ok"
        except Exception as e:  # noqa: BLE001 - capture, don't abort batch
            last_err = f"{type(e).__name__}: {e}"
        if attempt < max_retries:
            time.sleep(retry_base * (2 ** (attempt - 1)))  # bounded exponential backoff
    record["error"] = last_err or "failed"
    return record


def run_batch(manifest: List[Dict[str, Any]], base_config: KineticStudioConfig,
              out_root: str, workers: int = 1, max_retries: int = 1,
              retry_base: float = 0.5,
              on_progress: Optional[Callable[[BatchProgress], None]] = None,
              root: str = "") -> BatchProgress:
    """Fan out a manifest to parallel, retryable, validated runs.

    - validates every job up front (early reject)
    - runs jobs in a process pool (workers)
    - clobber-free: if two jobs target the same out_name, they share a unique suffix
    - emits structured BatchProgress via on_progress after each completion
    """
    os.makedirs(out_root, exist_ok=True)
    base_dict = base_config.to_dict()
    progress = BatchProgress(total=len(manifest))
    progress.items = [{**j, "status": "pending"} for j in manifest]

    # pre-validate + resolve; mark invalid items as failed up front (early reject)
    resolved_jobs = []
    for j in manifest:
        try:
            validate_job(j, root=root)
            resolved_jobs.append(j)
        except JobValidationError as e:
            progress.failed += 1
            progress.completed += 1
            progress.items.append({"clip": j.get("clip"), "status": "failed",
                                   "error": f"validation: {e}"})

    # clobber-free out_name disambiguation
    seen: Dict[str, int] = {}
    jobs_to_run = []
    for j in resolved_jobs:
        name = j.get("out_name") or (os.path.splitext(os.path.basename(j["clip"]))[0] + "_short.mp4")
        if name in seen:
            seen[name] += 1
            base, ext = os.path.splitext(name)
            name = f"{base}.{seen[name]}{ext}"
        else:
            seen[name] = 0
        job = dict(j); job["out_name"] = name
        jobs_to_run.append(job)

    def _emit():
        if on_progress:
            on_progress(progress)

    if workers <= 1 or len(jobs_to_run) <= 1:
        for job in jobs_to_run:
            progress.in_progress = [job["clip"]]
            rec = _run_one(base_dict, job, out_root, max_retries, retry_base)
            _ingest(rec, progress)
            progress.in_progress = []
            _emit()
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_run_one, base_dict, job, out_root, max_retries, retry_base): job
                    for job in jobs_to_run}
            for fut in as_completed(futs):
                progress.in_progress = [futs[fut]["clip"]]
                rec = fut.result()
                _ingest(rec, progress)
                progress.in_progress = []
                _emit()

    _emit()
    return progress


def _ingest(rec: Dict[str, Any], progress: BatchProgress) -> None:
    progress.completed += 1
    if rec.get("ok"):
        progress.succeeded += 1
    else:
        progress.failed += 1
    progress.items.append({"clip": rec["clip"], "out_name": rec.get("out_name"),
                           "status": "ok" if rec.get("ok") else "failed",
                           "attempts": rec.get("attempts"),
                           "output": rec.get("output"), "error": rec.get("error")})
