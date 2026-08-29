# Changelog

## 1.1.0 — Kinetic Studio roadmap batch
- **Motion presets** (`kinetic_studio/presets.py`): cinematic / energetic / freeze / subtle,
  each with a testable curve shape and a pure `build_motion_plan()`.
- **Audio-sync anchors**: the kinetic ramper now anchors slow-mo to beats + explicit markers
  + voice peaks, with snap-to-grid merging (no drift on slightly off-grid audio).
- **Preview / proxy mode**: `cfg.preview=True` runs a fast 360p draft and skips the Remotion
  HUD composite.
- **Batch pipeline** (`kinetic_studio/batch.py`): manifest fan-out, per-item reporting,
  retry w/ bounded backoff, early-reject validation, parallel worker pool (clobber-free),
  and structured `BatchProgress`.
- **FPS regression test**: proves the renderer is driven by the configured fps (not a baked 30).
- **Bug fixes**:
  - kinetic_ramper: real slow-mo was being lost (segment containment bug) — now correct, with
    overlapping-window merge + frame-grid snapping for render-accurate timing.
  - smart_reframe: forced even output dimensions (libx264 rejects odd heights).
  - audio_master_duck: voice envelope aligned to music timeline (fixed IndexError on
    differing-length tracks).

## 1.0.0 — OpenMontage Kinetic Studio
- End-to-end beat-synced vertical short pipeline: pose → motion-energy → smart-reframe →
  kinetic-ramper → kinetic-captions → audio-master-duck, plus the Remotion HUD composite.
