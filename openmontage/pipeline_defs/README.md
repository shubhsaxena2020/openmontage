# OpenMontage — pipeline runner

Declarative chaining of the 6 fitness-video tools. A pipeline is a JSON definition with
named `inputs` and an ordered list of `steps`; each step invokes a registered `BaseTool`
and its artifacts flow to later steps via `${ref}` expressions.

## Reference syntax
- `${inputs.<name>}`  — a path from the `inputs` block (resolved relative to workdir).
- `${<step_id>.<artifact_key>}` — an artifact produced by a prior step (e.g.
  `${beats.json}` reads the `json` artifact of step `beats`).
- `${<step_id>}` — the step's primary artifact (whichever key was declared `primary`,
  else the `out` path).

The runner creates output directories automatically and captures per-step failures
(rather than aborting the whole run).

## Example
`pipeline_defs/fitness_reel.json` chains:
```
beats(beat_drop_mapper) -> ramper(map_json=${beats.json})
reframe(smart_reframe, boxes=${inputs.boxes})
captions(kinetic_word_sync, audio=${inputs.speech})
+ motion_energy, fitness_pose
```

## Run
```bash
cd openmontage
.venv-om/bin/python -m pip ...   # ensure deps (see VERIFY.md)
.venv-om/bin/python -c "from pipeline import run_pipeline_file; \
    print(run_pipeline_file('pipeline_defs/fitness_reel.json', workdir='.').ok)"
```
Outputs land in `pipeline_out/` (beats.json, energy.json, pose.json, ramped.mp4,
reframed.mp4, captions.json).
