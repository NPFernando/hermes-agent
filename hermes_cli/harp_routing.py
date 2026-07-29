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

import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_SELECTOR = Path.home() / "workspace" / "labs" / "universal-harp-engine" / "scripts" / "harp-select-route.py"
SUBPROCESS_TIMEOUT_SECONDS = 5
DEFAULT_CACHE_TTL_SECONDS = 60

# In-process cache of recent decisions, keyed by (selector path, task, risk).
# The routing decision is a pure function of current live conditions (rate
# limits, model availability) for a given task/risk pair — a fresh subprocess
# per message is unnecessary overhead on fast back-and-forth conversations.
# Failures are cached too (short TTL), so a genuinely-down selector doesn't
# spawn a subprocess (and log a warning) on every single message.
_cache_lock = threading.Lock()
_cache: dict[tuple[str, str, str], tuple[float, dict[str, str] | None]] = {}


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


_TASK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("security_review", re.compile(r"\b(security review|vulnerabilit(y|ies)|exploit|cve-\d|pen ?test)\b", re.I)),
    ("audit", re.compile(r"\baudit\b", re.I)),
    ("debugging", re.compile(
        r"\b(traceback|stack ?trace|exception|crash(ed|ing)?|doesn'?t work|not working|"
        r"broken|fails?( to|ing)?|fix (this|the) (bug|error|issue)|bugs?\b)\b", re.I)),
    ("code_review", re.compile(r"\b(code review|review (this|my|the) (pr|code|diff|patch)|pull request)\b", re.I)),
    ("documentation", re.compile(r"\b(write (docs|documentation)|docstring|readme|document this)\b", re.I)),
    ("structured_output", re.compile(r"\b(as json|as yaml|as csv|in json format|in table format|structured output)\b", re.I)),
    ("code_generation", re.compile(
        r"\b(write a function|implement|create a script|build a|add a feature|refactor)\b", re.I)),
]


def classify_task(message_text: str | None) -> str:
    """Heuristic, keyword-based task_family guess from message content.

    Approximate by design — no ML/LLM call, purely local regex matching, so
    it's free and adds no latency. Checked in priority order (most specific
    first) so overlapping keywords (e.g. "review this bug") land on the more
    actionable category. Falls back to ``"text_summary"`` — the same
    conservative default used everywhere else in this hook — when nothing
    matches or ``message_text`` is empty/None.
    """
    if not message_text:
        return "text_summary"
    for task, pattern in _TASK_PATTERNS:
        if pattern.search(message_text):
            return task
    return "text_summary"


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

    Cached briefly per (selector, task, risk) — see ``DEFAULT_CACHE_TTL_SECONDS``
    / ``harp_routing.cache_ttl_seconds`` in config.yaml. Set the config key to
    ``0`` to disable caching entirely.
    """
    if not is_enabled(config):
        return None

    harp_cfg = _harp_routing_config(config)
    selector = selector_path or harp_cfg.get("selector_path") or DEFAULT_SELECTOR
    selector = Path(selector)
    if not selector.is_file():
        return None

    ttl = harp_cfg.get("cache_ttl_seconds", DEFAULT_CACHE_TTL_SECONDS)
    try:
        ttl = float(ttl)
    except (TypeError, ValueError):
        ttl = DEFAULT_CACHE_TTL_SECONDS

    cache_key = (str(selector), task, risk)
    now = time.monotonic()
    if ttl > 0:
        with _cache_lock:
            cached = _cache.get(cache_key)
        if cached is not None and (now - cached[0]) < ttl:
            return cached[1]

    try:
        completed = subprocess.run(
            ["python3", str(selector), "--task", task, "--risk", risk],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        result = None
    else:
        result = _parse_selector_output(completed.stdout) if completed.returncode == 0 else None

    if ttl > 0:
        with _cache_lock:
            _cache[cache_key] = (now, result)

    return result


def status_summary(
    config: dict[str, Any] | None,
    *,
    task: str = "text_summary",
    risk: str = "standard",
    selector_path: Path | None = None,
) -> dict[str, Any]:
    """Read-only status for display (e.g. ``/status``) — never calls the
    selector itself, only reports the enabled flag and whatever the existing
    cache already holds for this (task, risk) pair.
    """
    enabled = is_enabled(config)
    if not enabled:
        return {"enabled": False, "decision": None, "age_seconds": None}

    harp_cfg = _harp_routing_config(config)
    selector = selector_path or harp_cfg.get("selector_path") or DEFAULT_SELECTOR
    cache_key = (str(Path(selector)), task, risk)
    with _cache_lock:
        cached = _cache.get(cache_key)
    if cached is None:
        return {"enabled": True, "decision": None, "age_seconds": None}
    timestamp, decision = cached
    return {"enabled": True, "decision": decision, "age_seconds": round(time.monotonic() - timestamp, 1)}
