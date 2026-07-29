"""Integration regression test for the harp_routing hook's real call site.

Covers a real bug found 2026-07-28: the hook originally passed
``self.config`` (a ``gateway.config.GatewayConfig`` dataclass — no ``.get()``
method, no ``harp_routing`` field) to ``harp_routing.select_route()``. The
fail-open ``except Exception`` silently swallowed the resulting
``AttributeError`` on every call, so the hook always no-op'd regardless of
the ``harp_routing.enabled`` flag — invisible in unit tests that call
``harp_routing.select_route()`` directly with a plain dict, since those never
exercise what the gateway actually passes in.

This test constructs a real ``GatewayRunner`` with ``runner.config`` set to
an actual ``GatewayConfig()`` instance (matching production shape exactly,
not a dict) and asserts the HARP-selected model/provider is actually used —
so a regression back to reading ``self.config`` instead of
``load_config_readonly()`` fails this test immediately.
"""

import threading
from unittest.mock import AsyncMock, MagicMock

import gateway.run as gateway_run
from gateway.config import GatewayConfig


def _make_runner():
    runner = object.__new__(gateway_run.GatewayRunner)
    runner.adapters = {}
    runner.session_store = None
    runner.config = GatewayConfig()  # real production shape, not a dict
    runner._voice_mode = {}
    runner._ephemeral_system_prompt = ""
    runner._prefill_messages = []
    runner._reasoning_config = None
    runner._show_reasoning = False
    runner._provider_routing = {}
    runner._fallback_model = None
    runner._service_tier = None
    runner._running_agents = {}
    runner._running_agents_ts = {}
    runner._background_tasks = set()
    runner._session_db = None
    runner._session_model_overrides = {}
    runner._session_reasoning_overrides = {}
    runner._pending_model_notes = {}
    runner._pending_approvals = {}
    runner._agent_cache = {}
    runner._agent_cache_lock = threading.Lock()
    runner._get_or_create_gateway_honcho = lambda session_key: (None, None)
    runner.hooks = MagicMock()
    runner.hooks.emit = AsyncMock()
    runner.hooks.loaded_hooks = []
    return runner


def test_harp_routing_used_when_enabled_with_real_gateway_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
model:
  default: gpt-5.6-terra
  provider: openai-codex
harp_routing:
  enabled: true
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    import hermes_cli.harp_routing as harp_routing

    monkeypatch.setattr(
        harp_routing, "select_route",
        lambda config, **kwargs: {"model": "nemotron-free-test", "provider": "openrouter"},
    )

    def fake_resolve_runtime_provider(*, requested=None, explicit_base_url=None, explicit_api_key=None, target_model=None):
        assert requested == "openrouter"
        return {
            "api_key": "sk-openrouter-test",
            "base_url": "https://openrouter.ai/api/v1",
            "provider": "openrouter",
            "requested_provider": "openrouter",
            "api_mode": "chat_completions",
            "command": None,
            "args": [],
            "credential_pool": None,
        }

    import hermes_cli.runtime_provider as runtime_provider

    monkeypatch.setattr(runtime_provider, "resolve_runtime_provider", fake_resolve_runtime_provider)

    runner = _make_runner()
    model, runtime_kwargs = runner._resolve_session_agent_runtime(
        session_key="agent:main:telegram:dm:999",
        user_config={"model": {"default": "gpt-5.6-terra", "provider": "openai-codex"}},
    )

    assert model == "nemotron-free-test"
    assert runtime_kwargs["provider"] == "openrouter"


def test_harp_routing_falls_through_when_disabled(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
model:
  default: gpt-5.6-terra
  provider: openai-codex
harp_routing:
  enabled: false
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    import hermes_cli.harp_routing as harp_routing

    def _explode(*_args, **_kwargs):
        raise AssertionError("select_route should not be called when harp_routing.enabled is false")

    monkeypatch.setattr(harp_routing, "select_route", _explode)

    def fake_resolve_runtime_provider(*, requested=None, explicit_base_url=None, explicit_api_key=None, target_model=None):
        return {
            "api_key": "sk-codex-test",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "provider": "openai-codex",
            "requested_provider": "openai-codex",
            "api_mode": "codex_responses",
            "command": None,
            "args": [],
            "credential_pool": None,
        }

    import hermes_cli.runtime_provider as runtime_provider

    monkeypatch.setattr(runtime_provider, "resolve_runtime_provider", fake_resolve_runtime_provider)

    runner = _make_runner()
    model, runtime_kwargs = runner._resolve_session_agent_runtime(
        session_key="agent:main:telegram:dm:999",
        user_config={"model": {"default": "gpt-5.6-terra", "provider": "openai-codex"}},
    )

    assert model == "gpt-5.6-terra"
    assert runtime_kwargs["provider"] == "openai-codex"
