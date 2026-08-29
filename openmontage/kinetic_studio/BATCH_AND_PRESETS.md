# Kinetic Studio — Presets & Batch Processing

## Motion presets

Selectable via `cfg.motion.name` or the batch manifest `"preset"` field. Each preset
describes the *shape* of the motion: ramping speeds, a Ken-Burns zoom pulse, and an intro
transition. Presets are pure data — see `kinetic_studio/presets.py`.

| preset      | feel                                   | setup speed | slow-mo (peak) | zoom        |
|-------------|----------------------------------------|-------------|----------------|-------------|
| `cinematic` | smooth, gentle promo                   | 1.25        | 0.60           | soft pulse  |
| `energetic` | aggressive, high-energy gym reel       | 1.80        | 0.35           | punch       |
| `freeze`    | near-full freeze on every drop         | 1.50        | 0.12           | soft pulse  |
| `subtle`    | minimal ramping, mostly realtime       | 1.10        | 0.85           | none        |

List available presets programmatically:

```python
from kinetic_studio import presets as P
print(P.list_presets())                 # ['cinematic', 'energetic', 'freeze', 'subtle']
plan = P.build_motion_plan("energetic", fps=30, n_frames=180)
```

## Audio-sync anchors

The kinetic ramper anchors motion to **beats** (from `beat_drop_mapper`), **markers**
(explicit `cfg.ramp.markers` timestamps), and **voice peaks** (caption word onsets).
Anchors are snap-to-frame-grid merged (tolerance `cfg.ramp.snap_tolerance`, default 0.05s)
so slightly off-grid audio stays locked and never drifts.

## Preview / proxy mode

`cfg.preview = True` runs a fast draft: output drops to a 360p proxy, the Remotion HUD
composite is skipped, and the ramped (low-res) video is returned as the final. Great for
quick iteration before a full render.

## Batch processing

Fan a manifest of clips out to parallel, retryable, validated runs. Module:
`kinetic_studio/batch.py`.

### Manifest (JSON list)

```json
[
  {"clip": "clips/gym1.mp4", "music": "tracks/hype.mp3",
   "voiceover": "vo/gym1.mp3", "brand": "FBC Arena", "preset": "energetic"},
  {"clip": "clips/gym2.mp4", "preset": "cinematic", "out_name": "gym2_short.mp4"},
  {"clip": "clips/gym3.mp4", "preview": true}
]
```

Per-item overrides: `clip`, `music`, `voiceover`, `brand`, `preset`, `preview`, `fps`,
`markers`, `setup_speed`, `peak_speed`, `out_name`.

### Run

```python
from kinetic_studio.config import KineticStudioConfig
from kinetic_studio.batch import load_manifest, run_batch

manifest = load_manifest("manifest.json")
progress = run_batch(manifest, KineticStudioConfig(), out_root="batch_out",
                    workers=4, max_retries=2,
                    on_progress=lambda p: print(p.to_dict()))
print(f"{progress.succeeded}/{progress.total} succeeded")
```

### Guarantees

- **Early reject** — a job with a missing/empty/unsupported clip (or missing audio) is
  failed up front without spending GPU/CPU on it.
- **Retry w/ backoff** — failed jobs are retried up to `max_retries` with bounded
  exponential backoff; the per-item record reports how many attempts were made.
- **Clobber-free** — two jobs targeting the same `out_name` get unique suffixes.
- **Structured progress** — `BatchProgress.to_dict()` yields a machine-readable snapshot
  (total / completed / succeeded / failed / per-item status) suitable for a dashboard or
  CI log.
- **Parallel** — `workers > 1` uses a process pool so CPU-bound reframe/ramper work runs
  concurrently.
