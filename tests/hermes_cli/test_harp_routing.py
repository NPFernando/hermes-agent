import subprocess

from hermes_cli import harp_routing


def test_risk_for_chat_type():
    assert harp_routing.risk_for_chat_type("dm") == "standard"
    assert harp_routing.risk_for_chat_type(None) == "standard"
    assert harp_routing.risk_for_chat_type("group") == "low"
    assert harp_routing.risk_for_chat_type("channel") == "low"
    assert harp_routing.risk_for_chat_type("thread") == "low"


def test_disabled_by_default_returns_none():
    assert harp_routing.select_route({}) is None
    assert harp_routing.select_route(None) is None
    assert harp_routing.select_route({"harp_routing": {"enabled": False}}) is None


def test_missing_selector_script_returns_none(tmp_path):
    config = {"harp_routing": {"enabled": True}}
    missing = tmp_path / "does-not-exist.py"
    assert harp_routing.select_route(config, selector_path=missing) is None


def test_parses_model_and_provider(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="DECISION: free_first\nTASK: text_summary\nMODEL: nemotron-free\nPROVIDER: openrouter\n",
            stderr="",
        )

    monkeypatch.setattr(harp_routing.subprocess, "run", fake_run)
    result = harp_routing.select_route(config, selector_path=selector)
    assert result == {"model": "nemotron-free", "provider": "openrouter"}


def test_nonzero_exit_returns_none(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(harp_routing.subprocess, "run", fake_run)
    assert harp_routing.select_route(config, selector_path=selector) is None


def test_timeout_returns_none(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="harp-select-route.py", timeout=5)

    monkeypatch.setattr(harp_routing.subprocess, "run", fake_run)
    assert harp_routing.select_route(config, selector_path=selector) is None


def test_malformed_output_returns_none(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="not the expected format", stderr="")

    monkeypatch.setattr(harp_routing.subprocess, "run", fake_run)
    assert harp_routing.select_route(config, selector_path=selector) is None
