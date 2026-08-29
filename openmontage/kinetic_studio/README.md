# Kinetic Studio — README (RUN ON LAPTOP)

> **Important environment note:** This package was built and smoke-tested on a **headless
> Linux VPS**, but the **final Remotion HUD composite can only run on your laptop** (Windows,
> with a real browser + Node). Everything below is written for that environment
> (`C:\Users\shubh\Projects\OpenMontage`). The Python engine (everything except the HUD
> burn-in) runs fine on either, and **degrades gracefully** on the VPS (see "What the VPS
> actually proved" below).

## What Kinetic Studio does
Turns raw gym footage into a beat-synced vertical (9:16) short with pose tracking, dynamic
overlays, and kinetic captions — for **FBC Arena's** promo-content pipeline.

```
gym.mp4
  → audio extract → beat/drop map (librosa)
  → motion-energy highlights
  → pose/reps (YOLOv8-pose)            [optional]
  → athlete bbox track
  → smart 9:16 reframe (anti-jitter)
  → kinetic tempo-ramp synced to drops (ffmpeg setpts)
  → word-level kinetic captions (faster-whisper)   [if voiceover supplied]
  → Remotion final composite: footage + HUD + captions   [LAPTOP ONLY]
  → mux music back under the short
```

## Repo layout (this repo)
```
OpenMontage/                      (repo root)
  kinetic_studio/                 ← this package (CLI + orchestrator + config)
    cli.py  config.py  orchestrator.py  box_tracker.py
    requirements.txt  README.md  DESIGN.md
  remotion/                       ← Remotion app (HUD composite)
    src/StudioComposition.tsx  src/RepCounter.tsx  src/ExerciseNameCard.tsx
    src/BrandWatermark.tsx  src/KineticCaptions.tsx
    src/studio-entry.tsx  src/studio_input.json
    package.json  tsconfig.json
  tools/                          ← the 6 engine BaseTool tools
    analysis/fitness_pose.py  analysis/motion_energy.py
    video/smart_reframe.py  audio/beat_drop_mapper.py
    audio/audio_master_duck.py  subtitle/kinetic_word_sync.py
  samples/                        ← sample footage (athlete_16x9.mp4, beat_120bpm.wav, speech.wav)
  pipeline_defs/                  ← declarative engine pipelines (incl. build_fitness_short.json)
```

## Prereqs (laptop, one time)
1. **Python 3.11** + a venv:
   ```powershell
   cd C:\Users\shubh\Projects\OpenMontage
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r kinetic_studio\requirements.txt
   ```
   (torch: install the **CUDA** wheel from pytorch.org if you have an NVIDIA GPU — pose
   detection is much faster. CPU works but is slow.)
2. **ffmpeg** on PATH (https://ffmpeg.org/download.html, Windows build, add to PATH).
3. **Node 18+** (with npm) for Remotion:
   ```powershell
   cd C:\Users\shubh\Projects\OpenMontage\remotion
   npm install
   ```

> Or run the one-shot helper: `powershell -ExecutionPolicy Bypass -File setup_windows.ps1`
> (installs ffmpeg via winget, creates the venv, pip-installs, and runs `npm install`).

## Run
```powershell
# from the OpenMontage root, with the venv active
cd C:\Users\shubh\Projects\OpenMontage
.venv\Scripts\activate
set PYTHONPATH=.
python -m kinetic_studio run "C:\footage\gym1.mp4" `
    --music "C:\music\drop_track.mp3" `
    --voiceover "C:\vo\coach.mp3" `
    --brand "FBC Arena" `
    --workdir studio_out --out kinetic_short.mp4
```
Or generate a starter config and edit it, then run:
```powershell
python -m kinetic_studio init-config --out kinetic_studio_config.json
# edit kinetic_studio_config.json (brand, colors, speeds, caption style)
python -m kinetic_studio run "C:\footage\gym1.mp4" --config kinetic_studio_config.json
```

Then on the **laptop**, burn the HUD into the short:
```powershell
cd C:\Users\shubh\Projects\OpenMontage\remotion
npm run studio           # live preview of StudioComposition (open in browser)
# headless render (what the Python orchestrator also runs for you):
npm run render-studio    # -> out\studio_short.mp4
```
The orchestrator writes `remotion/src/studio_input.json` (brand, caption schedule, resolved
duration) and drives the headless render automatically. If Remotion/browser is unavailable it
degrades to the pre-HUD ramped clip (see below).

## What the VPS actually proved (honest)
- The **full engine chain** runs end-to-end on synthetic footage: audio → beat/drop map →
  motion-energy → pose → athlete bbox → 9:16 reframe (**real H.264**, not mp4v) → kinetic
  tempo-ramp → kinetic captions → audio duck + mux.
- The orchestrator **gracefully degrades**: on the VPS the Remotion headless browser cannot
  launch (missing `libnspr4.so`, no system Chrome), so it ships the pre-HUD ramped clip
  (`ramped.mp4`) with music muxed (`final_with_music.mp4`) instead of failing. Verified:
  `final_with_music.mp4` (~79 KB) is produced by `python -m kinetic_studio run ...` on the VPS.
- `tsc --noEmit` on the Remotion app passes (TypeScript types are sound).

## What ONLY the laptop can do (VPS could NOT)
- **The Remotion HUD composite** — headless Chromium render needs a browser + system libs
  (`libnspr4`) absent on the VPS. On the laptop, `npm run studio` (live 60fps) and headless
  `remotion render` produce the final short WITH the HUD (RepCounter, ExerciseNameCard,
  BrandWatermark) and kinetic captions burned in.
- **Real gym footage** with a person → `fitness_pose` actually detects keypoints (the VPS
  only had a synthetic box, so pose math was unit-tested but not run on a human).
- **Beat-sync quality** on real music (BPM accuracy was verified at 117.45 vs 120 truth).
- **GPU pose speed** (VPS ran CPU; laptop with CUDA will be far faster).
- **Windows path handling** — code uses `pathlib` throughout and auto-discovers ffmpeg, so
  it should work, but confirm on first run.

## Known graceful-degrade behavior
- No audio in source → skips beat-sync, does a uniform tempo-ramp.
- No voiceover → skips kinetic captions (HUD + reframe still produced).
- Pose model missing/fails → falls back to motion-centroid bbox tracking.
- Remotion unavailable (e.g. VPS) → studio ships the pre-HUD ramped clip + music instead of
  failing. The HUD burn-in is always the final laptop step.
