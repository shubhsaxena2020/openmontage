# RENDER.md — Remotion HUD render verification (PHASE C.6)

Run on this host (CPU-only sandbox; Remotion bundles its own headless Chromium "Headless
Shell", which downloaded successfully during the first render attempt).

## Commands
```
cd openmontage/remotion
npm install                 # 255 packages (remotion 4.0.518, react 18.3.1)
./node_modules/.bin/remotion render src/index.tsx FitnessHUD out/hud_test.mp4 --frames=0-60
./node_modules/.bin/remotion render src/captions-entry.tsx KineticCaptionsReal out/captions_test.mp4 --frames=0-120
```

## Results (real execution)
| Composition | Entry | Output | Frames | Result |
|---|---|---|---|---|
| FitnessHUD (RepCounter + ExerciseNameCard + BrandWatermark) | src/index.tsx | out/hud_test.mp4 (188 KB) | 61/61 rendered, 61/61 encoded | exit 0 |
| KineticCaptionsReal (word-highlight layer fed REAL captions.json from kinetic_word_sync) | src/captions-entry.tsx | out/captions_test.mp4 (264 KB) | 121/121 rendered, 121/121 encoded | exit 0 |

Both renders completed with exit code 0 and produced valid MP4 containers (Remotion's
encoder only writes a valid file on success; its log reports the exact frame counts).

## What this proves
- The three HUD components (RepCounter, ExerciseNameCard, BrandWatermark) and the
  KineticCaptions word-highlight layer **compile (TypeScript), bundle, and render** via
  headless Chromium without errors.
- The KineticCaptions layer **binds end-to-end** to the Python `kinetic_word_sync` output:
  the real `captions.json` (faster-whisper word timestamps on real speech audio) drives the
  per-frame active-word highlight.

## Honest limitations
- The interactive `remotion studio` **60fps preview** (a browser/GPU live-preview session)
  was NOT run — this is a headless server sandbox. The compositions are authored at 30fps
  and the headless encode succeeded; "60fps clean preview" is the configured `fps`/playback
  property and was not exercised interactively. To view: `npm run dev` on a machine with a
  display.
- Rendered output is a transparent-background HUD (bg:"transparent"); compositing over the
  athlete footage is the downstream step (e.g., kinetic_ramper / smart_reframe output).
- `captions.json` used here came from generic TTS speech (jo.wav), not a fitness coach; the
  code path is identical for real coaching audio.
