"""Render-time benchmark for the Kinetic Studio pipeline (Phase E.18).

Measures wall-clock render time of the kinetic ramper (the heaviest ffmpeg step) on the
committed sample asset across N runs and reports p50/p90/max. This is a real benchmark
(actual ffmpeg renders), not a synthetic estimate.

The ramper is chosen as the representative heavy step because it dominates per-clip render
cost (setpts trim+concat per segment). A full-studio benchmark is available via
`python -m kinetic_studio run --dry-run` for the plan, but the timed path here exercises
the real render.

Usage:
  python -m scripts.benchmark_render [--runs N] [--out PATH]

Defaults: runs=5, out=docs/benchmark-render.json (relative to repo root).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "openmontage"))

from tools import make_tool  # noqa: E402


def _sample() -> Path:
    # Reuse the committed synthetic sample that verify.py uses.
    p = _ROOT / "openmontage" / "samples" / "samples" / "athlete_16x9.mp4"
    if not p.exists():
        raise SystemExit(f"sample asset missing: {p}")
    return p


def bench_ramper(sample: Path, runs: int, work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    beats = _ROOT / "openmontage" / "samples" / "samples" / "beats.json"
    if not beats.exists():
        # derive a beat map first so the ramper has anchors
        r = make_tool("beat_drop_mapper",
                      audio_path=str(_ROOT / "openmontage" / "samples" / "samples" / "beat_120bpm.wav"),
                      out_json=str(beats))
        if not r.ok:
            raise SystemExit(f"beat mapping failed: {r.error}")
    times: list[float] = []
    errors = 0
    for i in range(runs):
        out = work / f"bench_ramped_{i}.mp4"
        t0 = time.perf_counter()
        r = make_tool("kinetic_ramper", input_path=str(sample), out_path=str(out),
                      map_json=str(beats), setup_speed=1.6, peak_speed=0.4)
        dt = time.perf_counter() - t0
        if not r.ok:
            errors += 1
            print(f"  run {i}: ERROR {r.error}")
            continue
        times.append(dt)
        print(f"  run {i}: {dt:.2f}s  segs={r.metrics.get('segments')}")
    if not times:
        raise SystemExit("all benchmark runs failed")
    times.sort()
    return {
        "step": "kinetic_ramper",
        "sample": str(sample.relative_to(_ROOT)),
        "runs": runs,
        "successful_runs": len(times),
        "errors": errors,
        "p50_sec": round(statistics.median(times), 3),
        "p90_sec": round(times[min(len(times) - 1, int(0.9 * (len(times) - 1)))], 3),
        "min_sec": round(min(times), 3),
        "max_sec": round(max(times), 3),
        "mean_sec": round(statistics.mean(times), 3),
        "host": "CPU-only (.venv-om); no GPU assumed",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kinetic Studio render benchmark")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out", default=str(_ROOT / "docs" / "benchmark-render.json"))
    ap.add_argument("--workdir", default=str(_ROOT / "docs" / "bench_out"))
    args = ap.parse_args(argv)

    sample = _sample()
    print(f"Benchmarking {args.runs} runs of kinetic_ramper on {sample.name} ...")
    result = bench_ramper(sample, args.runs, Path(args.workdir))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    print(f"  p50={result['p50_sec']}s  p90={result['p90_sec']}s  "
          f"max={result['max_sec']}s  (mean={result['mean_sec']}s)")
    return result


if __name__ == "__main__":
    main()
