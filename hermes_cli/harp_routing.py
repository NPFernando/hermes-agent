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
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_SELECTOR = Path.home() / "workspace" / "labs" / "universal-harp-engine" / "scripts" / "harp-select-route.py"
SUBPROCESS_TIMEOUT_SECONDS = 5
DEFAULT_CACHE_TTL_SECONDS = 60
HARP_PG_SCRIPTS_DIR = "/srv/projects/_hermes-control/scripts"
DEFAULT_PAID_BUDGET_DAILY_USD = 2.0
DEFAULT_PAID_BUDGET_MONTHLY_USD = 30.0
# classify_task() can produce "security_review", but harp_pg's model_evaluations
# table has no such task_type bucket yet (only "audit" is close) -- see
# docs/hermes-agent-harp-routing-runbook.md's Phase 2 notes in the
# universal-harp-engine repo. Map it for scoring-lookup purposes only; this
# does not affect classify_task()'s own return value or select_route()'s
# --task argument.
TASK_TYPE_SCORING_ALIASES = {"security_review": "audit"}
# Fallback when no eval data exists for a task_type at all.
DEFAULT_REVIEWER_PROVIDER = "claude-cli"
DEFAULT_REVIEWER_MODEL = "sonnet"


def _harp_pg_connect():
    """Import and connect to the harp_pg Postgres adapter, same pattern as
    ~/.hermes/scripts/qc-harp.sh and cost-digest-daily.sh. Returns None on any
    import/connection failure (fail-open) rather than raising."""
    try:
        if HARP_PG_SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, HARP_PG_SCRIPTS_DIR)
        import harp_pg

        return harp_pg.connect()
    except Exception:
        return None

# In-process cache of recent decisions, keyed by (selector path, task, risk).
# The routing decision is a pure function of current live conditions (rate
# limits, model availability) for a given task/risk pair — a fresh subprocess
# per message is unnecessary overhead on fast back-and-forth conversations.
# Failures are cached too (short TTL), so a genuinely-down selector doesn't
# spawn a subprocess (and log a warning) on every single message.
#
# Caches the RAW stdout text, not the parsed {"model", "provider"} dict --
# select_route() and get_candidate_chain() both need to parse the same
# subprocess output (top pick vs. the full ROUTE_CHAIN: block) without
# spawning two subprocesses for one logical decision.
_cache_lock = threading.Lock()
_cache: dict[tuple[str, str, str], tuple[float, str | None]] = {}


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


def _run_selector(
    config: dict[str, Any] | None,
    *,
    task: str,
    risk: str,
    selector_path: Path | None,
) -> str | None:
    """Run (or reuse a cached run of) ``harp-select-route.py`` for a given
    (selector, task, risk) and return its raw stdout, or ``None`` on any
    disabled/missing/failed/timed-out condition (fail open).

    Shared by ``select_route()`` (parses the top ``MODEL:``/``PROVIDER:``
    fields) and ``get_candidate_chain()`` (parses the full ``ROUTE_CHAIN:``
    block) so one logical routing decision costs exactly one subprocess call
    and one cache entry, not two.
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
        raw = None
    else:
        raw = completed.stdout if completed.returncode == 0 else None

    if ttl > 0:
        with _cache_lock:
            _cache[cache_key] = (now, raw)

    return raw


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

    Note: ``harp-select-route.py`` only accepts ``--task``/``--risk``/
    ``--allow-review-only``/``--json`` (confirmed via ``--help``) — there is
    no ``--data-class``/``--action-mode`` flag to pass through, unlike the
    broader ``harp_universal.contracts.TaskRequest`` schema used elsewhere in
    the universal-harp-engine repo. Callers needing data-class/action-mode as
    *policy* context (not selector input) should carry them separately — see
    ``plan_delegation_route()``, which accepts them for shadow-mode logging
    without forwarding anything unsupported to this subprocess call.
    """
    raw = _run_selector(config, task=task, risk=risk, selector_path=selector_path)
    if raw is None:
        return None
    return _parse_selector_output(raw)


_ROUTE_CHAIN_LINE = re.compile(
    r"^\s*\d+\.\s+(?P<provider>\S+)\s*/\s*(?P<model>\S+)\s*"
    r"\[(?P<tier>[^/\]]+)/(?P<role>[^\]]+)\]"
    r"(?:\s+score=(?P<score>[\d.]+))?\s*$"
)


def _parse_route_chain(text: str) -> list[dict[str, Any]]:
    """Parse the ``ROUTE_CHAIN:`` block from ``harp-select-route.py``'s
    output into an ordered list of candidates, e.g.::

        1. openrouter / nvidia/nemotron-3-super-120b-a12b:free [free/primary_free] score=54.85
        2. openrouter / nvidia/nemotron-3-ultra-550b-a55b:free [free/free_fallback] score=39.9
        3. openrouter / google/gemma-4-31b-it:free [free/free_fallback]

    Each entry: ``{"rank": int, "provider": str, "model": str, "tier": str,
    "role": str, "score": float | None}``. ``score`` is optional in the
    selector's own output (not every candidate has eval data), so it's
    ``None`` when absent rather than a fabricated value. Lines that don't
    match the expected shape are skipped rather than raising — this is
    parsing another script's text output, not a stable wire format, so a
    malformed/renumbered line degrades to "one fewer candidate" instead of
    breaking the whole parse.
    """
    chain: list[dict[str, Any]] = []
    in_chain = False
    for line in text.splitlines():
        if line.strip() == "ROUTE_CHAIN:" or line.rstrip().endswith("ROUTE_CHAIN:"):
            in_chain = True
            continue
        if not in_chain:
            continue
        if not line.strip():
            continue
        m = _ROUTE_CHAIN_LINE.match(line)
        if not m:
            # First non-matching line after the header ends the block (the
            # selector's output has nothing after ROUTE_CHAIN: today, but
            # this keeps the parse bounded if that ever changes).
            break
        rank_match = re.match(r"^\s*(\d+)\.", line)
        chain.append({
            "rank": int(rank_match.group(1)) if rank_match else len(chain) + 1,
            "provider": m.group("provider"),
            "model": m.group("model"),
            "tier": m.group("tier").strip(),
            "role": m.group("role").strip(),
            "score": float(m.group("score")) if m.group("score") else None,
        })
    return chain


def get_candidate_chain(
    config: dict[str, Any] | None,
    *,
    task: str = "text_summary",
    risk: str = "standard",
    selector_path: Path | None = None,
) -> list[dict[str, Any]] | None:
    """Full ranked candidate chain from ``harp-select-route.py``'s
    ``ROUTE_CHAIN:`` block, or ``None`` on disabled/missing/failed (fail
    open, same semantics as ``select_route()``).

    This is the selector's own liveness-filtered candidate order — dead or
    delisted models never appear here, unlike ``model_evaluations`` (a
    static scoring snapshot with no liveness awareness). Built for
    ``top_scoring_model_for_task()`` to cross-reference an eval-table pick
    against real-time availability before trusting it. Shares one cached
    subprocess call with ``select_route()`` for the same (selector, task,
    risk) — see ``_run_selector()``.
    """
    raw = _run_selector(config, task=task, risk=risk, selector_path=selector_path)
    if raw is None:
        return None
    return _parse_route_chain(raw)


def plan_delegation_route(
    config: dict[str, Any] | None,
    *,
    goal_text: str | None = None,
    data_class: str = "internal",
    action_mode: str = "write",
    risk: str = "standard",
    selector_path: Path | None = None,
) -> dict[str, Any]:
    """Shadow/enforce-mode routing plan for a ``delegate_task`` child.

    Thin wrapper around ``classify_task()`` + ``select_route()`` for the
    delegation boundary (``tools/delegate_tool.py``) — distinct from the
    gateway's per-message hook, but reuses the same classifier, selector
    subprocess call, cache, and fail-open semantics rather than duplicating
    them. ``data_class``/``action_mode`` are carried as policy/logging
    context only (see ``select_route()``'s docstring — the underlying
    selector script has no such flags to receive them).

    Always returns a dict, never raises — same fail-open contract as
    ``select_route()``. ``fallback_mode`` is ``"explicit_route"`` when a
    route was found, ``"inherit_parent"`` otherwise (disabled, selector
    failed, or no route available) — callers in shadow mode should always
    behave as if they saw ``"inherit_parent"`` regardless of this value;
    only ``enforce`` mode should act on ``"explicit_route"``.

    ``top_scoring_model`` is the cross-referenced per-category eval-score
    pick (``top_scoring_model_for_task()`` with ``config=`` set, so it's
    already checked against the live candidate chain — never a delisted
    model). Purely informational in both shadow and enforce mode; ``None``
    when no eval data exists for the task or nothing eval-ranked is
    currently live. Computed here (not left to individual callers) so
    shadow-mode plans carry the same signal enforce-mode logging already
    did, instead of only enforce mode seeing it.
    """
    task = classify_task(goal_text)
    try:
        route = select_route(config, task=task, risk=risk, selector_path=selector_path)
    except Exception:
        route = None
    try:
        top_scoring_model = top_scoring_model_for_task(
            task, config=config, risk=risk, selector_path=selector_path,
        )
    except Exception:
        top_scoring_model = None
    return {
        "task": task,
        "risk": risk,
        "data_class": data_class,
        "action_mode": action_mode,
        "route": route,
        "fallback_mode": "explicit_route" if route else "inherit_parent",
        "top_scoring_model": top_scoring_model,
    }


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
    timestamp, raw = cached
    decision = _parse_selector_output(raw) if raw is not None else None
    return {"enabled": True, "decision": decision, "age_seconds": round(time.monotonic() - timestamp, 1)}


def _routing_config(config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = config or {}
    delegation = cfg.get("delegation")
    routing = delegation.get("routing") if isinstance(delegation, dict) else None
    return routing if isinstance(routing, dict) else {}


def within_paid_budget(config: dict[str, Any] | None) -> bool:
    """True if today's/this month's cumulative OpenRouter spend is under the
    configured caps (``delegation.routing.paid_budget_daily_usd``/
    ``paid_budget_monthly_usd``, defaults $2/day $30/month).

    Fails open to ``False`` (block the paid route, fall through to
    inherit_parent) on any DB/import error -- a budget gate that can't verify
    spend must not silently approve it. Same ``openrouter_key_snapshots``
    cumulative-usage query pattern as ``~/.hermes/scripts/cost-digest-daily.sh``.
    """
    routing_cfg = _routing_config(config)
    try:
        daily_cap = float(routing_cfg.get("paid_budget_daily_usd", DEFAULT_PAID_BUDGET_DAILY_USD))
        monthly_cap = float(routing_cfg.get("paid_budget_monthly_usd", DEFAULT_PAID_BUDGET_MONTHLY_USD))
    except (TypeError, ValueError):
        daily_cap = DEFAULT_PAID_BUDGET_DAILY_USD
        monthly_cap = DEFAULT_PAID_BUDGET_MONTHLY_USD

    con = _harp_pg_connect()
    if con is None:
        return False
    try:
        cur = con.cursor()

        def usage_at(hours_ago: float):
            row = cur.execute(
                "SELECT usage_usd FROM openrouter_key_snapshots "
                "WHERE captured_at <= ? AND usage_usd IS NOT NULL "
                "ORDER BY captured_at DESC LIMIT 1",
                ((datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(),),
            ).fetchone()
            return row[0] if row else None

        latest_row = cur.execute(
            "SELECT usage_usd FROM openrouter_key_snapshots "
            "WHERE usage_usd IS NOT NULL ORDER BY captured_at DESC LIMIT 1"
        ).fetchone()
        if not latest_row:
            return False  # no usage data at all -- can't verify, fail closed
        usage_now = latest_row[0]

        usage_24h = usage_at(24)
        usage_30d = usage_at(24 * 30)
        burn_24h = max(0.0, usage_now - usage_24h) if usage_24h is not None else 0.0
        burn_30d = max(0.0, usage_now - usage_30d) if usage_30d is not None else 0.0

        return burn_24h < daily_cap and burn_30d < monthly_cap
    except Exception:
        return False
    finally:
        try:
            con.close()
        except Exception:
            pass


def is_free_route(route: dict[str, str] | None) -> bool:
    """True if a ``select_route()``/``plan_delegation_route()`` route is a
    free-tier OpenRouter model. Same heuristic already used elsewhere in this
    codebase (``harp_universal/broker.py``'s `_hemes_routes` filter): a
    ``":free"`` suffix on the model id. Avoids adding a ``tier`` field to
    ``select_route()``'s established return shape, which several existing
    tests assert exact equality against.
    """
    if not route:
        return False
    return route.get("provider") == "openrouter" and str(route.get("model") or "").endswith(":free")


def top_scoring_model_for_task(
    task: str,
    *,
    config: dict[str, Any] | None = None,
    risk: str = "standard",
    selector_path: Path | None = None,
) -> dict[str, str] | None:
    """Best-scoring ``{"model": ..., "provider": ...}`` for a task_type from
    ``harp_pg``'s ``model_evaluations`` table (same connection/query pattern
    as ``~/.hermes/scripts/qc-harp.sh``'s "DB Eval Scores" section).

    Returns ``None`` on any failure or when no eval rows exist for this
    task_type -- callers should fall back to their own default (this
    function does not know what a safe default model/provider is).
    ``task`` is mapped through ``TASK_TYPE_SCORING_ALIASES`` first (e.g.
    ``security_review`` -> ``audit``) since the eval table doesn't have a
    bucket for every ``classify_task()`` category yet.

    **Cross-referencing (opt-in via ``config``)**: ``model_evaluations`` is a
    static scoring snapshot with no liveness awareness -- it previously
    surfaced ``openrouter/owl-alpha`` as the top scorer for ``audit`` despite
    that model being delisted from OpenRouter (2026-07). When ``config`` is
    given, this walks the eval rows for the task_type in score order and
    returns the first one that also appears in
    ``get_candidate_chain(config, task=task, risk=risk)`` -- the selector's
    own liveness-filtered candidate list, which by construction never
    contains dead/delisted models. If no eval candidate appears in the live
    chain (or the chain can't be fetched at all), returns ``None`` rather
    than falling back to the raw top scorer -- a pick this function can't
    verify is live is worse than no pick, for any caller that might one day
    treat this as more than informational.

    When ``config`` is omitted (the original call shape), no cross-check is
    performed and the raw top-scoring row is returned unchanged -- existing
    informational-only callers and tests are unaffected.
    """
    eval_task_type = TASK_TYPE_SCORING_ALIASES.get(task, task)
    con = _harp_pg_connect()
    if con is None:
        return None
    try:
        cur = con.cursor()
        if config is None:
            row = cur.execute(
                "SELECT model_id FROM model_evaluations WHERE task_type = ? "
                "ORDER BY quality_score DESC NULLS LAST LIMIT 1",
                (eval_task_type,),
            ).fetchone()
            if not row or not row[0]:
                return None
            # model_evaluations.model_id is a bare model identifier (e.g.
            # "nvidia/nemotron-3-super-120b-a12b:free") -- provider is always
            # openrouter for these rows in current data (confirmed
            # 2026-07-30: all 9 populated task_type buckets are
            # OpenRouter-catalog models).
            return {"model": row[0], "provider": "openrouter"}

        rows = cur.execute(
            "SELECT model_id FROM model_evaluations WHERE task_type = ? "
            "ORDER BY quality_score DESC NULLS LAST",
            (eval_task_type,),
        ).fetchall()
        if not rows:
            return None

        chain = get_candidate_chain(config, task=task, risk=risk, selector_path=selector_path)
        if not chain:
            return None
        live_models = {c["model"] for c in chain}

        for row in rows:
            if row and row[0] and row[0] in live_models:
                return {"model": row[0], "provider": "openrouter"}
        return None
    except Exception:
        return None
    finally:
        try:
            con.close()
        except Exception:
            pass
