# OpenMontage

Self-contained toolkit that converts raw workout / gym footage into **high-energy, beat-synced
vertical (9:16) shorts** with pose tracking, dynamic overlays, and kinetic captions — built to
feed **FBC Arena's** continuous stream of promotional content.

## Two layers

1. **Engine** — six composable `BaseTool` tools under `tools/` (analysis / video / audio /
   subtitle). Each does one CV/audio job and emits a JSON artifact + a media file. Verified on
   CPU; GPU (CUDA) accelerates pose detection.
2. **Kinetic Studio** (`kinetic_studio/`) — the config-driven *product* on top of the engine.
   `python -m kinetic_studio run INPUT.mp4` chains the tools, writes `studio_input.json`, and
   (on a machine with a browser) burns the HUD in via the Remotion app in `remotion/`.

## Quick start (laptop — Windows)

```powershell
cd C:\Users\shubh\Projects\OpenMontage
# one-shot: ffmpeg + venv + pip + npm install
powershell -ExecutionPolicy Bypass -File setup_windows.ps1

.venv\Scripts\activate
set PYTHONPATH=.
python -m kinetic_studio run "C:\footage\gym1.mp4" `
    --music "C:\music\drop_track.mp3" --voiceover "C:\vo\coach.mp3" `
    --brand "FBC Arena" --workdir studio_out --out kinetic_short.mp4

# burn the HUD (needs Node + browser)
cd remotion
npm run studio           # live preview of StudioComposition (open in browser)
# headless render (what the Python orchestrator runs for you):
npm run render-studio    # -> out/studio_short.mp4
```

Full details: [`kinetic_studio/README.md`](kinetic_studio/README.md). Design notes:
[`kinetic_studio/DESIGN.md`](kinetic_studio/DESIGN.md).

## What it does, step by step

| Stage | Tool / component | Output |
|-------|------------------|--------|
| Beat / drop map | `beat_drop_mapper` (librosa) | `beats.json` (BPM, drops) |
| Motion-energy highlights | `motion_energy` | `energy.json` |
| Pose / reps | `fitness_pose` (YOLOv8-pose) | `pose.json` |
| Athlete track | `kinetic_studio/box_tracker.py` | `boxes.json` |
| 9:16 reframe (anti-jitter) | `smart_reframe` (H.264) | `reframed.mp4` |
| Tempo-ramp synced to drops | `kinetic_ramper` (ffmpeg setpts) | `ramped.mp4` |
| Kinetic captions | `kinetic_word_sync` (faster-whisper) | `captions.json` |
| Audio duck under VO | `audio_master_duck` | `ducked.wav` |
| **HUD composite** | `remotion/StudioComposition.tsx` | **final short** |
| Music mux | ffmpeg | `final_with_music.mp4` |

## Engine pipeline (no browser needed)

For a headless run with no browser, `pipeline_defs/build_fitness_short.json` composes the
engine tools end-to-end and produces every media artifact the HUD consumes. Run it with:

```powershell
.venv\Scripts\activate
python -m pytest tests\test_build_fitness_short.py -v   # end-to-end integration test
```

## Graceful degradation

The studio never hard-fails:
- No audio → no beat-sync, uniform ramp.
- No voiceover → no captions (HUD + reframe still produced).
- Pose fails → motion-centroid tracker.
- **No browser (e.g. headless VPS) → ships the pre-HUD ramped clip + music**; the HUD burn-in
  is the final laptop step.

## Verification status

- Python engine + orchestrator: full pytest suite passes (36 tests) on synthetic media.
- Remotion composite: `tsc --noEmit` clean; the **headless browser render only runs where a
  browser + system libs exist (the laptop)**. On a headless VPS the studio degrades as above.
- Real-gym-footage pose detection, real-music beat-sync, and 60fps live preview must be
  confirmed on the laptop.
