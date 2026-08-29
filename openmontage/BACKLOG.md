# openmontage (Kinetic Studio) — Next Backlog (autonomous work program)

Status: v1.1-openmontage-kinetic-studio shipped. Pane offered real repo-hygiene work while idle:
(1) clean up 6 stale merged feat/* branches, (2) promote SMALL-SCREEN.md / UX-AUDIT-REPORT.md into a
docs/ folder and commit them, (3) re-run verify.py against .venv-om to confirm v1.1 still passes cold.
The orchestrator APPROVES exactly that. Then continue with the fuller backlog below. Work via
branch -> PR -> squash-merge -> tag -> release.

## Phase A — Approved repo hygiene (do exactly what was proposed)
1. [ ] List the 6 stale merged feat/* branches (local + remote) and confirm each is superseded by a squash-merge.
   **done when** list produced and reconciled with git log.
2. [ ] Delete the 6 stale branches locally and remotely (safe — already merged). **done when** branches gone,
   working tree clean.
3. [ ] Create `docs/` and move SMALL-SCREEN.md + UX-AUDIT-REPORT.md into it; commit. **done when** files in
   docs/, root clean.
4. [ ] Re-run `verify.py` against `.venv-om` as a cold no-op health re-check. **done when** v1.1 still passes
   (13/13 or equivalent).
5. [ ] PR for the hygiene work -> squash-merge -> tag v1.2-hygiene. **done when** tag pushed.

## Phase B — Test & coverage
6. [ ] Inventory the test suite; document which modules lack coverage (motion-energy, pose, smart-reframe,
   audio-ducking, ramper, HUD/captions). **done when** coverage map exists.
7. [ ] Add unit tests for the kinetic ramper (v0.8) edge cases (zero-duration, overshoot). **done when** ramper
   tested.
8. [ ] Add unit tests for audio-sync anchor detection (v1.1). **done when** anchors tested.
9. [ ] Add a regression test for the beat-sync BPM extraction (v0.7) on a fixture clip. **done when** beat-sync
   tested.
10. [ ] Add tests for the batch pipeline orchestration. **done when** batch tested.

## Phase C — Features (self-contained, no new paid accounts)
11. [ ] Add a CLI subcommand to list presets + show their parameter schema. **done when** `openmontage presets
    list` works.
12. [ ] Add an export of the UX-AUDIT findings to a structured JSON for tracking. **done when** exporter present.
13. [ ] Add a small-screen (mobile vertical) preset variant referenced by SMALL-SCREEN.md. **done when** preset
    exists and is selectable.
14. [ ] Add a dry-run mode that computes the edit plan without rendering (fast preview). **done when** `--dry-run`
    prints the plan.

## Phase D — Docs & release
15. [ ] Write `docs/ARCHITECTURE.md` for the Kinetic Studio pipeline. **done when** arch doc present.
16. [ ] Add a `CHANGELOG.md` maintained per release. **done when** changelog present.
17. [ ] Tag v1.3 once B–C land with green verify. **done when** tag pushed.

## Phase E — Stretch
18. [ ] Benchmark render time on a sample short and record p50. **done when** benchmark note exists.
19. [ ] Add an ffmpeg-version compatibility check in verify.py. **done when** check present.
20. [ ] Prototype a caption-style HUD theme variant. **done when** variant selectable in demo.
