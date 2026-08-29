"""OpenMontage pipeline runner — declarative chaining of BaseTool steps.

A pipeline is a JSON/YAML-like dict with:
  inputs:  { name: path }            # named input files
  steps:   [ { id, tool, params, out?, primary? } ]

Each step runs `make_tool(tool, **resolved_params)`. `params` may reference prior
artifacts / inputs with `${src.key}` (src = "inputs" or a prior step id; key = an
artifact name) or `${stepid}` (the step's primary artifact). After a step, its
`artifacts` are added to the namespace so later steps can consume them — this is how
tools are wired together (e.g. beat_drop_mapper -> kinetic_ramper via map_json).

The runner is dependency-light (only tools.base_tool) and resilient: a step that raises
is captured as a failed step rather than aborting the whole run, and the final
ToolResult-like summary reports per-step ok/error + output artifact paths.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tools.base_tool import BaseTool, ToolResult, get_tool, make_tool


_REF = re.compile(r"\$\{([^}]+)\}")


@dataclass
class StepResult:
    id: str
    tool: str
    ok: bool
    error: Optional[str] = None
    artifacts: Dict[str, str] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "tool": self.tool, "ok": self.ok,
                "error": self.error, "artifacts": self.artifacts,
                "metrics": self.metrics}


@dataclass
class PipelineResult:
    ok: bool
    steps: List[StepResult] = field(default_factory=list)
    workdir: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "workdir": self.workdir,
                "steps": [s.to_dict() for s in self.steps]}


class PipelineRunner:
    def __init__(self, workdir: Optional[str] = None):
        self.workdir = workdir or os.getcwd()

    # ---- reference resolution -------------------------------------------------
    def _lookup(self, ref: str, ns: Dict[str, Dict[str, Any]]) -> Any:
        if ":" in ref:
            src, key = ref.split(":", 1)
        elif "." in ref:
            src, key = ref.split(".", 1)
        else:
            src, key = ref, None
        if src not in ns:
            raise KeyError(f"pipeline ref '{ref}': unknown source '{src}'")
        if key is None or key == "":
            return ns[src].get("_primary")
        if key not in ns[src]:
            raise KeyError(f"pipeline ref '{ref}': unknown key '{key}' in '{src}'")
        return ns[src][key]

    def _resolve(self, val: Any, ns: Dict[str, Dict[str, Any]]) -> Any:
        if isinstance(val, str):
            if _REF.fullmatch(val):
                return self._lookup(_REF.fullmatch(val).group(1), ns)  # type: ignore
            return _REF.sub(lambda m: str(self._lookup(m.group(1), ns)), val)
        if isinstance(val, list):
            return [self._resolve(v, ns) for v in val]
        if isinstance(val, dict):
            return {k: self._resolve(v, ns) for k, v in val.items()}
        return val

    # ---- run ------------------------------------------------------------------
    def run(self, definition: Dict[str, Any]) -> PipelineResult:
        inputs = {k: (os.path.join(self.workdir, v) if not os.path.isabs(v) else v)
                  for k, v in (definition.get("inputs") or {}).items()}
        ns: Dict[str, Dict[str, Any]] = {"inputs": dict(inputs)}
        results: List[StepResult] = []

        for step in definition.get("steps", []):
            sid = step["id"]
            tool = step["tool"]
            params = dict(step.get("params", {}))
            # resolve references
            try:
                params = self._resolve(params, ns)
            except KeyError as e:
                sr = StepResult(id=sid, tool=tool, ok=False, error=f"ref error: {e}")
                results.append(sr)
                ns[sid] = {}
                continue

            # auto-assign output artifact paths inside workdir + ensure parent dirs.
            # When `out` is declared we force the absolute workdir-joined path (even if
            # the JSON also set out_json/out_path relatively) so tools write under workdir.
            out = step.get("out")
            if out:
                abs_out = os.path.join(self.workdir, out)
                if "out_json" in (self._tool_params(tool) or {}):
                    params["out_json"] = abs_out
                if "out_path" in (self._tool_params(tool) or {}):
                    params["out_path"] = abs_out
                os.makedirs(os.path.dirname(abs_out), exist_ok=True)

            try:
                res: ToolResult = make_tool(tool, **params)
            except Exception as e:  # noqa: BLE001 - capture, don't abort pipeline
                sr = StepResult(id=sid, tool=tool, ok=False, error=f"{type(e).__name__}: {e}")
                results.append(sr)
                ns[sid] = {}
                continue

            artifacts = dict(res.artifacts or {})
            primary = step.get("primary")
            if primary and primary in artifacts:
                artifacts["_primary"] = artifacts[primary]
            elif out:
                p = os.path.join(self.workdir, out)
                if os.path.exists(p):
                    artifacts["_primary"] = p
            ns[sid] = artifacts
            results.append(StepResult(id=sid, tool=tool, ok=res.ok,
                                      error=res.error, artifacts=artifacts,
                                      metrics=res.metrics or {}))

        ok = all(r.ok for r in results) and bool(results)
        return PipelineResult(ok=ok, steps=results, workdir=self.workdir)

    @staticmethod
    def _tool_params(tool: str) -> Optional[Dict[str, Any]]:
        cls = get_tool(tool)
        if cls is None:
            return None
        return getattr(cls, "params", None)


def run_pipeline_file(path: str, workdir: Optional[str] = None) -> PipelineResult:
    with open(path) as fh:
        definition = json.load(fh)
    return PipelineRunner(workdir=workdir).run(definition)
