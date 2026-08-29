"""Item 12 — release-check gate tests.

The release gate must FAIL when required metadata is missing (so a release can't ship
half-documented) and PASS when everything is present. Covers both the pure check_release()
and the CLI exit code.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(os.path.dirname(HERE), "..", "openmontage")
sys.path.insert(0, REPO)

from scripts.release_check import check_release


def _make_repo(tmp_path, *, version="1.1.0", changelog=True, with_features=True, empty_readme=False):
    from pathlib import Path
    root = Path(tmp_path) / "repo"
    root.mkdir()
    (root / "VERSION").write_text(version + "\n")
    if empty_readme:
        (root / "README.md").write_text("")
        (root / "kinetic_studio").mkdir()
        (root / "kinetic_studio" / "README.md").write_text("")
    else:
        (root / "README.md").write_text("# OpenMontage\n")
        (root / "kinetic_studio").mkdir()
        (root / "kinetic_studio" / "README.md").write_text("# Kinetic Studio\n")
    if changelog:
        (root / "CHANGELOG.md").write_text(f"# Changelog\n\n## {version}\n- batch + presets\n")
    if with_features:
        (root / "kinetic_studio" / "orchestrator.py").write_text(
            "def render_dims(): pass\ndef should_render_studio(): pass\nclass X:\n    preview = False\n")
        (root / "kinetic_studio" / "presets.py").write_text("x=1")
        (root / "kinetic_studio" / "batch.py").write_text("x=1")
        (root / "tools").mkdir()
        (root / "tools" / "video").mkdir()
        (root / "tools" / "video" / "kinetic_ramper.py").write_text(
            "def resolve_anchors(): pass\ndef merge_slow_windows(): pass\n")
    return str(root)


def test_release_ok_when_metadata_complete():
    root = _make_repo(__import__("tempfile").mkdtemp())
    # use tmp_path-like: build manually
    import tempfile
    root = _make_repo(tempfile.mkdtemp())
    ok, problems = check_release(root, "1.1.0")
    assert ok, problems


def test_release_fails_on_missing_version():
    import tempfile
    root = _make_repo(tempfile.mkdtemp())
    ok, problems = check_release(root, "")
    assert not ok
    assert any("version" in p for p in problems)


def test_release_fails_on_missing_features():
    import tempfile
    root = _make_repo(tempfile.mkdtemp(), with_features=False)
    ok, problems = check_release(root, "1.1.0")
    assert not ok
    assert any("v1.1 feature" in p for p in problems)


def test_release_fails_on_empty_readme():
    import tempfile
    root = _make_repo(tempfile.mkdtemp(), empty_readme=True)
    ok, problems = check_release(root, "1.1.0")
    assert not ok
    assert any("README" in p for p in problems)


def test_release_fails_when_changelog_omits_version():
    import tempfile
    root = _make_repo(tempfile.mkdtemp(), changelog=True)
    # rewrite changelog without the version
    with open(os.path.join(root, "CHANGELOG.md"), "w") as fh:
        fh.write("# Changelog\n\n## 0.9.0\n- old\n")
    ok, problems = check_release(root, "1.1.0")
    assert not ok
    assert any("CHANGELOG" in p for p in problems)


def test_cli_exit_codes():
    import tempfile, subprocess
    # good repo -> exit 0
    good = _make_repo(tempfile.mkdtemp())
    r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "release_check.py"),
                        "--repo", good, "--version", "1.1.0"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    # bad repo (no features) -> exit 1
    bad = _make_repo(tempfile.mkdtemp(), with_features=False)
    r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "release_check.py"),
                        "--repo", bad, "--version", "1.1.0"],
                       capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "NOT READY" in r.stdout
