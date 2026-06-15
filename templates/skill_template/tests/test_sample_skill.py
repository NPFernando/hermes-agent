"""Sample unit tests for the skill template."""

import subprocess
import sys
import os


def test_skill_manifest_exists():
    """Ensure the skill manifest is present."""
    assert os.path.exists("manifest.yaml"), "manifest.yaml missing"


def test_skill_json_valid():
    """Validate that skill.json contains required fields."""
    import json
    with open("skill.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    required = {"name", "description", "version", "author"}
    assert required.issubset(data.keys()), (
        f"Missing fields in skill.json: {required - data.keys()}"
    )


def test_sample_script_runs():
    """Run the sample script and verify it produces expected output."""
    result = subprocess.run(
        [sys.executable, "scripts/sample_skill.py"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"Sample script failed: {result.stderr}"
    assert "Hello from Hermes Skill Template!" in result.stdout