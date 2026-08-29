# Changelog

## 1.3.0 — Phase B/C feature + test program
- **Presets CLI** (`kinetic_studio presets`): list all motion presets with their full
  parameter schema (text or `--json`); new pure helpers `preset_schema()` /
  `list_presets_with_schema()`.
- **Small-screen (mobile) preset**: `mobile` — gentle ramp + soft zoom pulse for narrow
  phone viewports; referenced by `docs/web-terminal-dashboard/SMALL-SCREEN.md`. Selectable
  via `--preset mobile` or config.
- **`--dry-run` edit-plan mode**: `KineticStudio.dry_run()` returns the full edit plan
  (clip probe, audio strategy, preset motion plan, anchors, and the heavy steps `run()`
  would perform) **without rendering**. Wired as `run --dry-run [--preset X]`.
- **UX-AUDIT JSON export** (`scripts/export_ux_audit.py`): parses the browser-terminal
  `UX-AUDIT-REPORT.md` into structured `docs/web-terminal-dashboard/ux-audit-findings.json`
  (tldr / tasks w/ decisions / changes / sources) for tracking/diffing.
- **Test & coverage** (Phase B): `tests/COVERAGE_MAP.md` documents per-module coverage for
  all 7 engine tools + product layer + HUD; `tests/test_ramper_edgecases.py` adds 10 fast,
  no-ffmpeg unit tests for the ramper's render-independent helpers (empty→uniform segment,
  segment merge, end-clamp, zero-length skip, overshoot, anchor snap/dedupe). Full suite
  baseline: 69 passed.

## 1.2.0 — Repo hygiene
- Deleted 6 stale merged `feat/*` branches; flipped GitHub default branch to `master`.
- Promoted `SMALL-SCREEN.md` + `UX-AUDIT-REPORT.md` into `docs/web-terminal-dashboard/`.
- Fixed `verify.py` stale tool-count assertion (5→7) so the cold health check is honest again.

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
