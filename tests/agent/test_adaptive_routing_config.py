"""Tests for adaptive routing config parsing."""

from __future__ import annotations

import logging

import pytest

from agent.adaptive_routing_config import (
    AdaptiveRoutingConfig,
    load_adaptive_routing_config,
)


def test_missing_section_returns_disabled_config():
    cfg = load_adaptive_routing_config({})

    assert isinstance(cfg, AdaptiveRoutingConfig)
    assert cfg.enabled is False
    assert cfg.dry_run is False
    assert cfg.default_policy == "balanced"
    assert cfg.apply_to.delegation is True
    assert cfg.apply_to.cli is False
    assert cfg.models == []


@pytest.mark.parametrize("raw_policy", ["speed", "unknown-policy", ""])
def test_unknown_default_policy_falls_back_to_balanced_with_warning(raw_policy, caplog):
    raw_config = {
        "adaptive_routing": {
            "enabled": True,
            "default_policy": raw_policy,
        }
    }

    with caplog.at_level(logging.WARNING, logger="agent.adaptive_routing_config"):
        cfg = load_adaptive_routing_config(raw_config)

    assert cfg.enabled is True
    assert cfg.default_policy == "balanced"
    assert any("unknown adaptive routing policy" in rec.message.lower() for rec in caplog.records)


def test_invalid_model_entries_are_skipped_with_redacted_warning(caplog):
    raw_config = {
        "adaptive_routing": {
            "enabled": True,
            "models": [
                "not-a-dict-with-secret-token-123",
                {"id": "missing-provider", "model": "gpt-test", "extra_secret": "secret-provider-token"},
                {"id": "missing-model", "provider": "openrouter", "api_key": "secret-model-token"},
                {"id": "", "provider": "openrouter", "model": "gpt-test", "token": "secret-id-token"},
                {"id": "valid", "provider": "openrouter", "model": "anthropic/claude-test"},
            ],
        }
    }

    with caplog.at_level(logging.WARNING, logger="agent.adaptive_routing_config"):
        cfg = load_adaptive_routing_config(raw_config)

    assert [model.id for model in cfg.models] == ["valid"]
    warnings = "\n".join(rec.message for rec in caplog.records)
    assert "adaptive_routing.models[0]" in warnings
    assert "adaptive_routing.models[1]" in warnings
    assert "adaptive_routing.models[2]" in warnings
    assert "adaptive_routing.models[3]" in warnings
    assert "secret-provider-token" not in warnings
    assert "secret-model-token" not in warnings
    assert "secret-id-token" not in warnings
    assert "not-a-dict-with-secret-token-123" not in warnings


def test_gemini_models_prefix_normalized_only_for_gemini_providers():
    raw_config = {
        "adaptive_routing": {
            "models": [
                {"id": "gemini", "provider": "gemini", "model": "models/gemini-2.5-pro"},
                {"id": "gemini-cli", "provider": "google-gemini-cli", "model": "models/gemini-2.5-flash"},
                {"id": "openrouter", "provider": "openrouter", "model": "models/gemini-2.5-pro"},
            ]
        }
    }

    cfg = load_adaptive_routing_config(raw_config)

    assert [(entry.provider, entry.model) for entry in cfg.models] == [
        ("gemini", "gemini-2.5-pro"),
        ("google-gemini-cli", "gemini-2.5-flash"),
        ("openrouter", "models/gemini-2.5-pro"),
    ]


def test_unknown_model_policy_falls_back_to_default_with_warning(caplog):
    raw_config = {
        "adaptive_routing": {
            "default_policy": "balanced",
            "models": [
                {"id": "fast", "provider": "openrouter", "model": "gpt-test", "policy": "fastest"},
            ],
        }
    }

    with caplog.at_level(logging.WARNING, logger="agent.adaptive_routing_config"):
        cfg = load_adaptive_routing_config(raw_config)

    assert cfg.models[0].policy == "balanced"
    assert any("unknown adaptive routing policy" in rec.message.lower() for rec in caplog.records)
