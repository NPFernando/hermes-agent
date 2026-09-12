"""Tests for recently added CLI-only command behavior."""

from types import SimpleNamespace
from unittest.mock import Mock

from cli import HermesCLI


def test_cost_command_uses_existing_usage_and_does_not_fabricate_totals(capsys):
    show_usage = Mock()
    cli_stub = SimpleNamespace(_show_usage=show_usage)

    HermesCLI._handle_cost_command(cli_stub, "/cost 30")

    show_usage.assert_called_once_with()
    output = capsys.readouterr().out
    assert "Historical cost ranges are not available" in output
    assert "$70 OpenRouter credits remaining" not in output
    assert "$0 spent this session" not in output
