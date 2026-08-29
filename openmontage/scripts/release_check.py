#!/usr/bin/env python3
"""Release-readiness gate for OpenMontage Kinetic Studio.

Run before tagging a release. Exits non-zero (and prints the missing items) if any required
release metadata/artifact is absent, so a release can never ship half-documented or
un-versioned. Pure checks are factored into `check_release()` so they are unit-testable
without touching git.

Required:
  - a version string (VERSION file or passed via --version)
  - a CHANGELOG / release-notes file mentioning that version
  - the orchestrator exposes the v1.1 feature surface (preset + batch + preview hooks)
  - (when --git) the current HEAD commit carries a matching git tag
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import List, Tuple

REQUIRED_FILES = ["README.md", "kinetic_studio/README.md"]


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def check_release(repo_root: str, version: str, git_tagged: bool = False) -> Tuple[bool, List[str]]:
    """Return (ok, list_of_problems). Pure & testable."""
    problems: List[str] = []
    if not version or not re.match(r"^\d+\.\d+(\.\d+)?$", version.strip()):
        problems.append(f"invalid or missing version: {version!r}")

    # required files present + non-empty
    for f in REQUIRED_FILES:
        p = os.path.join(repo_root, f)
        if not os.path.exists(p) or len(_read(p).strip()) == 0:
            problems.append(f"missing/empty required file: {f}")

    # changelog mentions the version
    changelog = _read(os.path.join(repo_root, "CHANGELOG.md"))
    if changelog and version not in changelog:
        problems.append(f"CHANGELOG.md does not mention version {version}")
    # (CHANGELOG is optional; only complain if it exists but omits the version)

    # orchestrator feature surface for v1.1 must be present
    orch_src = _read(os.path.join(repo_root, "kinetic_studio", "orchestrator.py"))
    for sym in ("render_dims", "should_render_studio", "preview"):
        if sym not in orch_src:
            problems.append(f"orchestrator missing v1.1 feature: {sym}")
    ramper_src = _read(os.path.join(repo_root, "tools", "video", "kinetic_ramper.py"))
    for sym in ("resolve_anchors", "merge_slow_windows"):
        if sym not in ramper_src:
            problems.append(f"ramper missing v1.1 feature: {sym}")
    if not os.path.exists(os.path.join(repo_root, "kinetic_studio", "presets.py")):
        problems.append("kinetic_studio/presets.py missing")
    if not os.path.exists(os.path.join(repo_root, "kinetic_studio", "batch.py")):
        problems.append("kinetic_studio/batch.py missing")

    if git_tagged and not _head_has_tag(repo_root, version):
        problems.append(f"current HEAD is not tagged with {version}")

    return (len(problems) == 0, problems)


def _head_has_tag(repo_root: str, version: str) -> bool:
    try:
        import subprocess
        out = subprocess.run(["git", "tag", "--points-at", "HEAD"],
                             cwd=repo_root, capture_output=True, text=True)
        tags = out.stdout.split()
        return any(version in t for t in tags)
    except Exception:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="OpenMontage Kinetic Studio release gate")
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--version", default="", help="version to verify (else read VERSION)")
    ap.add_argument("--git", action="store_true", help="also require the HEAD to be tagged")
    args = ap.parse_args(argv)

    version = args.version
    if not version:
        version = _read(os.path.join(args.repo, "VERSION")).strip()
    ok, problems = check_release(args.repo, version, git_tagged=args.git)
    if ok:
        print(f"RELEASE OK: {version}")
        return 0
    print(f"RELEASE NOT READY ({version}):")
    for p in problems:
        print(f"  - {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
