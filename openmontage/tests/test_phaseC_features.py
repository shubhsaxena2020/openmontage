"""Phase C feature tests (fast, no ffmpeg/video render).

Covers:
  - presets CLI list + schema (C11)
  - mobile small-screen preset variant (C13)
  - dry-run plan (no render) without negative timestamps (C14)
  - UX-AUDIT JSON exporter (C12)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kinetic_studio.presets import (  # noqa: E402
    list_presets, get_preset, preset_schema, list_presets_with_schema,
)
from kinetic_studio.orchestrator import KineticStudio  # noqa: E402
from kinetic_studio.config import KineticStudioConfig  # noqa: E402


def test_presets_list_includes_mobile():
    names = list_presets()
    assert "mobile" in names, "mobile small-screen preset must be listed"
    # all five documented presets present
    for n in ("cinematic", "energetic", "freeze", "subtle", "mobile"):
        assert n in names


def test_mobile_preset_is_small_screen_friendly():
    p = get_preset("mobile")
    # gentle ramp + soft zoom pulse keeps action centered/readable on a narrow viewport
    assert p["ramp"]["setup_speed"] < 1.5
    assert p["zoom"]["mode"] == "pulse"
    assert "mobile" in p["description"].lower() or "phone" in p["description"].lower()


def test_preset_schema_shape():
    s = preset_schema("mobile")
    assert s["name"] == "mobile"
    assert set(s) >= {"name", "description", "ramp", "zoom", "transition"}
    alls = list_presets_with_schema()
    assert len(alls) == len(list_presets())
    assert all("ramp" in x for x in alls)


def test_dry_run_produces_plan_without_rendering(tmp_path):
    # Point at a file that does NOT exist -> cv2 probe fails -> no render attempted,
    # yet a structured plan is returned (no negative timestamps).
    cfg = KineticStudioConfig()
    cfg.motion.name = "mobile"
    studio = KineticStudio(cfg, workdir=str(tmp_path))
    plan = studio.dry_run(str(tmp_path / "nope.mp4"), out_name="out.mp4")

    assert plan["preset"] == "mobile"
    assert plan["out_name"] == "out.mp4"
    # no render must have produced an output
    assert not (tmp_path / "out.mp4").exists()
    # no negative timestamps anywhere in the plan
    def has_neg(o):
        if isinstance(o, dict):
            return any(has_neg(v) for v in o.values())
        if isinstance(o, list):
            return any(has_neg(x) for x in o)
        if isinstance(o, (int, float)):
            return o < 0
        return False
    assert not has_neg(plan), "dry-run plan must not contain negative timestamps"
    # the heavy render steps are named so the caller knows what run() would do
    for step in ("reframe", "ramper", "studio_composite"):
        assert step in plan["render_steps"]


def test_dry_run_reports_render_steps_with_music(tmp_path):
    cfg = KineticStudioConfig()
    studio = KineticStudio(cfg, workdir=str(tmp_path))
    plan = studio.dry_run(str(tmp_path / "nope.mp4"), music="track.mp3")
    assert "mux_music" in plan["render_steps"]
    assert plan["audio_for_beats"] is True


def test_ux_audit_export(tmp_path):
    # Run the real exporter against the committed report and assert structured output.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "export_ux_audit",
        str(ROOT / "scripts" / "export_ux_audit.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    report = ROOT.parent / "docs" / "web-terminal-dashboard" / "UX-AUDIT-REPORT.md"
    out = tmp_path / "ux.json"
    findings = mod.main(["--report", str(report), "--out", str(out)])
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["schema_version"] == "1.0"
    assert len(data["tasks"]) == 2
    assert len(data["tldr"]) >= 1
    assert len(data["sources"]) >= 1
    # decisions captured from the report
    decisions = {t["id"]: t["decision"] for t in data["tasks"]}
    assert "Option A" in (decisions.get("task-1") or "")
    assert "canvas" in (decisions.get("task-2") or "")
