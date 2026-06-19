#!/usr/bin/env python3
"""Create standard auto-improvement cycle report artifacts.

The auto-improvement cron loop writes durable per-cycle artifacts outside the
repository so scratch files do not pollute the project root. This helper makes
that convention repeatable and easy to test:

    python scripts/auto_improvement_reports.py 20260619-my-cycle

By default artifacts are written to
``/srv/projects/auto-improvement-reports/<cycle>/``. Use ``--base-dir`` in tests
or local dry-runs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_BASE_DIR = Path("/srv/projects/auto-improvement-reports")
ARTIFACTS = ("IDEAS.json", "TASKS.md", "PLAN.md", "TEST_REPORT.json", "CLOSE_SUMMARY.md")
_CYCLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")


def _default_content(cycle: str, filename: str) -> str:
    if filename == "IDEAS.json":
        return json.dumps([], indent=2) + "\n"
    if filename == "TASKS.md":
        return f"# Tasks — {cycle}\n\n- [ ] Idea generation\n- [ ] Planning\n- [ ] Implementation\n- [ ] Testing\n- [ ] Review/deployment\n- [ ] Close/reflect\n"
    if filename == "PLAN.md":
        return f"# Plan — {cycle}\n\n## Summary\n\n## Files to Modify\n\n## Implementation Steps\n\n## Test Cases\n\n## Rollback Procedure\n"
    if filename == "TEST_REPORT.json":
        return json.dumps({"passed": False, "tests": [], "notes": "not run yet"}, indent=2) + "\n"
    if filename == "CLOSE_SUMMARY.md":
        return f"# Close Summary — {cycle}\n\n## What changed\n\n## Verification\n\n## Side effects\n\n## Follow-up ideas\n"
    raise ValueError(f"unknown artifact: {filename}")


def validate_cycle_name(cycle: str) -> str:
    """Return ``cycle`` if it is safe as one path segment, else raise ValueError."""
    if not _CYCLE_RE.fullmatch(cycle):
        raise ValueError(
            "cycle must be 3-128 chars of letters, numbers, dot, underscore, or hyphen; "
            "it must start with a letter or number"
        )
    if ".." in cycle:
        raise ValueError("cycle must not contain '..'")
    return cycle


def create_report_artifacts(cycle: str, *, base_dir: Path = DEFAULT_BASE_DIR, force: bool = False) -> Path:
    """Create standard cycle artifacts and return the resolved cycle directory.

    Existing files are preserved unless ``force`` is true. The returned path is
    resolved after creation so cron logs show the exact durable location.
    """
    cycle = validate_cycle_name(cycle)
    base_dir = Path(base_dir).expanduser()
    report_dir = base_dir / cycle
    report_dir.mkdir(parents=True, exist_ok=True)

    existing = [name for name in ARTIFACTS if (report_dir / name).exists()]
    if existing and not force:
        joined = ", ".join(existing)
        raise FileExistsError(f"refusing to overwrite existing artifacts without --force: {joined}")

    for name in ARTIFACTS:
        path = report_dir / name
        if force or not path.exists():
            path.write_text(_default_content(cycle, name), encoding="utf-8")
    return report_dir.resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create auto-improvement cycle report artifacts")
    parser.add_argument("cycle", help="Cycle id/path segment, e.g. 20260619-report-helper")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=DEFAULT_BASE_DIR,
        help=f"Report base directory (default: {DEFAULT_BASE_DIR})",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing standard artifact files")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report_dir = create_report_artifacts(args.cycle, base_dir=args.base_dir, force=args.force)
    except (FileExistsError, ValueError, OSError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(report_dir)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
