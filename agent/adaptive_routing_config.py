"""Typed helpers for adaptive routing configuration.

This module intentionally has no runtime side effects. HARP routing is gated by
``adaptive_routing.enabled`` and remains disabled by default; these helpers only
parse and validate config data for future routing code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

logger = logging.getLogger(__name__)

_BALANCED_POLICY = "balanced"
_KNOWN_POLICIES = frozenset({_BALANCED_POLICY})
_GEMINI_PREFIX_STRIPPING_PROVIDERS = frozenset({"gemini", "google-gemini-cli"})

_DEFAULT_REASONING_RULES = {
    "trivial": "minimal",
    "simple": "low",
    "standard": "medium",
    "complex": "high",
    "high_risk": "high",
    "unknown": "high",
}


@dataclass
class AdaptiveRoutingApplyTo:
    delegation: bool = True
    cli: bool = False
    gateway: bool = False
    cron: bool = False
    one_shot: bool = False


@dataclass
class AdaptiveRoutingReasoning:
    mode: str = "auto"
    default_effort: str = "medium"
    rules: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_REASONING_RULES))


@dataclass
class AdaptiveRoutingPaidFallback:
    provider: str = "main"
    model: str = ""


@dataclass
class AdaptiveRoutingModel:
    id: str
    provider: str
    model: str
    policy: str = _BALANCED_POLICY


@dataclass
class AdaptiveRoutingConfig:
    enabled: bool = False
    dry_run: bool = False
    apply_to: AdaptiveRoutingApplyTo = field(default_factory=AdaptiveRoutingApplyTo)
    default_policy: str = _BALANCED_POLICY
    reasoning: AdaptiveRoutingReasoning = field(default_factory=AdaptiveRoutingReasoning)
    paid_fallback: AdaptiveRoutingPaidFallback = field(default_factory=AdaptiveRoutingPaidFallback)
    models: list[AdaptiveRoutingModel] = field(default_factory=list)


def _bool_value(raw: Any, default: bool) -> bool:
    return raw if isinstance(raw, bool) else default


def _non_empty_string(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value or None


def _policy_value(
    raw: Any,
    *,
    location: str,
    fallback: str = _BALANCED_POLICY,
    warn_if_invalid: bool = False,
) -> str:
    if isinstance(raw, str):
        policy = raw.strip().lower()
        if policy in _KNOWN_POLICIES:
            return policy
        if policy or warn_if_invalid:
            logger.warning(
                "Unknown adaptive routing policy at %s; falling back to %s",
                location,
                fallback,
            )
        return fallback

    if raw is not None or warn_if_invalid:
        logger.warning(
            "Unknown adaptive routing policy at %s; falling back to %s",
            location,
            fallback,
        )
    return fallback


def _load_apply_to(raw: Any) -> AdaptiveRoutingApplyTo:
    if not isinstance(raw, dict):
        return AdaptiveRoutingApplyTo()
    return AdaptiveRoutingApplyTo(
        delegation=_bool_value(raw.get("delegation"), True),
        cli=_bool_value(raw.get("cli"), False),
        gateway=_bool_value(raw.get("gateway"), False),
        cron=_bool_value(raw.get("cron"), False),
        one_shot=_bool_value(raw.get("one_shot"), False),
    )


def _load_reasoning(raw: Any) -> AdaptiveRoutingReasoning:
    if not isinstance(raw, dict):
        return AdaptiveRoutingReasoning()

    rules = dict(_DEFAULT_REASONING_RULES)
    raw_rules = raw.get("rules")
    if isinstance(raw_rules, dict):
        for key, value in raw_rules.items():
            clean_key = _non_empty_string(key)
            clean_value = _non_empty_string(value)
            if clean_key and clean_value:
                rules[clean_key] = clean_value

    return AdaptiveRoutingReasoning(
        mode=_non_empty_string(raw.get("mode")) or "auto",
        default_effort=_non_empty_string(raw.get("default_effort")) or "medium",
        rules=rules,
    )


def _load_paid_fallback(raw: Any) -> AdaptiveRoutingPaidFallback:
    if not isinstance(raw, dict):
        return AdaptiveRoutingPaidFallback()
    return AdaptiveRoutingPaidFallback(
        provider=_non_empty_string(raw.get("provider")) or "main",
        model=_non_empty_string(raw.get("model")) or "",
    )


def _normalize_model_for_provider(provider: str, model: str) -> str:
    if provider in _GEMINI_PREFIX_STRIPPING_PROVIDERS and model.startswith("models/"):
        return model[len("models/") :]
    return model


def _warn_invalid_model_entry(index: int, reason: str) -> None:
    # Keep warnings generic/redacted: never interpolate the raw model-entry dict
    # because future schemas may carry secret-adjacent custom data.
    logger.warning("Skipping invalid adaptive_routing.models[%s]: %s", index, reason)


def _load_model_entry(
    raw: Any,
    *,
    index: int,
    default_policy: str,
) -> AdaptiveRoutingModel | None:
    if not isinstance(raw, dict):
        _warn_invalid_model_entry(index, "entry must be an object")
        return None

    model_id = _non_empty_string(raw.get("id"))
    if not model_id:
        _warn_invalid_model_entry(index, "missing or invalid id")
        return None

    provider = _non_empty_string(raw.get("provider"))
    if not provider:
        _warn_invalid_model_entry(index, "missing provider")
        return None
    provider = provider.lower()

    model = _non_empty_string(raw.get("model"))
    if not model:
        _warn_invalid_model_entry(index, "missing model")
        return None
    model = _normalize_model_for_provider(provider, model)

    policy = default_policy
    if "policy" in raw:
        policy = _policy_value(
            raw.get("policy"),
            location=f"adaptive_routing.models[{index}].policy",
            fallback=default_policy,
            warn_if_invalid=True,
        )

    return AdaptiveRoutingModel(
        id=model_id,
        provider=provider,
        model=model,
        policy=policy,
    )


def _load_models(raw: Any, *, default_policy: str) -> list[AdaptiveRoutingModel]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        logger.warning("adaptive_routing.models must be a list; ignoring invalid value")
        return []

    models: list[AdaptiveRoutingModel] = []
    for index, entry in enumerate(raw):
        model = _load_model_entry(entry, index=index, default_policy=default_policy)
        if model is not None:
            models.append(model)
    return models


def load_adaptive_routing_config(raw_config: dict[str, Any] | None) -> AdaptiveRoutingConfig:
    """Parse ``adaptive_routing`` from a loaded config dict.

    Missing or malformed sections return the safe disabled defaults. The helper
    validates only this feature's config shape and does not enable routing by
    itself.
    """
    if not isinstance(raw_config, dict):
        return AdaptiveRoutingConfig()

    raw_section = raw_config.get("adaptive_routing")
    if not isinstance(raw_section, dict):
        return AdaptiveRoutingConfig()

    default_policy = _policy_value(
        raw_section.get("default_policy", _BALANCED_POLICY),
        location="adaptive_routing.default_policy",
        warn_if_invalid="default_policy" in raw_section,
    )

    return AdaptiveRoutingConfig(
        enabled=_bool_value(raw_section.get("enabled"), False),
        dry_run=_bool_value(raw_section.get("dry_run"), False),
        apply_to=_load_apply_to(raw_section.get("apply_to")),
        default_policy=default_policy,
        reasoning=_load_reasoning(raw_section.get("reasoning")),
        paid_fallback=_load_paid_fallback(raw_section.get("paid_fallback")),
        models=_load_models(raw_section.get("models"), default_policy=default_policy),
    )
