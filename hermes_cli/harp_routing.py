"""Optional live routing hook: ask Universal HARP which model/provider to use.

Disabled by default (``harp_routing.enabled: false`` in config.yaml). When
disabled, or on any failure, ``select_route()`` returns ``None`` and callers
fall through to the existing static ``model.default``/``fallback_providers``
resolution — this module can never make the gateway less capable than it is
today, only optionally more informed.

Calls ``harp-select-route.py`` as a subprocess rather than importing
``harp_universal`` in-process: hermes-agent and the universal-harp-engine repo
each have their own venv with different dependencies, so a subprocess call
across a plain-text CLI boundary is lower-coupling than merging dependency
sets across two independently-versioned repos.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

DEFAULT_SELECTOR = Path.home() / "workspace" / "labs" / "universal-harp-engine" / "scripts" / "harp-select-route.py"
SUBPROCESS_TIMEOUT_SECONDS = 5


def _harp_routing_config(config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = config or {}
    section = cfg.get("harp_routing")
    return section if isinstance(section, dict) else {}


def is_enabled(config: dict[str, Any] | None) -> bool:
    return bool(_harp_routing_config(config).get("enabled", False))


def _parse_selector_output(text: str) -> dict[str, str] | None:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip().upper()] = value.strip()
    model = fields.get("MODEL")
    provider = fields.get("PROVIDER")
    if not model or not provider:
        return None
    return {"model": model, "provider": provider}


def risk_for_chat_type(chat_type: str | None) -> str:
    """Coarse risk hint from the chat type alone (no message content available
    at the call site yet — see docs/hermes-agent-live-integration-scoping.md's
    "known limitation" note in the universal-harp-engine repo).

    A direct 1:1 DM defaults to ``standard`` (unchanged prior behavior). Any
    group/topic chat defaults to ``low`` — casual group discussion is
    presumed lower-stakes than a direct request, and ``low`` is a valid,
    already-approved risk tier for the canary gate.
    """
    return "standard" if (chat_type or "dm") == "dm" else "low"


def select_route(
    config: dict[str, Any] | None,
    *,
    task: str = "text_summary",
    risk: str = "standard",
    selector_path: Path | None = None,
) -> dict[str, str] | None:
    """Return ``{"model": ..., "provider": ...}`` or ``None`` (fail open).

    ``task`` defaults to the conservative choice already listed in
    ``approved_families`` for the canary-readiness gate — this hook does not
    attempt per-conversation task classification yet (no message content is
    available at the call site). ``risk`` defaults to ``"standard"`` here,
    but callers with a chat-type signal should pass ``risk_for_chat_type(...)``
    instead — see ``gateway/run.py``'s ``_resolve_session_agent_runtime``.
    """
    if not is_enabled(config):
        return None

    selector = selector_path or _harp_routing_config(config).get("selector_path") or DEFAULT_SELECTOR
    selector = Path(selector)
    if not selector.is_file():
        return None

    try:
        completed = subprocess.run(
            ["python3", str(selector), "--task", task, "--risk", risk],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if completed.returncode != 0:
        return None

    return _parse_selector_output(completed.stdout)
