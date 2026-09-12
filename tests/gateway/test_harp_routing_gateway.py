"""Gateway integration tests for optional HARP selector routing."""

from __future__ import annotations

import importlib
import sys
import textwrap

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.delenv("HERMES_MAX_TOKENS", raising=False)
    monkeypatch.delenv("UNIVERSAL_HARP_SELECTOR_SCRIPT", raising=False)

    saved = {
        k: v
        for k, v in sys.modules.items()
        if k.startswith(("hermes_cli", "gateway"))
    }

    def write_cfg(body: str) -> None:
        (hermes_home / "config.yaml").write_text(textwrap.dedent(body), encoding="utf-8")

    def fresh_gateway():
        for mod in list(sys.modules.keys()):
            if mod.startswith(("hermes_cli", "gateway")):
                del sys.modules[mod]
        return importlib.import_module("gateway.run")

    try:
        yield write_cfg, fresh_gateway, hermes_home
    finally:
        for mod in list(sys.modules.keys()):
            if mod.startswith(("hermes_cli", "gateway")):
                del sys.modules[mod]
        sys.modules.update(saved)


def test_gateway_applies_harp_selector_route(isolated_home, monkeypatch):
    write_cfg, fresh_gateway, hermes_home = isolated_home
    selector = hermes_home / "selector.py"
    selector.write_text(
        "print('PROVIDER: openai-codex')\nprint('MODEL: gpt-5.5')\n",
        encoding="utf-8",
    )
    write_cfg(
        f"""
        model:
          default: baseline-model
          provider: openrouter
        harp_routing:
          enabled: true
          selector_script: {selector}
          task: code_generation
          risk: standard
          timeout_seconds: 2
        """
    )

    grun = fresh_gateway()
    import hermes_cli.runtime_provider as rp

    def fake_resolve_runtime_provider(*, requested=None, **kwargs):
        if requested == "openai-codex":
            return {
                "provider": "openai-codex",
                "api_key": "codex-key",
                "base_url": "https://chatgpt.com/backend-api/codex",
                "api_mode": "codex_responses",
                "command": None,
                "args": [],
                "credential_pool": None,
            }
        return {
            "provider": "openrouter",
            "api_key": "or-key",
            "base_url": "https://openrouter.ai/api/v1",
            "api_mode": "chat_completions",
            "command": None,
            "args": [],
            "credential_pool": None,
        }

    monkeypatch.setattr(rp, "resolve_runtime_provider", fake_resolve_runtime_provider)

    runner = object.__new__(grun.GatewayRunner)
    runner._session_model_overrides = {}
    runner._last_resolved_model = {}

    model, runtime_kwargs = runner._resolve_session_agent_runtime(
        session_key="agent:main:telegram:dm:123",
        user_config={"model": {"default": "baseline-model", "provider": "openrouter"}},
    )

    assert model == "gpt-5.5"
    assert runtime_kwargs["provider"] == "openai-codex"
    assert runtime_kwargs["api_mode"] == "codex_responses"

