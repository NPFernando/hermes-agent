import json
import os
import subprocess
import sys
import re

def run_pytest():
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest"],
            timeout=60,
            capture_output=True,
            text=True
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired as e:
        # If the process timed out, we still get stdout and stderr up to the timeout.
        return e.returncode if e.returncode is not None else 1, (e.stdout or "") + (e.stderr or "")

def run_ruff(args):
    result = subprocess.run(
        [".venv/bin/ruff"] + args,
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout + result.stderr

test_exit_code, test_output = run_pytest()
linting_exit_code, linting_output = run_ruff(["check", "."])
# Count PLW1514 issues
ruff_exit_code, ruff_output = run_ruff(["check", ".", "--select", "PLW1514"])
# Each line that contains a file path and a colon and then line and column is an issue.
# We'll count the lines that match the pattern.
pattern = r'^[^\s]+\.[^\s]+:\d+:\d+: PLW1514'
lines = ruff_output.splitlines()
linting_error_count = sum(1 for line in lines if re.match(pattern, line))
linting_passed = linting_error_count <= 5

report = {
    "test_exit_code": test_exit_code,
    "test_output": test_output,
    "linting_exit_code": linting_exit_code,
    "linting_output": linting_output,
    "linting_error_count": linting_error_count,
    "linting_passed": linting_passed
}

print(json.dumps(report, indent=2))
