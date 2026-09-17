"""Tests for optional Universal HARP routing integration."""

from __future__ import annotations

from pathlib import Path

from hermes_cli.harp_routing import resolve_harp_route_decision


def _write_cfg(home: Path, text: str) -> None:
    (home / "config.yaml").write_text(text, encoding="utf-8")


def test_harp_routing_disabled_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _write_cfg(
        tmp_path,
        """
harp_routing:
  enabled: false
""".lstrip(),
    )
    assert resolve_harp_route_decision() is None


def test_harp_routing_enabled_missing_selector_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _write_cfg(
        tmp_path,
        """
harp_routing:
  enabled: true
  selector_script: /does/not/exist.py
""".lstrip(),
    )
    assert resolve_harp_route_decision() is None


def test_harp_routing_enabled_parses_selector_output(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    selector = tmp_path / "selector.py"
    selector.write_text(
        "print('PROVIDER: openai-codex')\nprint('MODEL: gpt-5.5')\n",
        encoding="utf-8",
    )
    _write_cfg(
        tmp_path,
        f"""
harp_routing:
  enabled: true
  selector_script: {selector}
  task: code_generation
  risk: standard
  timeout_seconds: 2
""".lstrip(),
    )
    decision = resolve_harp_route_decision()
    assert decision is not None
    assert decision.provider == "openai-codex"
    assert decision.model == "gpt-5.5"


def test_harp_routing_nonzero_selector_fails_open(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    selector = tmp_path / "selector_fail.py"
    selector.write_text("import sys\nsys.exit(9)\n", encoding="utf-8")
    _write_cfg(
        tmp_path,
        f"""
harp_routing:
  enabled: true
  selector_script: {selector}
""".lstrip(),
    )
    assert resolve_harp_route_decision() is None

