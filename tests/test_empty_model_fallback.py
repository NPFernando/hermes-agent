"""Tests for empty model fallback — when provider is configured but model is missing."""

from unittest.mock import patch
import asyncio
import hashlib
import hmac
import json
from pathlib import Path


class TestGetDefaultModelForProvider:
    """Unit tests for hermes_cli.models.get_default_model_for_provider."""

    def test_known_provider_returns_first_model(self):
        from hermes_cli.models import get_default_model_for_provider
        result = get_default_model_for_provider("openai-codex")
        # Should return first model from _PROVIDER_MODELS["openai-codex"]
        assert result
        assert isinstance(result, str)

    def test_openrouter_returns_empty(self):
        """OpenRouter uses dynamic model fetch, no static catalog entry."""
        from hermes_cli.models import get_default_model_for_provider
        # OpenRouter is not in _PROVIDER_MODELS — it uses live fetching
        result = get_default_model_for_provider("openrouter")
        assert result == ""

    def test_unknown_provider_returns_empty(self):
        from hermes_cli.models import get_default_model_for_provider
        assert get_default_model_for_provider("nonexistent-provider") == ""

    def test_custom_provider_returns_empty(self):
        """Custom provider has no model catalog — should return empty."""
        from hermes_cli.models import get_default_model_for_provider
        # Custom providers don't have entries in _PROVIDER_MODELS
        assert get_default_model_for_provider("some-random-custom") == ""

    def test_nous_silent_default_is_not_the_expensive_flagship(self):
        """Nous Portal is a metered aggregator whose curated list is ordered
        most-capable-first, so entry [0] is the priciest flagship
        (anthropic/claude-opus-4.8). The silent fallback (provider set, no model)
        must NOT escalate to it — otherwise an unconfigured profile silently
        bills the most expensive model. Regression for the billing footgun.
        """
        from hermes_cli.models import (
            _PROVIDER_MODELS,
            _PROVIDER_SILENT_DEFAULT_OVERRIDES,
            get_default_model_for_provider,
        )

        result = get_default_model_for_provider("nous")
        assert result, "nous must resolve to a usable default model"
        assert "opus" not in result.lower(), (
            f"silent default escalated to an expensive flagship: {result!r}"
        )
        assert result != _PROVIDER_MODELS["nous"][0], (
            "silent default must not be the most-capable/priciest catalog entry"
        )
        # The override must point at a model that actually exists in the catalog.
        assert result == _PROVIDER_SILENT_DEFAULT_OVERRIDES["nous"]
        assert result in _PROVIDER_MODELS["nous"]

    def test_override_falls_back_to_catalog_when_missing(self):
        """If an override model is no longer in the catalog, fall back to [0]
        rather than returning a stale/absent id."""
        from unittest.mock import patch

        from hermes_cli import models as models_mod

        with patch.dict(
            models_mod._PROVIDER_SILENT_DEFAULT_OVERRIDES,
            {"openai-codex": "does-not-exist-model"},
            clear=False,
        ):
            result = models_mod.get_default_model_for_provider("openai-codex")
            assert result == models_mod._PROVIDER_MODELS["openai-codex"][0]


class TestGatewayEmptyModelFallback:
    """Test that _resolve_session_agent_runtime fills in empty model from provider catalog."""

    def test_empty_model_filled_from_provider(self):
        """When config has no model but provider is openai-codex, use first codex model."""
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._session_model_overrides = {}

        # Mock _resolve_gateway_model to return empty string
        # Mock _resolve_runtime_agent_kwargs to return openai-codex provider
        with patch("gateway.run._resolve_gateway_model", return_value=""), \
             patch("gateway.run._resolve_runtime_agent_kwargs", return_value={
                 "provider": "openai-codex",
                 "api_key": "test-key",
                 "base_url": "https://chatgpt.com/backend-api/codex",
                 "api_mode": "codex_responses",
             }):
            model, kwargs = runner._resolve_session_agent_runtime()

        # Model should have been filled in from provider catalog
        assert model, "Model should not be empty when provider is known"
        assert isinstance(model, str)
        assert kwargs["provider"] == "openai-codex"

    def test_nonempty_model_not_overridden(self):
        """When config has a model set, don't override it."""
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._session_model_overrides = {}

        with patch("gateway.run._resolve_gateway_model", return_value="gpt-5.4"), \
             patch("gateway.run._resolve_runtime_agent_kwargs", return_value={
                 "provider": "openai-codex",
                 "api_key": "test-key",
                 "base_url": "https://chatgpt.com/backend-api/codex",
                 "api_mode": "codex_responses",
             }):
            model, kwargs = runner._resolve_session_agent_runtime()

        assert model == "gpt-5.4", "Explicit model should not be overridden"

    def test_empty_model_no_provider_stays_empty(self):
        """When both model and provider are empty, model stays empty."""
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._session_model_overrides = {}

        with patch("gateway.run._resolve_gateway_model", return_value=""), \
             patch("gateway.run._resolve_runtime_agent_kwargs", return_value={
                 "provider": "",
                 "api_key": "test-key",
                 "base_url": "https://example.com",
                 "api_mode": "chat_completions",
             }):
            model, kwargs = runner._resolve_session_agent_runtime()

        # Can't fill in a default without knowing the provider
        assert model == ""


class TestResolveGatewayModel:
    """Test _resolve_gateway_model reads model from config correctly."""

    def test_returns_default_key(self):
        from gateway.run import _resolve_gateway_model
        assert _resolve_gateway_model({"model": {"default": "gpt-5.4"}}) == "gpt-5.4"

    def test_returns_model_key_fallback(self):
        from gateway.run import _resolve_gateway_model
        assert _resolve_gateway_model({"model": {"model": "gpt-5.4"}}) == "gpt-5.4"

    def test_returns_empty_when_missing(self):
        from gateway.run import _resolve_gateway_model
        assert _resolve_gateway_model({"model": {}}) == ""

    def test_returns_empty_when_no_model_section(self):
        from gateway.run import _resolve_gateway_model
        assert _resolve_gateway_model({}) == ""

    def test_string_model_config(self):
        from gateway.run import _resolve_gateway_model
        assert _resolve_gateway_model({"model": "my-model"}) == "my-model"


class TestGatewayHarpRouting:
    """Gateway should integrate optional HARP routing in a fail-open way."""

    def test_harp_route_decision_overrides_model_and_provider(self):
        from gateway.run import GatewayRunner
        from hermes_cli.harp_routing import HarpRouteDecision

        runner = object.__new__(GatewayRunner)
        runner._session_model_overrides = {}

        calls = []

        def _fake_runtime_kwargs(*, requested_provider=None):
            calls.append(requested_provider)
            return {
                "provider": requested_provider or "openrouter",
                "api_key": "test-key",
                "base_url": "https://example.com/v1",
                "api_mode": "chat_completions",
            }

        with patch("gateway.run._resolve_gateway_model", return_value=""), \
             patch("gateway.run._resolve_runtime_agent_kwargs", side_effect=_fake_runtime_kwargs), \
             patch(
                 "hermes_cli.harp_routing.resolve_harp_route_decision",
                 return_value=HarpRouteDecision(provider="openai-codex", model="gpt-5.5"),
             ):
            model, kwargs = runner._resolve_session_agent_runtime()

        assert model == "gpt-5.5"
        assert kwargs["provider"] == "openai-codex"
        assert calls == ["openai-codex"]
        assert runner._harp_routing_status["state"] == "applied"
        assert runner._harp_routing_status["provider"] == "openai-codex"
        assert runner._harp_routing_status["model"] == "gpt-5.5"

    def test_harp_route_provider_resolution_failure_falls_back(self):
        from gateway.run import GatewayRunner
        from hermes_cli.harp_routing import HarpRouteDecision

        runner = object.__new__(GatewayRunner)
        runner._session_model_overrides = {}

        def _fake_runtime_kwargs(*, requested_provider=None):
            if requested_provider:
                raise RuntimeError("simulated provider resolution error")
            return {
                "provider": "openrouter",
                "api_key": "fallback-key",
                "base_url": "https://openrouter.ai/api/v1",
                "api_mode": "chat_completions",
            }

        with patch("gateway.run._resolve_gateway_model", return_value="gpt-5.4"), \
             patch("gateway.run._resolve_runtime_agent_kwargs", side_effect=_fake_runtime_kwargs), \
             patch(
                 "hermes_cli.harp_routing.resolve_harp_route_decision",
                 return_value=HarpRouteDecision(provider="openai-codex", model="gpt-5.5"),
             ):
            model, kwargs = runner._resolve_session_agent_runtime()

        assert model == "gpt-5.4"
        assert kwargs["provider"] == "openrouter"
        assert runner._harp_routing_status["state"] == "failed"

    def test_harp_failures_can_auto_disable_routing(self):
        from gateway.run import GatewayRunner
        from hermes_cli.harp_routing import HarpRouteDecision

        runner = object.__new__(GatewayRunner)
        runner._session_model_overrides = {}

        def _fake_runtime_kwargs(*, requested_provider=None):
            if requested_provider:
                raise RuntimeError("simulated provider resolution error")
            return {
                "provider": "openrouter",
                "api_key": "fallback-key",
                "base_url": "https://openrouter.ai/api/v1",
                "api_mode": "chat_completions",
            }

        cfg = {
            "harp_routing": {
                "enabled": True,
                "history_size": 20,
                "auto_disable_failure_threshold": 1,
                "auto_disable_window_seconds": 300,
            }
        }
        writes = []

        with patch("gateway.run._resolve_gateway_model", return_value="gpt-5.4"), \
             patch("gateway.run._resolve_runtime_agent_kwargs", side_effect=_fake_runtime_kwargs), \
             patch("gateway.run._load_gateway_config", return_value=cfg), \
             patch("gateway.run.atomic_yaml_write", side_effect=lambda path, payload, sort_keys=False: writes.append((path, payload))), \
             patch(
                 "hermes_cli.harp_routing.resolve_harp_route_decision",
                 return_value=HarpRouteDecision(provider="openai-codex", model="gpt-5.5"),
             ):
            runner._resolve_session_agent_runtime()

        assert writes, "auto-disable should persist harp_routing.enabled=false"
        assert runner._harp_routing_status["state"] == "auto_disabled"

    def test_harp_auto_disable_can_emit_alert_hook(self):
        from gateway.run import GatewayRunner
        from hermes_cli.harp_routing import HarpRouteDecision

        runner = object.__new__(GatewayRunner)
        runner._session_model_overrides = {}

        class _FakeLoop:
            def __init__(self):
                self.count = 0

            def is_running(self):
                return True

            def create_task(self, coro):
                self.count += 1
                coro.close()
                return None

        runner._gateway_loop = _FakeLoop()

        def _fake_runtime_kwargs(*, requested_provider=None):
            if requested_provider:
                raise RuntimeError("simulated provider resolution error")
            return {
                "provider": "openrouter",
                "api_key": "fallback-key",
                "base_url": "https://openrouter.ai/api/v1",
                "api_mode": "chat_completions",
            }

        cfg = {
            "harp_routing": {
                "enabled": True,
                "history_size": 20,
                "auto_disable_failure_threshold": 1,
                "auto_disable_window_seconds": 300,
                "alert_on_auto_disable": True,
            }
        }

        with patch("gateway.run._resolve_gateway_model", return_value="gpt-5.4"), \
             patch("gateway.run._resolve_runtime_agent_kwargs", side_effect=_fake_runtime_kwargs), \
             patch("gateway.run._load_gateway_config", return_value=cfg), \
             patch("gateway.run.atomic_yaml_write"), \
             patch("gateway.run.atomic_json_write"), \
             patch(
                 "hermes_cli.harp_routing.resolve_harp_route_decision",
                 return_value=HarpRouteDecision(provider="openai-codex", model="gpt-5.5"),
             ):
            runner._resolve_session_agent_runtime()

        assert runner._gateway_loop.count == 2

    def test_harp_status_command_shows_recent_decisions(self):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._harp_routing_status = {
            "state": "applied",
            "provider": "openai-codex",
            "model": "gpt-5.5",
            "reason": "",
            "timestamp": 1735689600.0,
        }
        runner._harp_routing_history = [
            {
                "state": "applied",
                "provider": "openai-codex",
                "model": "gpt-5.5",
                "reason": "",
                "timestamp": 1735689600.0,
            },
            {
                "state": "failed",
                "provider": "openrouter",
                "model": "x",
                "reason": "boom",
                "timestamp": 1735689601.0,
            },
            {
                "state": "failed",
                "provider": "openrouter",
                "model": "x",
                "reason": "boom2",
                "timestamp": 1735689602.0,
            },
        ]

        with patch("gateway.run._load_gateway_config", return_value={"harp_routing": {"enabled": True}}):
            output = asyncio.run(runner._handle_harp_status_command(event=None))

        assert "HARP routing status" in output
        assert "Enabled: yes" in output
        assert "Last state: applied" in output
        assert "Provider failure counters:" in output
        assert "openrouter: 2" in output

    def test_harp_status_command_reset_clears_history(self, tmp_path):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._harp_routing_status = {"state": "applied"}
        runner._harp_routing_history = [{"state": "applied", "timestamp": 1.0}]
        runner._harp_routing_alert_history = [{"severity": "warning", "message": "x", "timestamp": 1.0}]

        status_file = tmp_path / "harp-routing-status.json"
        status_file.write_text("{}", encoding="utf-8")

        class _Event:
            def get_command_args(self):
                return "reset"

        with patch("gateway.run._hermes_home", Path(tmp_path)):
            output = asyncio.run(runner._handle_harp_status_command(event=_Event()))

        assert output == "HARP status history reset."
        assert runner._harp_routing_status == {}
        assert runner._harp_routing_history == []
        assert runner._harp_routing_alert_history == []

    def test_harp_status_command_json_output(self):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._harp_routing_status = {"state": "applied", "provider": "openai-codex", "model": "gpt-5.5"}
        runner._harp_routing_history = [
            {"state": "failed", "provider": "openrouter", "model": "x", "reason": "boom", "timestamp": 1.0}
        ]
        runner._harp_routing_alert_history = [
            {"severity": "warning", "message": "failure count 4/5", "timestamp": 2.0}
        ]

        class _Event:
            def get_command_args(self):
                return "--json"

        with patch("gateway.run._load_gateway_config", return_value={"harp_routing": {"enabled": True}}):
            output = asyncio.run(runner._handle_harp_status_command(event=_Event()))

        assert '"enabled":true' in output
        assert '"alerts":[{"message":"failure count 4/5","severity":"warning","timestamp":2.0}]' in output
        assert '"provider_failure_counts":{"openrouter":1}' in output

    def test_harp_status_command_json_tail_output(self):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._harp_routing_status = {"state": "applied"}
        runner._harp_routing_history = [
            {"state": "failed", "provider": "openrouter", "timestamp": 1.0},
            {"state": "applied", "provider": "openai-codex", "timestamp": 2.0},
        ]

        class _Event:
            def get_command_args(self):
                return "--json --tail 1"

        with patch("gateway.run._load_gateway_config", return_value={"harp_routing": {"enabled": True}}):
            output = asyncio.run(runner._handle_harp_status_command(event=_Event()))

        assert '"history":[{"provider":"openai-codex","state":"applied","timestamp":2.0}]' in output

    def test_harp_status_command_json_since_filters_history_and_alerts(self):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._harp_routing_status = {"state": "applied"}
        runner._harp_routing_history = [
            {"state": "failed", "provider": "openrouter", "timestamp": 10.0},
            {"state": "applied", "provider": "openai-codex", "timestamp": 20.0},
        ]
        runner._harp_routing_alert_history = [
            {"severity": "warning", "message": "w", "timestamp": 11.0},
            {"severity": "critical", "message": "c", "timestamp": 21.0},
        ]

        class _Event:
            def get_command_args(self):
                return "--json --since 15"

        with patch("gateway.run._load_gateway_config", return_value={"harp_routing": {"enabled": True}}):
            output = asyncio.run(runner._handle_harp_status_command(event=_Event()))

        assert '"since":15.0' in output
        assert '"history":[{"provider":"openai-codex","state":"applied","timestamp":20.0}]' in output
        assert '"alerts":[{"message":"c","severity":"critical","timestamp":21.0}]' in output

    def test_harp_status_command_json_since_id_filters_incremental(self):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._harp_routing_status = {"state": "applied"}
        runner._harp_routing_history = [
            {"decision_id": "d1", "state": "failed", "provider": "openrouter", "timestamp": 10.0},
            {"decision_id": "d2", "state": "applied", "provider": "openai-codex", "timestamp": 20.0},
        ]
        runner._harp_routing_alert_history = [
            {"audit_id": "a1", "severity": "warning", "message": "w", "timestamp": 11.0},
            {"audit_id": "a2", "severity": "critical", "message": "c", "timestamp": 21.0},
        ]

        class _Event:
            def get_command_args(self):
                return "--json --since-id d1"

        with patch("gateway.run._load_gateway_config", return_value={"harp_routing": {"enabled": True}}):
            output = asyncio.run(runner._handle_harp_status_command(event=_Event()))

        assert '"since_id":"d1"' in output
        assert '"history":[{"decision_id":"d2","provider":"openai-codex","state":"applied","timestamp":20.0}]' in output

    def test_harp_alert_audit_history_respects_size_limit(self):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._harp_routing_alert_history = []
        runner._harp_routing_history = []
        runner._harp_routing_status = {}

        cfg = {"harp_routing": {"enabled": True, "alert_history_size": 2}}
        writes = []

        with patch("gateway.run.time.time", side_effect=[1.0, 2.0, 3.0]), \
             patch("gateway.run._load_gateway_config", return_value=cfg), \
             patch("gateway.run.atomic_json_write", side_effect=lambda path, payload: writes.append(payload)):
            runner._record_harp_alert_event(severity="warning", message="a")
            runner._record_harp_alert_event(severity="warning", message="b")
            runner._record_harp_alert_event(severity="critical", message="c")

        assert len(runner._harp_routing_alert_history) == 2
        assert [row["message"] for row in runner._harp_routing_alert_history] == ["b", "c"]
        assert writes[-1]["alerts"][-1]["severity"] == "critical"

    def test_harp_critical_alert_records_audit_id_and_webhook_result(self):
        from gateway.run import GatewayRunner

        class _Cfg:
            def get_home_channel(self, _platform):
                return None

        runner = object.__new__(GatewayRunner)
        runner.adapters = {}
        runner.config = _Cfg()
        runner._harp_routing_alert_history = []
        runner._harp_routing_history = []
        runner._harp_routing_status = {}

        async def _fake_webhook(**kwargs):
            assert kwargs["severity"] == "critical"
            assert kwargs["message"] == "auto-disabled"
            return {"status": "sent", "attempts": 2, "error": ""}

        with patch.object(runner, "_send_harp_alert_webhook", side_effect=_fake_webhook), \
             patch("gateway.run.atomic_json_write"):
            asyncio.run(runner._send_harp_alert(severity="critical", message="auto-disabled"))

        assert len(runner._harp_routing_alert_history) == 1
        row = runner._harp_routing_alert_history[0]
        assert row["severity"] == "critical"
        assert row["webhook_status"] == "sent"
        assert row["webhook_attempts"] == 2
        assert row["audit_id"]
        assert row["webhook_signed"] is False

    def test_harp_webhook_uses_hmac_signature_when_secret_configured(self):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)

        class _Resp:
            status_code = 200

        class _Client:
            def __init__(self, timeout):
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, content=None, headers=None):
                assert url == "https://example.test/hook"
                assert headers is not None
                assert headers.get("X-HARP-Audit-Id") == "aid-1"
                assert str(headers.get("X-HARP-Signature", "")).startswith("sha256=")
                assert headers.get("X-HARP-Max-Skew-Seconds") == "300"
                assert headers.get("Content-Type") == "application/json"
                assert isinstance(content, str) and '"audit_id":"aid-1"' in content
                assert '"nonce":"' in content
                assert '"sent_at":"' in content
                assert '"max_skew_seconds":300' in content
                return _Resp()

        cfg = {
            "harp_routing": {
                "alert_webhook_url": "https://example.test/hook",
                "alert_webhook_secret": "topsecret",
                "alert_webhook_timeout_seconds": 3,
                "alert_webhook_max_retries": 0,
            }
        }

        with patch("gateway.run._load_gateway_config", return_value=cfg), \
             patch("gateway.run.httpx.AsyncClient", side_effect=lambda timeout: _Client(timeout)):
            result = asyncio.run(
                runner._send_harp_alert_webhook(
                    audit_id="aid-1",
                    severity="critical",
                    message="boom",
                )
            )

        assert result["status"] == "sent"
        assert result["signed"] is True

    def test_harp_verify_command_valid_signature(self):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        body = '{"audit_id":"aid-1","message":"ok"}'
        sig = "sha256=" + hmac.new(
            b"secret",
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        class _Event:
            def get_command_args(self):
                return f"--body '{body}' --signature '{sig}' --secret secret"

        output = asyncio.run(runner._handle_harp_verify_command(event=_Event()))
        assert "Valid: yes" in output

    def test_harp_verify_command_invalid_signature(self):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        body = '{"audit_id":"aid-1"}'

        class _Event:
            def get_command_args(self):
                return f"--body '{body}' --signature 'sha256=deadbeef' --secret secret"

        output = asyncio.run(runner._handle_harp_verify_command(event=_Event()))
        assert "Valid: no" in output

    def test_harp_verify_command_supports_body_and_signature_files(self, tmp_path):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        body = '{"audit_id":"aid-2","message":"ok"}'
        sig = "sha256=" + hmac.new(
            b"secret",
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        body_file = tmp_path / "body.json"
        sig_file = tmp_path / "sig.txt"
        body_file.write_text(body, encoding="utf-8")
        sig_file.write_text(sig, encoding="utf-8")

        class _Event:
            def get_command_args(self):
                return (
                    f"--body-file '{body_file}' --signature-file '{sig_file}' --secret secret"
                )

        output = asyncio.run(runner._handle_harp_verify_command(event=_Event()))
        assert "Valid: yes" in output

    def test_harp_verify_command_supports_headers_file(self, tmp_path):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        body = '{"audit_id":"aid-3","message":"ok"}'
        sig = "sha256=" + hmac.new(
            b"secret",
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        body_file = tmp_path / "body.json"
        headers_file = tmp_path / "headers.json"
        body_file.write_text(body, encoding="utf-8")
        headers_file.write_text(json.dumps({"X-HARP-Signature": sig}), encoding="utf-8")

        class _Event:
            def get_command_args(self):
                return (
                    f"--body-file '{body_file}' --headers-file '{headers_file}' --secret secret"
                )

        output = asyncio.run(runner._handle_harp_verify_command(event=_Event()))
        assert "Valid: yes" in output

    def test_harp_verify_command_strict_mode_blocks_replay(self, tmp_path):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        body_obj = {
            "audit_id": "aid-4",
            "message": "ok",
            "nonce": "nonce-1",
            "sent_at": "2026-01-01T00:00:00Z",
            "max_skew_seconds": 300,
        }
        body = json.dumps(body_obj, separators=(",", ":"))
        sig = "sha256=" + hmac.new(
            b"secret",
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        cache_file = tmp_path / "nonces.json"

        class _Event:
            def get_command_args(self):
                return (
                    f"--body '{body}' --signature '{sig}' --secret secret "
                    f"--strict --nonce-cache-file '{cache_file}' --now 1767225600"
                )

        first = asyncio.run(runner._handle_harp_verify_command(event=_Event()))
        second = asyncio.run(runner._handle_harp_verify_command(event=_Event()))
        assert "Valid: yes" in first
        assert "Strict: passed" in first
        assert "nonce replay detected" in second

    def test_harp_verify_command_json_output(self):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        body = '{"audit_id":"aid-5","message":"ok"}'
        sig = "sha256=" + hmac.new(
            b"secret",
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        class _Event:
            def get_command_args(self):
                return f"--body '{body}' --signature '{sig}' --secret secret --json"

        output = asyncio.run(runner._handle_harp_verify_command(event=_Event()))
        payload = json.loads(output)
        assert payload["ok"] is True
        assert payload["valid"] is True
        assert payload["strict"] == "disabled"
        assert payload["schema_id"] == "harp.verify.result.v1"
        assert "provider-routing.md" in payload["changelog_url"]

    def test_harp_verify_command_json_schema_output(self):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        body = '{"audit_id":"aid-6","message":"ok"}'
        sig = "sha256=" + hmac.new(
            b"secret",
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        class _Event:
            def get_command_args(self):
                return f"--body '{body}' --signature '{sig}' --secret secret --json --json-schema"

        output = asyncio.run(runner._handle_harp_verify_command(event=_Event()))
        payload = json.loads(output)
        assert payload["ok"] is True
        assert payload["schema_version"] == "1.0"
        assert payload["schema"]["type"] == "object"

    def test_harp_can_auto_reenable_after_clean_cooldown(self):
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._session_model_overrides = {}
        runner._harp_routing_history = [
            {"state": "auto_disabled", "timestamp": 1.0, "provider": "", "model": "", "reason": "", "session_key": ""}
        ]
        runner._harp_routing_status = {"state": "auto_disabled", "timestamp": 1.0}

        cfg = {
            "harp_routing": {
                "enabled": False,
                "history_size": 20,
                "history_max_age_days": 14,
                "auto_reenable_cooldown_seconds": 1,
                "auto_reenable_min_clean_decisions": 1,
                "alert_on_auto_disable": False,
            }
        }
        writes = []

        with patch("gateway.run.time.time", return_value=10.0), \
             patch("gateway.run._resolve_gateway_model", return_value="baseline"), \
             patch("gateway.run._resolve_runtime_agent_kwargs", return_value={"provider": "openrouter", "api_key": "k"}), \
             patch("gateway.run._load_gateway_config", return_value=cfg), \
             patch("gateway.run.atomic_yaml_write", side_effect=lambda path, payload, sort_keys=False: writes.append(payload)), \
             patch("gateway.run.atomic_json_write"), \
             patch("hermes_cli.harp_routing.resolve_harp_route_decision", return_value=None):
            runner._resolve_session_agent_runtime()

        assert writes, "auto-reenable should write config with enabled=true"
        assert writes[-1]["harp_routing"]["enabled"] is True
        assert runner._harp_routing_status["state"] == "auto_reenabled"

    def test_harp_provider_penalty_cooldown_skips_selected_provider(self):
        from gateway.run import GatewayRunner
        from hermes_cli.harp_routing import HarpRouteDecision

        runner = object.__new__(GatewayRunner)
        runner._session_model_overrides = {}
        runner._harp_routing_history = [
            {
                "state": "failed",
                "provider": "openai-codex",
                "model": "gpt-5.5",
                "reason": "err",
                "session_key": "s",
                "timestamp": 10.0,
            }
        ]

        cfg = {
            "harp_routing": {
                "enabled": True,
                "provider_cooldown_base_seconds": 0,
                "provider_penalties": {"openai-codex": 30},
                "history_size": 20,
                "history_max_age_days": 14,
            }
        }
        calls = []

        def _runtime(*, requested_provider=None):
            calls.append(requested_provider)
            return {"provider": requested_provider or "openrouter", "api_key": "k"}

        with patch("gateway.run.time.time", return_value=20.0), \
             patch("gateway.run._resolve_gateway_model", return_value="baseline"), \
             patch("gateway.run._resolve_runtime_agent_kwargs", side_effect=_runtime), \
             patch("gateway.run._load_gateway_config", return_value=cfg), \
             patch("gateway.run.atomic_json_write"), \
             patch(
                 "hermes_cli.harp_routing.resolve_harp_route_decision",
                 return_value=HarpRouteDecision(provider="openai-codex", model="gpt-5.5"),
             ):
            model, runtime_kwargs = runner._resolve_session_agent_runtime()

        assert calls == [None]
        assert model == "baseline"
        assert runtime_kwargs["provider"] == "openrouter"
        assert runner._harp_routing_status["state"] == "provider_cooldown"

    def test_harp_provider_penalty_exponential_decay_extends_cooldown(self):
        from gateway.run import GatewayRunner
        from hermes_cli.harp_routing import HarpRouteDecision

        runner = object.__new__(GatewayRunner)
        runner._session_model_overrides = {}
        runner._harp_routing_history = [
            {"state": "failed", "provider": "openai-codex", "timestamp": 10.0},
            {"state": "failed", "provider": "openai-codex", "timestamp": 12.0},
        ]

        cfg = {
            "harp_routing": {
                "enabled": True,
                "provider_cooldown_base_seconds": 0,
                "provider_penalties": {"openai-codex": 15},
                "provider_penalty_decay": "exponential",
                "history_size": 20,
                "history_max_age_days": 14,
            }
        }
        calls = []

        def _runtime(*, requested_provider=None):
            calls.append(requested_provider)
            return {"provider": requested_provider or "openrouter", "api_key": "k"}

        with patch("gateway.run.time.time", return_value=35.0), \
             patch("gateway.run._resolve_gateway_model", return_value="baseline"), \
             patch("gateway.run._resolve_runtime_agent_kwargs", side_effect=_runtime), \
             patch("gateway.run._load_gateway_config", return_value=cfg), \
             patch("gateway.run.atomic_json_write"), \
             patch(
                 "hermes_cli.harp_routing.resolve_harp_route_decision",
                 return_value=HarpRouteDecision(provider="openai-codex", model="gpt-5.5"),
             ):
            model, runtime_kwargs = runner._resolve_session_agent_runtime()

        # With exponential decay and two consecutive failures, penalty becomes 30s.
        # At t=35 with last failure t=12, 7 seconds remain so selected provider is skipped.
        assert calls == [None]
        assert model == "baseline"
        assert runtime_kwargs["provider"] == "openrouter"
        assert runner._harp_routing_status["state"] == "provider_cooldown"
