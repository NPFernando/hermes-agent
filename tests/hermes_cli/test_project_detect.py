"""Tests for local project detection used by the Hermes CLI."""

import json

from hermes_cli.project_detect import detect_project, format_project_summary


def test_detects_node_framework_and_script_commands(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({
            "name": "sample-dashboard",
            "scripts": {
                "test": "vitest run",
                "build": "vite build",
                "dev": "vite",
                "lint": "eslint .",
            },
            "dependencies": {"react": "^19.0.0"},
        }),
        encoding="utf-8",
    )

    project = detect_project(str(tmp_path))

    assert project is not None
    assert project["type"] == "node"
    assert project["name"] == "sample-dashboard"
    assert project["framework"] == "react"
    assert project["test_cmd"] == "npm test"
    assert project["build_cmd"] == "npm run build"
    assert project["dev_cmd"] == "npm run dev"
    assert project["lint_cmd"] == "npm run lint"


def test_detects_python_test_and_lint_tools(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "sample-api"\ndependencies = ["fastapi", "pytest", "ruff"]\n',
        encoding="utf-8",
    )

    project = detect_project(str(tmp_path))

    assert project is not None
    assert project["type"] == "python"
    assert project["framework"] == "fastapi"
    assert project["test_cmd"] == "pytest"
    assert project["lint_cmd"] == "ruff check"


def test_returns_none_for_directory_without_project_markers(tmp_path):
    assert detect_project(str(tmp_path)) is None


def test_formats_detected_commands_for_display():
    summary = format_project_summary({
        "name": "sample-dashboard",
        "type": "node",
        "framework": "react",
        "test_cmd": "npm test",
    })

    assert "sample-dashboard (node)" in summary
    assert "Framework: react" in summary
    assert "Test: npm test" in summary
