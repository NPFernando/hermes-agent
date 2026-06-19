from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "auto_improvement_reports.py"
spec = importlib.util.spec_from_file_location("auto_improvement_reports", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_create_report_artifacts_writes_expected_files(tmp_path):
    report_dir = mod.create_report_artifacts("20260619-report-helper", base_dir=tmp_path)

    assert report_dir == (tmp_path / "20260619-report-helper").resolve()
    assert sorted(path.name for path in report_dir.iterdir()) == sorted(mod.ARTIFACTS)
    assert json.loads((report_dir / "IDEAS.json").read_text(encoding="utf-8")) == []
    test_report = json.loads((report_dir / "TEST_REPORT.json").read_text(encoding="utf-8"))
    assert test_report["passed"] is False
    assert "Rollback Procedure" in (report_dir / "PLAN.md").read_text(encoding="utf-8")


def test_existing_artifacts_are_preserved_without_force(tmp_path):
    report_dir = mod.create_report_artifacts("cycle-001", base_dir=tmp_path)
    ideas = report_dir / "IDEAS.json"
    ideas.write_text('[{"title": "keep me"}]\n', encoding="utf-8")

    with pytest.raises(FileExistsError):
        mod.create_report_artifacts("cycle-001", base_dir=tmp_path)

    assert json.loads(ideas.read_text(encoding="utf-8"))[0]["title"] == "keep me"


def test_force_overwrites_existing_standard_artifacts(tmp_path):
    report_dir = mod.create_report_artifacts("cycle-002", base_dir=tmp_path)
    ideas = report_dir / "IDEAS.json"
    ideas.write_text('[{"title": "replace me"}]\n', encoding="utf-8")

    mod.create_report_artifacts("cycle-002", base_dir=tmp_path, force=True)

    assert json.loads(ideas.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("cycle", ["..", "ab", "bad/name", "bad name", "cycle..oops"])
def test_invalid_cycle_names_are_rejected(tmp_path, cycle):
    with pytest.raises(ValueError):
        mod.create_report_artifacts(cycle, base_dir=tmp_path)
