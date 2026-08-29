# Kinetic Studio — DESIGN

## Goal
Automated, config-driven pipeline that converts raw workout/gym footage into high-energy,
beat-synced vertical (9:16) shorts with pose tracking, dynamic overlays, and kinetic
captions — supporting FBC Arena's need for a continuous stream of promotional content.

## Architecture (3 layers)

```
┌──────────────────────────────────────────────────────────────┐
│  CLI  (kinetic_studio/cli.py)  — `python -m kinetic_studio`   │
│     run / init-config                                          │
├──────────────────────────────────────────────────────────────┤
│  Orchestrator (orchestrator.py) — KineticStudio.run()          │
│     chains tools, writes studio_input.json, drives Remotion    │
├──────────────────────────────────────────────────────────────┤
│  Engine = the 6 OpenMontage BaseTool tools (tools/)            │
│     fitness_pose · motion_energy · smart_reframe               │
│     beat_drop_mapper · kinetic_ramper · kinetic_word_sync      │
│  + box_tracker.py (pose-or-centroid athlete bbox)              │
├──────────────────────────────────────────────────────────────┤
│  Remotion final composite (remotion/src/StudioComposition.tsx) │
│     <Video bg> + RepCounter + ExerciseNameCard + BrandWatermark│
│     + KineticCaptions (word highlight synced to speech)         │
└──────────────────────────────────────────────────────────────┘
```

## Data flow
1. **Audio** — if no `--music`/`--voiceover`, extract from the video (ffmpeg). Silent
   footage degrades to uniform ramp (no beat-sync).
2. **beat_drop_mapper** → `beats.json` (BPM, downbeats, drops).
3. **motion_energy** → `energy.json` (highlight moments).
4. **fitness_pose** → `pose.json` (reps/angles) — optional; on failure, skipped.
5. **box_tracker** → `boxes.json` (athlete bbox; from pose if detected, else motion
   centroid). Feeds reframe.
6. **smart_reframe** → `reframed.mp4` (9:16, centered, anti-jitter).
7. **kinetic_ramper** → `ramped.mp4` (setpts speed-up on setup, slow-mo on drops, synced
   to `beats.json`). No beats → uniform ramp (graceful).
8. **kinetic_word_sync** → `captions.json` (only if `--voiceover`).
9. **Remotion StudioComposition** → final short. The bg video is transcoded to **H.264**
   first (OpenCV's mp4v codec is undecodable by Remotion's Chromium). `studio_input.json`
   carries brand + caption schedule; `durationInFrames` is probed from the real footage so
   Remotion doesn't error on out-of-range frames.
10. **mux** music back under the short (ffmpeg).

## Configuration
All knobs live in `config.py` (`KineticStudioConfig`): brand (name/accent/watermark),
output (1080x1920/30fps), reframe (target_w/alpha/deadband), ramp (speeds/drop thr),
caption (model/lang/style), pose (model/device). Serializable to JSON/YAML.

## Portability (VPS Linux ↔ laptop Windows)
- `pathlib.Path` everywhere; no hardcoded Unix paths.
- ffmpeg auto-discovery: `FFMPEG_BIN` env → PATH → imageio-ffmpeg fallback.
- torch device: `"auto"` → CUDA if available else CPU.
- Remotion is OS-agnostic; `npm run studio` gives the 60fps laptop preview.

## Resilience
Every step is recorded (ok/detail/artifact) but a failure does not abort the run. The
studio degrades: no audio → no beat-sync; no voiceover → no captions; pose fail → motion
tracker; Remotion fail → ship pre-HUD ramped clip. Result: `StudioRunResult.ok` reflects
whether a final short file exists.

## Why this shape
The 6 engine tools were built earlier this session (PHASE A–C) as a self-contained
OpenMontage-style toolkit. Kinetic Studio is the **product layer** on top — it does no
low-level CV/audio itself; it composes the tools and adds the business logic (branding,
beat-sync tempo, caption scheduling, final composite). This keeps the engine reusable and
the studio easy to retarget (different brand, different output spec) via config alone.
