# OpenMontage Kinetic Studio — Architecture

How the Kinetic Studio product turns raw gym footage into a beat-synced vertical (9:16)
short. This document describes the **current** code (v1.3), not a plan.

## High-level pipeline

```
input.mp4
  │
  ├─ extract audio (ffmpeg)                     [if no separate music/voiceover]
  ▼
beat_drop_mapper(audio)        → beats.json     (BPM + drop/peak timestamps)
motion_energy(video)           → energy.json    (highlight moments)
fitness_pose(video)            → pose.json       (reps/angles; optional, needs YOLOv8)
box_tracker(pose|motion)       → boxes.json      (athlete bbox for reframe)
smart_reframe(video, boxes)    → reframed.mp4    (9:16, centered, anti-jitter)
kinetic_word_sync(voiceover)   → captions.json   (if voiceover + captions enabled)
kinetic_ramper(reframed, beats)→ ramped.mp4      (tempo-synced to drops)
Remotion StudioComposition(ramped + HUD + captions) → final short.mp4
mux music back under the short (ffmpeg)          [if separate music provided]
```

Every step is resilient: a failure is recorded but does **not** abort the whole run — the
studio degrades gracefully (e.g. no captions if no speech, no pose if the model is missing).

Source of truth: `openmontage/kinetic_studio/orchestrator.py` (`KineticStudio.run`).

## Layer map

| Layer | Location | Responsibility |
|-------|----------|----------------|
| CLI | `kinetic_studio/cli.py` | argparse entry; `run`, `presets`, `init-config` subcommands |
| Orchestrator | `kinetic_studio/orchestrator.py` | chains the toolkit; `run()` + `dry_run()` |
| Config | `kinetic_studio/config.py` | `KineticStudioConfig` dataclass (JSON/YAML load+save) |
| Presets | `kinetic_studio/presets.py` | named motion "looks" (ramp/zoom/transition) + pure planner |
| Batch | `kinetic_studio/batch.py` | manifest fan-out, retry, parallel workers |
| Engine (analysis) | `tools/analysis/` | `fitness_pose`, `motion_energy` |
| Engine (video) | `tools/video/` | `smart_reframe`, `kinetic_ramper` |
| Engine (audio) | `tools/audio/` | `beat_drop_mapper`, `audio_master_duck` |
| Engine (subtitle) | `tools/subtitle/` | `kinetic_word_sync` |
| HUD | `remotion/` | React/TS Remotion `StudioComposition` (HUD + captions over video) |

## The 7 engine tools (registry)

Registered via `tools/registry.py` (`make_tool(name, **params)`). All return a
`ToolResult(ok, data, artifacts, metrics)`.

1. **fitness_pose** (analysis) — YOLOv8-pose; angle geometry + rep counting on the
   detected skeleton. CPU-only; optional (needs the model weight).
2. **motion_energy** (analysis) — per-frame motion magnitude; peaks = highlight moments.
3. **smart_reframe** (video) — crops to a moving subject bbox, renders 9:16, EMA-smoothed
   with a px dead-band (anti-jitter). Forces even dimensions (libx264 constraint).
4. **kinetic_ramper** (video) — ffmpeg `setpts` time-remap; speeds up setup movement,
   slow-mo on peak lifts/drops, anchored to the beat-drop map (+ markers + voice peaks).
   Render-independent helpers (`_build_segments`, `merge_slow_windows`, `resolve_anchors`)
   are pure and unit-tested.
5. **beat_drop_mapper** (audio) — librosa BPM + relative-energy drop detection.
6. **audio_master_duck** (audio) — RMS envelope; ducks music under voice peaks.
7. **kinetic_word_sync** (subtitle) — faster-whisper → word-timed captions (kinetic style).

## Motion presets

`kinetic_studio/presets.py` is a pure data + pure planner library (no ffmpeg/Remotion
needed to prove the curve). Each preset describes the *shape* of the motion:

- `ramp`: `setup_speed` (>1 = faster on setup) / `peak_speed` (<1 = slow-mo on drops)
- `zoom`: Ken-Burns pulse/punch (amount + pivot)
- `transition`: intro/outro fade|wipe + duration

`build_motion_plan()` turns a preset + clip geometry into a concrete frame-accurate plan
(ramp segments, zoom keyframes, transition) that the ramper or renderer consumes.
Presets: `cinematic`, `energetic`, `freeze`, `subtle`, `mobile` (small-screen variant).

## Config

`KineticStudioConfig` is a single dataclass holding every knob (brand, output dims/fps,
reframe, ramp, caption, pose, motion preset, preview flag, workdir). Loaded from JSON or
YAML (PyYAML optional). The same config drives the headless VPS smoke-test and the laptop
production run, keeping the two environments identical.

## Preview / dry-run modes

- **Preview** (`cfg.preview=True`): renders a 360p proxy and skips the Remotion HUD
  composite — fast draft for iteration.
- **Dry-run** (`studio.run --dry-run`): `KineticStudio.dry_run()` probes the clip and
  returns the edit plan (audio strategy, preset motion plan, anchors, and the list of
  heavy steps `run()` would perform) **without any ffmpeg render**. No output file is
  produced.

## Remotion HUD

The final composite is a React/TS Remotion `StudioComposition`
(`remotion/src/studio-entry.tsx`) that overlays the HUD (brand badge, exercise name card,
rep counter, kinetic captions) on the ramped video. It is rendered headless via
`remotion render` when a browser/Node toolchain is present; otherwise the studio falls back
to the ramped `.mp4` as the final output. The composition's fps/dims come from config
(regression-tested so a hard-coded 30 is never baked in).

## Build & verify

- `openmontage/verify.py` — cold no-op health re-check (tool registry + a few smoke
  computations) against the `.venv-om` virtualenv.
- `openmontage/tests/` — pytest suite covering all 7 engine tools (pure + real-fixture),
  the product layer (presets, batch, audio-sync anchors, fps regression, studio e2e), and
  the Remotion HUD type-check. See `openmontage/tests/COVERAGE_MAP.md` for the per-module
  coverage breakdown.

## Directory layout

```
openmontage/
  tools/            engine (analysis/video/audio/subtitle)
  kinetic_studio/   cli, orchestrator, config, presets, batch, box_tracker
  remotion/         React/TS HUD composition
  tests/            pytest suite + COVERAGE_MAP.md
  verify.py         cold health re-check
  CHANGELOG.md
docs/
  ARCHITECTURE.md   (this file)
  web-terminal-dashboard/   browser-terminal UX audit (SMALL-SCREEN.md, UX-AUDIT-REPORT.md,
                            ux-audit-findings.json)
```
