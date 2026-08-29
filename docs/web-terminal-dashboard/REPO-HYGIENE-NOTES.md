# Repo hygiene — web-terminal dashboard docs (PR context)

This folder collects the browser-terminal (ttyd / xterm.js / tmux) dashboard audit
artifacts that were previously sitting untracked at the repo root. Promoting them into
`docs/` is pure repo hygiene so the agent-6 root stays clean.

## Contents
- `SMALL-SCREEN.md` — keypress mitigations for cramped/phone screens (the 3×2 dashboard
  does not reflow; `Ctrl-b z` zoom is the intended small-screen mode).
- `UX-AUDIT-REPORT.md` — the full small-screen + canvas-vs-webgl audit. Conclusion:
  KEEP `rendererType=canvas`; do NOT switch to webgl (context-loss has no canvas fallback,
  risking invisible panes on an always-on ops dashboard). No production change made.

## Evidence captured during this hygiene pass (2026-08-29)
- `openmontage/verify.py` was stale: it asserted `len(tl) == 5` but the engine registry
  now has 7 tools (audio_master_duck + kinetic_word_sync landed in Phase C / v1.1). The
  brittle assertion aborted the harness before exercising any tool. Fixed to `== 7`.
- Cold re-run after the fix (`.venv-om/bin/python openmontage/verify.py`): **5/5 checks
  PASS** — motion_energy (16 peaks), smart_reframe (jitter 7.9px), beat_drop_mapper
  (117.45 BPM vs 120 truth), kinetic_ramper (22 segs rendered), fitness_pose (runs,
  0 detections on synthetic box — honest, no human clip).
- The 6 long-lived `feat/*` branches (kinetic-studio, openmontage-audio-master-duck,
  openmontage-build-fitness-short, openmontage-packaging-laptop-run,
  openmontage-phaseA-pose-energy-reframe-beat, openmontage-phaseB5-ramper-sync-phaseC-hud-captions)
  were each verified with `git cherry master <branch>` → every commit is `-` (already
  applied to master via squash-merge). They carry no unmerged content and are safe to
  delete. Deletion of those branches is a separate, explicit step in this same session.

## What this PR does NOT do
- It does not change openmontage engine code beyond the verify.py assertion fix.
- It does not touch the web-terminal container, ttyd config, or ~/.tmux.conf
  (the audit explicitly recommended no production change there).
- bench/ (xterm parser-benchmark harness) is left untracked/ignored — it is audit-scratch,
  not project deliverable, and is excluded from this commit.
