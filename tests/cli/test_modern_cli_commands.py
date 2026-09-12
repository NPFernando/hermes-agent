"""Tests for recently added CLI-only command behavior."""

from types import SimpleNamespace
from unittest.mock import Mock

from cli import HermesCLI


def test_cost_command_uses_existing_usage_and_does_not_fabricate_totals(monkeypatch):
    show_usage = Mock()
    cli_stub = SimpleNamespace(_show_usage=show_usage)
    printed = []
    monkeypatch.setattr("cli._cprint", lambda message, **kwargs: printed.append(str(message)))

    HermesCLI._handle_cost_command(cli_stub, "/cost 30")

    show_usage.assert_called_once_with()
    output = "\n".join(printed)
    assert "Historical cost ranges are not available" in output
    assert "$70 OpenRouter credits remaining" not in output
    assert "$0 spent this session" not in output


def test_project_command_formats_a_detected_project(monkeypatch):
    from hermes_cli import project_detect

    printed = []
    monkeypatch.setattr(project_detect, "detect_project", lambda path: {"name": "demo", "type": "node"})
    monkeypatch.setattr(project_detect, "format_project_summary", lambda project: "demo (node)")
    monkeypatch.setattr("cli._cprint", lambda message, **kwargs: printed.append(str(message)))

    HermesCLI._handle_project_command(SimpleNamespace(), "/project")

    assert "demo (node)" in "\n".join(printed)
