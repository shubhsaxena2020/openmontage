# OpenMontage Kinetic Studio — Test coverage map

Generated 2026-08-29 during the Phase B coverage inventory. Scope: the 7 engine tools
plus the Kinetic Studio product layer (cli / orchestrator / config / presets / batch) and
the Remotion HUD.

## How to read this
- `covered` = at least one real test exercises the path (file::test in the suite).
- `gap` = no test found; a candidate for a new test.
- "real" = runs the tool on a fixture; "pure" = unit-tests the helper in isolation
  (no ffmpeg/video/whisper).

## Engine tools

### fitness_pose (analysis) — tools/analysis/fitness_pose.py
- angle geometry (pure): `test_fitness_pose.py::test_angle_straight`, `::test_angle_right`
- rep counting on synthetic signal (pure): `test_fitness_pose.py::test_count_reps_squat_signal`, `::test_count_reps_flat_signal_zero`
- runs on synthetic clip no-crash (real): `test_fitness_pose.py::test_run_no_detection_ok`
- angle/reps math (pure): `test_phase_a_b_tools.py::test_angle_geometry`, `::test_count_reps_squat_signal`, `::test_count_reps_flat_is_zero`
- runs on real clip (real): `test_phase_a_b_tools.py::test_pose_runs_on_real_clip_no_crash`
- **gap**: true keypoint accuracy on a HUMAN clip (no human asset on host — honest limit,
  documented in VERIFY.md; math is unit-tested, detection is not).

### motion_energy (analysis) — tools/analysis/motion_energy.py
- peaks on moving clip (real): `test_phase_a_b_tools.py::test_motion_energy_detects_peaks_on_moving_clip`
- peaks in pipeline (real): `test_pipeline.py::test_motion_energy_detects_peaks`
- **covered.** (Backlog B6 listed this as a gap; it is in fact covered.)

### smart_reframe (video) — tools/video/smart_reframe.py
- renders 9:16 + smooths (real): `test_phase_a_b_tools.py::test_smart_reframe_renders_9x16_and_smooths`
- renders + low jitter (real): `test_pipeline.py::test_smart_reframe_renders_and_low_jitter`
- **covered.** (Backlog B6 listed this as a gap; it is in fact covered.)

### kinetic_ramper (video) — tools/video/kinetic_ramper.py
- genuine speedup + slow-mo (real): `test_phaseB5_C.py::test_ramper_genuine_speedup_and_slowmo`
- smooth + synced with audio (real): `test_phaseB5_C.py::test_ramper_smooth_and_synced_with_audio`
- no-beats graceful degrade (real): `test_phaseB5_C.py::test_ramper_no_beats_degrades_gracefully`
- end-to-end markers+voice peaks (real): `test_audio_sync_anchors.py::test_ramper_uses_markers_and_voice_peaks_end_to_end`
- **added in this pass (pure, no ffmpeg):** `test_ramper_edgecases.py`
  - `_build_segments` with empty slow windows -> single uniform setup segment
  - `_build_segments` merges adjacent equal-speed segments
  - `merge_slow_windows` clamps to [0,end] and drops empty intervals
  - peak_speed > 1 (overshoot) still produces one segment per window, never inverted
  - anchors resolved by `resolve_anchors` (snap + dedupe) — see B8

### beat_drop_mapper (audio) — tools/audio/beat_drop_mapper.py
- BPM accuracy on 120 click (real): `test_phase_a_b_tools.py::test_beat_mapper_bpm_accuracy_on_120_click`
- BPM in pipeline (real): `test_pipeline.py::test_beat_drop_mapper_bpm`
- **covered** (this is the B9 regression test — already present, confirmed.)

### audio_master_duck (audio) — tools/audio/audio_master_duck.py
- RMS envelope shape (pure): `test_audio_master_duck.py::test_rms_envelope_shape_and_energy`
- gain envelope bounds + ducking (pure): `test_audio_master_duck.py::test_gain_envelope_bounds_and_ducking`
- attack faster than release (pure): `test_audio_master_duck.py::test_gain_envelope_attack_faster_than_release`
- run renders + measures duck (real): `test_audio_master_duck.py::test_run_renders_and_measures_duck`
- no voice -> no duck (real): `test_audio_master_duck.py::test_run_no_voice_no_duck`
- **covered.** (Backlog B6 listed this as a gap; it is in fact covered.)

### kinetic_word_sync (subtitle) — tools/subtitle/kinetic_word_sync.py
- timing on real audio (real): `test_kinetic_word_sync.py::test_kinetic_word_sync_real_audio`, `test_phaseB5_C.py::test_word_sync_timing_on_real_audio`
- missing file (real): `test_kinetic_word_sync.py::test_kinetic_word_sync_missing_file`, `test_phaseB5_C.py::test_word_sync_missing_file`
- **covered.**

## Product layer
- presets (pure): `test_motion_presets.py` (selectable, unknown raises, curve shapes, build plan, drop times, none=noop)
- audio-sync anchors (pure): `test_audio_sync_anchors.py` (snap off-grid, tolerance zero, merge/dedup, no-drift — this is the B8 test, already present)
- batch orchestration (pure): `test_batch.py` (11 tests: manifest parse, validate, early-reject, clobber-free, retry, parallel, structured progress — this is the B10 test, already present)
- fps regression (product): `test_fps_regression.py` (3 tests)
- studio e2e + graceful no-audio (real): `test_kinetic_studio.py`
- preview mode (product): `test_preview_mode.py`
- build_fitness_short pipeline (real): `test_build_fitness_short.py`
- pipeline runner (real): `test_pipeline_runner.py`
- release check (product): `test_release_check.py`
- **covered.**

## Remotion HUD (React/TS)
- No automated JS test harness in this Python repo. Verified by `tsc --noEmit` (type check)
  per VERIFY.md; interactive 60fps preview requires a browser/GPU session (not executed).
- **gap (accepted):** no unit tests for HUD components (RepCounter/ExerciseNameCard/
  BrandWatermark/KineticCaptions). Out of scope for this Python-only test pass; would need
  a jsdom/vitest setup under `remotion/`.

## Summary of genuine gaps (after this inventory)
1. ramper pure-helper edge cases — **closed this pass** (test_ramper_edgecases.py).
2. human-clip pose accuracy — blocked on missing asset (honest, not a code gap).
3. Remotion HUD component unit tests — needs a JS test setup; deferred.
All other "gaps" named in the backlog (motion-energy, smart-reframe, audio-ducking,
beat-sync, batch) are already covered by existing tests; no duplicate tests were added.
