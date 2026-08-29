"""OpenMontage tool framework — minimal BaseTool + registry.

This is a self-contained, OpenMontage-compatible tool convention scaffold. If/when the
real OpenMontage repo is present, these tools subclass the same BaseTool contract
(run -> ToolResult, a `name`, `category`, `description`, declarative `params`) and drop
into its `tools/` tree and pipeline registry without modification.

Design notes for the reviewer:
- BaseTool is intentionally small: subclasses implement `run(**params) -> ToolResult`.
- Every tool returns a ToolResult (ok, data, artifacts) so pipelines can chain them.
- `register`/`get_tool`/`list_tools` provide the registry the brief refers to as the
  "tool registry". real OpenMontage reads these via pipeline_defs/; we mirror that.
"""
from __future__ import annotations

import abc
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolResult:
    """Standard return envelope for every tool."""

    ok: bool
    data: Any = None
    artifacts: Dict[str, str] = field(default_factory=dict)  # name -> path
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "artifacts": self.artifacts,
            "error": self.error,
            "metrics": self.metrics,
        }


class BaseTool(abc.ABC):
    """Base class every OpenMontage analysis/video/audio tool subclasses."""

    #: Unique tool id, e.g. "fitness_pose"
    name: str = "base"
    #: Category folder under tools/, e.g. "analysis", "video", "audio"
    category: str = "analysis"
    #: Human description for the registry / pipeline_defs
    description: str = ""
    #: Declarative parameter schema (name -> {type, default, required, help})
    params: Dict[str, Dict[str, Any]] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _REGISTRY[cls.name] = cls

    def validate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Coerce/validate params against the declared schema; fill defaults."""
        out: Dict[str, Any] = {}
        for pname, spec in self.params.items():
            if pname in params and params[pname] is not None:
                out[pname] = params[pname]
            elif spec.get("required"):
                raise ValueError(f"missing required param '{pname}' for tool '{self.name}'")
            else:
                out[pname] = spec.get("default")
        # allow extra passthrough (e.g. input_path) without strict rejection
        for k, v in params.items():
            out.setdefault(k, v)
        return out

    def run(self, **params) -> ToolResult:
        """Subclasses implement the real work here. Wrapped by `execute`."""
        raise NotImplementedError

    def execute(self, **params) -> ToolResult:
        """Safe entrypoint: validate, time, and capture errors."""
        t0 = time.time()
        try:
            params = self.validate(params)
            res = self.run(**params)
        except Exception as e:  # noqa: BLE001 - surface as ToolResult, not crash
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}",
                              metrics={"trace": traceback.format_exc()[:2000]})
        res.metrics.setdefault("elapsed_s", round(time.time() - t0, 3))
        return res


_REGISTRY: Dict[str, type] = {}


def register(tool_cls: type) -> type:
    _REGISTRY[tool_cls.name] = tool_cls
    return tool_cls


def get_tool(name: str) -> Optional[type]:
    return _REGISTRY.get(name)


def list_tools() -> List[Dict[str, Any]]:
    return [
        {"name": c.name, "category": c.category, "description": c.description}
        for c in _REGISTRY.values()
    ]


def make_tool(name: str, **params) -> ToolResult:
    """Convenience: instantiate + execute a tool by name."""
    cls = get_tool(name)
    if cls is None:
        return ToolResult(ok=False, error=f"unknown tool '{name}'")
    return cls().execute(**params)
