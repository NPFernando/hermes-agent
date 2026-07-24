#!/usr/bin/env python3
"""
Python Sister Registry — reads sister profiles from YAML + profile configs.

Sources:
  - ~/.hermes/sister_profiles.yaml  (3 delegation specialists)
  - ~/.hermes/profiles/<id>/config.yaml  (individual sister configs with sister_id)

Provides: list_sisters(), get_sister(id), match_sister(query)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))


# ── Legacy aliases ────────────────────────────────────────────────────────
ALIASES: Dict[str, str] = {
    "fofoqueiro": "bia",
    "vini": "vitoria",
    "larissinha": "larissa",
    "daiane": "daine",
}

# YAML delegation keys → canonical sister ID
YAML_KEY_TO_ID: Dict[str, str] = {
    "researcher": "luna",
    "coder": "ada",
    "builder": "maya",
}

# Canonical ID → fallback emoji (when profile config lacks display.emoji)
CANONICAL_EMOJIS: Dict[str, str] = {
    "astra": "🌟",    "luna": "🌙",     "ada": "💻",
    "maya": "🏗️",     "nova": "🔬",     "helena": "⚖️",
    "larissa": "📋",   "clara": "💼",    "bia": "📡",
    "vitoria": "🎨",   "daine": "📊",    "novus": "🏠",
}


# ── Keyword → sister scoring ──────────────────────────────────────────────
DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "astra":   ["orchestrate", "route", "delegate", "plan", "coordinate", "dispatch"],
    "luna":    ["research", "literature", "paper", "fact-check", "cite", "synthesize",
                "analyst", "deep dive", "competitive intel", "background"],
    "ada":     ["code", "debug", "refactor", "review", "PR", "type check", "lint",
                "algorithm", "architecture", "unit test"],
    "maya":    ["build", "deploy", "ship", "infra", "CI/CD", "Docker", "terraform",
                "migrate", "release", "pipeline"],
    "nova":    ["browser", "screenshot", "vision", "web search", "fetch", "scrape",
                "URL", "page", "online", "website"],
    "helena":  ["legal", "compliance", "GDPR", "contract", "regulatory", "audit",
                "policy", "terms", "liability", "jurisdiction"],
    "larissa": ["customer", "support", "helpdesk", "follow-up", "ticket", "onboarding",
                "FAQ", "user guide", "reply", "email"],
    "clara":   ["sales", "lead", "qualify", "prospect", "CRM", "pipeline", "outreach",
                "demo", "pitch", "close"],
    "bia":     ["monitor", "alert", "signal", "risk", "watchdog", "surveillance",
                "anomaly", "detect", "threshold", "trigger"],
    "vitoria": ["design", "creative", "visual", "brand", "UI", "UX", "icon", "logo",
                "palette", "layout"],
    "daine":   ["analytics", "data", "report", "dashboard", "metric", "SQL", "BI",
                "chart", "statistics", "trend"],
    "novus":   ["local", "private", "offline", "no-network", "airgap", "Ollama",
                "on-prem", "local model"],
}


def _pick_emoji(profile_emoji: Optional[str], canonical_id: str) -> str:
    """Choose the best emoji: prefer a non-generic profile emoji, then canonical, then 🤖."""
    if profile_emoji and profile_emoji != "🤖":
        return profile_emoji
    return CANONICAL_EMOJIS.get(canonical_id, "🤖")


def _resolve_alias(name: str) -> str:
    """Map legacy sister IDs to canonical IDs."""
    return ALIASES.get(name.lower(), name.lower())


def _load_sister_profiles_yaml() -> Dict[str, Any]:
    """Load the main sister_profiles.yaml file."""
    path = os.path.join(HERMES_HOME, "sister_profiles.yaml")
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def _load_profile_configs() -> Dict[str, Any]:
    """Scan ~/.hermes/profiles/*/config.yaml for entries with sister_id."""
    profiles_dir = Path(HERMES_HOME, "profiles")
    if not profiles_dir.is_dir():
        return {}
    results: Dict[str, Any] = {}
    for profile_dir in sorted(profiles_dir.iterdir()):
        if not profile_dir.is_dir():
            continue
        config_path = profile_dir / "config.yaml"
        if not config_path.exists():
            continue
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f) or {}
        sister_id = cfg.get("sister_id") or profile_dir.name
        if not sister_id:
            continue
        results[sister_id] = cfg
    return results


def list_sisters(include_disabled: bool = False) -> List[Dict[str, Any]]:
    """Return all registered sisters with canonical metadata.
    
    Merges sister_profiles.yaml (delegation specialists) with
    ~/.hermes/profiles/*/config.yaml (individual sister configs).
    """
    main = _load_sister_profiles_yaml()
    profiles = _load_profile_configs()
    
    # Build a merged dict keyed by canonical ID
    merged: Dict[str, Dict[str, Any]] = {}

    # First pass: delegation YAML entries
    for yaml_key, entry in main.items():
        if not isinstance(entry, dict):
            continue
        if not include_disabled and not entry.get("enabled", False):
            continue
        canonical = YAML_KEY_TO_ID.get(yaml_key, yaml_key.lower())
        merged[canonical] = {
            "id": canonical,
            "name": entry.get("name", canonical.title()),
            "emoji": entry.get("emoji") or CANONICAL_EMOJIS.get(canonical, "🤖"),
            "role": entry.get("role", "unknown"),
            "description": entry.get("description", ""),
            "enabled": entry.get("enabled", True),
            "system_prompt": entry.get("system_prompt", ""),
            "source": "sister_profiles.yaml",
        }

    # Second pass: profile configs (add or augment)
    for sid, cfg in profiles.items():
        canonical = _resolve_alias(sid)
        display = cfg.get("display", {}) or {}
        is_new = canonical not in merged

        if is_new:
            merged[canonical] = {
                "id": canonical,
                "name": canonical.title(),
                "emoji": _pick_emoji(display.get("emoji"), canonical),
                "role": display.get("role", cfg.get("description", "unknown")),
                "description": cfg.get("description", ""),
                "enabled": True,
                "system_prompt": cfg.get("system_prompt", ""),
                "source": f"profiles/{sid}/config.yaml",
            }
        else:
            # Augment existing: profile config provides richer system_prompt
            existing = merged[canonical]
            if cfg.get("system_prompt"):
                existing["system_prompt"] = cfg["system_prompt"]
            if display.get("emoji") and display.get("emoji") != "🤖":
                existing["emoji"] = display["emoji"]
            existing["source"] += f" + profiles/{sid}/config.yaml"

    # Sort: Astra first, then alphabetical
    result = sorted(merged.values(), key=lambda s: (0 if s["id"] == "astra" else 1, s["id"]))
    return result


def get_sister(sister_id: str) -> Optional[Dict[str, Any]]:
    """Return a single sister by ID (supports aliases)."""
    canonical = _resolve_alias(sister_id)
    for s in list_sisters(include_disabled=True):
        if s["id"] == canonical:
            return s
    return None


def match_sister(query: str, top_n: int = 3) -> List[Dict[str, Any]]:
    """Find the best sister(s) for a given task query using keyword scoring."""
    query_lower = query.lower()
    scores: Dict[str, int] = {}

    for sid, keywords in DOMAIN_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw.lower() in query_lower:
                score += 1
        if score > 0:
            scores[sid] = score

    # Sort by score descending, then by ID
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    results: List[Dict[str, Any]] = []
    for sid, score in ranked[:top_n]:
        sister = get_sister(sid)
        if sister:
            sister = dict(sister)  # shallow copy
            sister["match_score"] = score
            sister["matched_keywords"] = [
                kw for kw in DOMAIN_KEYWORDS.get(sid, [])
                if kw.lower() in query_lower
            ]
            results.append(sister)

    return results