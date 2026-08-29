# OpenMontage — AGENT_GUIDE.md

Self-contained OpenMontage-style tool framework. Tools live under `tools/<category>/`
(`analysis/`, `video/`, `audio/`), each subclassing `BaseTool` from `tools/base_tool.py`.
They register themselves on import via `__init_subclass__`, and the registry
(`get_tool` / `list_tools` / `make_tool`) is what pipelines and `pipeline_defs/` consume.

## Tool contract
Every tool:
- sets `name` (unique id), `category` (`analysis`|`video`|`audio`), `description`, and
  `params` (declarative schema: `{param: {type, default, required, help}}`).
- implements `run(**params) -> ToolResult`. **Do not** call `run` directly in pipelines;
  call `execute(**params)`, which validates params, times the call, and returns a
  `ToolResult` even on exception (never raises into the pipeline).
- returns `ToolResult(ok, data, artifacts, error, metrics)` where `artifacts` maps
  logical name -> output file path (rendered video, json, csv).
- treats `input_path` (and `audio_path`) as explicit inputs; it never reads repo `.env`
  or production pointers.

## Layout
```
openmontage/
  tools/
    base_tool.py        # BaseTool, ToolResult, registry
    analysis/
      fitness_pose.py   # PHASE A.1
      motion_energy.py  # PHASE A.2
    video/
      smart_reframe.py  # PHASE A.3
      kinetic_ramper.py # PHASE B.5
    audio/
      beat_drop_mapper.py # PHASE B.4
    __init__.py         # imports all tools so registration happens
  samples/              # generated synthetic media used for verification
  tests/                # per-tool verification tests
```

## Conventions (match real OpenMontage when it is dropped in)
- CPU-first: tools must run without a GPU (YOLOv8-pose on CPU is slow but fine for tests).
- Deterministic: same input -> same output; random seed pinned where relevant.
- Honest verification: a tool "verified" against a *synthetic* generated clip is labelled
  as such; claims about a real human fitness clip require that asset to be present.
- Render tests are CPU smoke-tests (short clips, low resolution) unless a GPU is present.

## Verification status (this scaffold)
See VERIFY.md in the repo root of this build. Summary: all 5 tools implemented and run
against generated synthetic media; pose/energy/reframe/beat/ramper each produce valid
output. "Real sample clip" tests are gated on a human-clip asset being supplied.
