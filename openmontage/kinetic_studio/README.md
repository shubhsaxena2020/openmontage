# Kinetic Studio — README (RUN ON LAPTOP)

> **Status:** The laptop repo `C:\Users\shubh\Projects\OpenMontage` is **unreachable from
> the VPS** (no mount/ssh/sync). This package was built and smoke-tested on the VPS
> (Linux/CPU) and is designed to **run on your Windows laptop** inside the real OpenMontage
> repo. Everything below is written for that environment.

## What Kinetic Studio does
Turns raw gym footage into a beat-synced vertical (9:16) short with pose tracking, dynamic
overlays, and kinetic captions — for FBC Arena's promo content pipeline.

```
gym.mp4
  → audio extract → beat/drop map (librosa)
  → motion-energy highlights
  → pose/reps (YOLOv8-pose)            [optional]
  → athlete bbox track
  → smart 9:16 reframe (anti-jitter)
  → kinetic tempo-ramp synced to drops (ffmpeg setpts)
  → word-level kinetic captions (faster-whisper)   [if voiceover supplied]
  → Remotion final composite: footage + HUD + captions
  → mux music back under the short
```

## Where these files go in the real OpenMontage repo
This folder (`kinetic_studio/`) drops into `OpenMontage/tools/studio/` (or `apps/kinetic-studio/`).
The `remotion/` folder's `StudioComposition.tsx` + `studio-entry.tsx` go into the repo's
Remotion app (e.g. `OpenMontage/remotion/src/`). The 6 engine tools already live under
`tools/analysis|video|audio|subtitle/`.

## Prereqs (laptop, one time)
1. **Python 3.11** + a venv:
   ```powershell
   cd C:\Users\shubh\Projects\OpenMontage
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r tools\studio\requirements.txt
   ```
   (torch: install the **CUDA** wheel from pytorch.org if you have an NVIDIA GPU — pose
   detection is much faster. CPU works but is slow.)
2. **ffmpeg** on PATH (https://ffmpeg.org/download.html, Windows build, add to PATH).
3. **Node 18+** + Remotion:
   ```powershell
   cd remotion
   npm install
   ```

## Run
```powershell
# from the OpenMontage root, with the venv active
set PYTHONPATH=tools
python -m kinetic_studio run "C:\footage\gym1.mp4" `
    --music "C:\music\drop_track.mp3" `
    --voiceover "C:\vo\coach.mp3" `
    --brand "FBC Arena" `
    --workdir studio_out --out kinetic_short.mp4
```
Or generate a starter config and edit it, then:
```powershell
python -m kinetic_studio init-config --out kinetic_studio_config.json
# edit kinetic_studio_config.json (brand, colors, speeds, caption style)
python -m kinetic_studio run "C:\footage\gym1.mp4" --config kinetic_studio_config.json
```
Then preview/burn the HUD in Remotion Studio (60fps on the laptop):
```powershell
cd remotion
npm run studio        # opens StudioComposition at 60fps with the live HUD
```

## What was verified on the VPS (honest)
- Full orchestrator chain runs end-to-end on synthetic footage and **produces a real
  `kinetic_short.mp4`** (738 KB) via the Remotion composite.
- All 6 engine tools unit/integration tested (pytest: 14 passed).
- Remotion `tsc --noEmit` + `remotion bundle` + headless render all exit 0.

## What you must verify on the laptop (VPS couldn't)
- **Real gym footage** with a person → `fitness_pose` actually detects keypoints (the VPS
  only had a synthetic box, so pose math was unit-tested but not run on a human).
- **Beat-sync quality** on real music (BPM accuracy was verified at 117.45 vs 120 truth).
- **Remotion Studio 60fps live preview** (headless render passed; interactive preview
  needs your display/GPU).
- **GPU pose speed** (VPS ran CPU; laptop with CUDA will be far faster).
- **Windows path handling** — code uses `pathlib` throughout and auto-discovers ffmpeg, so
  it should work, but confirm on first run.

## Known graceful-degrade behavior
- No audio in source → skips beat-sync, does a uniform tempo-ramp.
- No voiceover → skips kinetic captions (HUD + reframe still produced).
- Pose model missing/fails → falls back to motion-centroid bbox tracking.
- Remotion unavailable → studio ships the pre-HUD ramped clip instead of failing.
