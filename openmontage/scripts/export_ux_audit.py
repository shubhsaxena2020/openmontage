"""Export the browser-terminal UX-AUDIT findings to structured JSON for tracking.

The audit report (docs/web-terminal-dashboard/UX-AUDIT-REPORT.md) is a human narrative.
This script parses its known structure (TL;DR, two TASK sections, DECISION lines,
CHANGES MADE, SOURCES) into a stable JSON schema so findings can be tracked/diffed over
time without re-reading prose.

Usage:
  python -m scripts.export_ux_audit [--report PATH] [--out PATH]

Defaults: report = docs/web-terminal-dashboard/UX-AUDIT-REPORT.md (relative to repo root),
          out    = docs/web-terminal-dashboard/ux-audit-findings.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _repo_root() -> Path:
    # openmontage/scripts/export_ux_audit.py -> openmontage/.. = repo root
    return Path(__file__).resolve().parents[2]


def parse_report(text: str) -> dict:
    """Extract the documented structure from the audit report.

    The parser is deliberately tolerant: it keys off the recurring section headers
    (===== dividers, TASK N, DECISION:, CHANGES MADE, SOURCES) that the report uses,
    so it stays stable if wording inside a section changes. It does NOT invent findings.
    """
    out: dict = {
        "title": None,
        "date": None,
        "scope": None,
        "tldr": [],
        "tasks": [],
        "changes_made": [],
        "sources": [],
    }

    # title / date / scope lines
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        out["title"] = m.group(1).strip()
    m = re.search(r"^Date:\s*(.+)$", text, re.MULTILINE)
    if m:
        out["date"] = m.group(1).strip()
    m = re.search(r"^Scope:\s*(.+)$", text, re.MULTILINE)
    if m:
        out["scope"] = m.group(1).strip()

    # TL;DR bullets
    tldr_block = _between(text, "TL;DR", "ENVIRONMENT FACTS")
    if tldr_block:
        for line in tldr_block.splitlines():
            line = line.strip()
            if line.startswith("TASK") or line.startswith("-") or line.startswith("RECOMMENDATION"):
                out["tldr"].append(line)

    # Tasks: TASK N — TITLE ... up to the next TASK or CHANGES MADE
    task_blocks = re.split(r"^TASK\s+\d+\s+—", text, flags=re.MULTILINE)
    # task_blocks[0] is preamble before TASK 1; each subsequent is a task body.
    task_titles = re.findall(r"^TASK\s+(\d+)\s+—\s*(.+)$", text, re.MULTILINE)
    for (num, title), body in zip(task_titles, task_blocks[1:]):
        decision = None
        dm = re.search(r"^DECISION:\s*(.+)$", body, re.MULTILINE)
        if dm:
            decision = dm.group(1).strip()
        # pull the key RECOMMENDATION / recommendation lines
        recs = re.findall(r"RECOMMENDATION:\s*(.+)$", body, re.MULTILINE)
        out["tasks"].append({
            "id": f"task-{num}",
            "title": title.strip(),
            "decision": decision,
            "recommendations": [r.strip() for r in recs],
            "body_chars": len(body),
        })

    # CHANGES MADE bullets
    changes_block = _between(text, "CHANGES MADE", "SOURCES")
    if changes_block:
        for line in changes_block.splitlines():
            line = line.strip().lstrip("-").strip()
            if line and not line.startswith("==="):
                out["changes_made"].append(line)

    # SOURCES bullets
    sources_block = _between(text, "SOURCES", None)
    if sources_block:
        for line in sources_block.splitlines():
            line = line.strip().lstrip("-").strip()
            if line and not line.startswith("==="):
                out["sources"].append(line)

    return out


def _between(text: str, start_marker: str, end_marker: str | None) -> str | None:
    """Return the text of the section whose heading contains `start_marker`.

    Sections are delimited by lines of all `=` characters. We find the divider-bounded
    block whose heading line (the first non-empty line after the opening divider)
    contains `start_marker`, then slice to the next divider (or EOF if end is None).
    """
    dividers = [m.start() for m in re.finditer(r"^={5,}$", text, re.MULTILINE)]
    lines = text.splitlines()
    for i, dpos in enumerate(dividers):
        j = text.count("\n", 0, dpos) + 1  # line index just after the divider
        # heading is the first non-empty line after the divider
        heading = ""
        for k in range(j, min(j + 4, len(lines))):
            if lines[k].strip():
                heading = lines[k]
                break
        if start_marker.lower() in heading.lower():
            # section content lives BETWEEN this heading's closing divider (i+1)
            # and the next section's opening divider (i+2) — i.e. skip the
            # header rule that immediately closes the heading line.
            start = dividers[i + 1] if i + 1 < len(dividers) else dpos
            end = dividers[i + 2] if i + 2 < len(dividers) else len(text)
            return text[start:end]
    return None


def main(argv=None):
    root = _repo_root()
    ap = argparse.ArgumentParser(description="Export UX-AUDIT findings to JSON")
    ap.add_argument("--report", default=str(root / "docs" / "web-terminal-dashboard"
                                            / "UX-AUDIT-REPORT.md"))
    ap.add_argument("--out", default=str(root / "docs" / "web-terminal-dashboard"
                                         / "ux-audit-findings.json"))
    args = ap.parse_args(argv)

    report_path = Path(args.report)
    if not report_path.exists():
        raise SystemExit(f"report not found: {report_path}")
    findings = parse_report(report_path.read_text(encoding="utf-8"))
    findings["schema_version"] = "1.0"
    findings["source_report"] = str(report_path.relative_to(root))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    print(f"wrote {out_path} ({len(findings['tasks'])} tasks, "
          f"{len(findings['tldr'])} tldr, {len(findings['changes_made'])} changes, "
          f"{len(findings['sources'])} sources)")
    return findings


if __name__ == "__main__":
    main()
