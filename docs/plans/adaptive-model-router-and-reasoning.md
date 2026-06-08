# HARP: Hermes Adaptive Routing and Reasoning Plan

> **For Hermes:** Use the `subagent-driven-development` skill to implement this plan task-by-task. Use TDD, keep changes small, and run targeted tests after every task.

**Goal:** Add a production-ready adaptive model router that uses free/low-cost models efficiently, rotates across configured models when quota/rate limits are hit, preserves the main paid/high-capability model for risky work, and automatically selects reasoning effort based on task complexity.

**Architecture:** Introduce a policy-driven routing layer between user/agent requests and provider runtime resolution. The router classifies the task, selects an appropriate model and reasoning effort, checks local quota/cooldown state, builds an ordered fallback chain, and records outcomes for future routing decisions. Existing Hermes provider resolution, fallback, credential redaction, and error classification remain the source of truth for actual provider calls.

**Tech Stack:** Python, YAML config, SQLite state under Hermes home, existing Hermes provider runtime resolver, existing fallback chain machinery, pytest.

**Feature codename:** HARP — Hermes Adaptive Routing Planner.

**Optional assistant/personality name:** Astra. This is an optional generic persona label for an efficiency-focused Hermes assistant personality, not required for routing and not tied to any user identity.

---

## 1. Problem Statement

Hermes can already use many providers and has fallback support, but model selection is mostly static:

- `model.provider` / `model.default` choose the main route.
- `delegation.provider` / `delegation.model` can pin subagents to one model.
- `fallback_providers` can reactively switch after rate-limit, overload, or connection errors.
- Existing `agent.reasoning_effort` is static per session/config.

This is inefficient for agentic workflows because:

1. Simple subtasks can waste expensive/high-reasoning models.
2. Delegated subagents may all hit the same free-model quota.
3. Free-tier quota is usually model-specific or provider-specific but not always exposed via API.
4. Users need a safe way to fall back after quota exhaustion without blindly retrying.
5. Reasoning effort should be low for simple tasks and high/xhigh only when complexity justifies it.

HARP solves this by turning routing into a conservative, inspectable policy engine.

---

## 2. Current Grounding and Constraints

### 2.1 Verified current Hermes behavior

Current Hermes already has useful primitives:

- `fallback_providers` / `fallback_model` support provider/model fallback chains.
- Error classification treats rate-limit, quota, billing, model-not-found, context overflow, and provider-policy errors differently.
- The conversation loop switches to fallback immediately for rate-limit or quota/billing shaped failures when fallback is configured.
- `delegate_task` resolves `delegation.provider` and `delegation.model` once and passes the resolved model/provider into child `AIAgent` instances.
- `/gquota` exists for Google Gemini Code Assist quota reporting, not as a generic ChatGPT/Codex quota dashboard.

### 2.2 Current limitation this plan addresses

A config block such as `quota_routing.free_providers` is not sufficient unless the active Hermes checkout has code that reads and applies it. Implementation must include code, tests, docs, and migration/validation.

### 2.3 ChatGPT / OpenAI Codex subscription constraint

Public OpenAI developer docs state that ChatGPT Plus, Pro, Business, Edu, and Enterprise plans include Codex. However, exact remaining ChatGPT/Codex subscription quota is provider-controlled and may not be programmatically exposed to Hermes.

Hermes can reliably handle these cases:

- If OpenAI/Codex returns a 429, quota, usage-limit, or rate-limit shaped error, Hermes can treat the credentials as still valid and route to a fallback model/provider.
- If the error includes `Retry-After` or reset information, Hermes can store a cooldown and avoid hammering the same route.
- If another provider/model is configured, Hermes can continue work there.

Hermes must not assume:

- that switching to another Codex model under the same ChatGPT subscription always bypasses the quota;
- that the quota is always model-specific;
- that remaining quota is knowable before a request;
- that re-authenticating fixes quota exhaustion.

Design rule: treat ChatGPT/Codex quota as opaque unless the provider exposes reliable reset/quota metadata. Fallback to other configured providers/models when exhausted.

---

## 3. Non-Goals

- Do not bypass provider terms, subscription limits, or safety policies.
- Do not scrape or store private account dashboards.
- Do not store raw prompts or secrets in routing state.
- Do not replace existing `fallback_providers`; extend and reuse it.
- Do not make free routing default for all users. It must be opt-in or safely conservative.
- Do not route sensitive/private/high-risk work to free/unknown models by default.
- Do not hard-code any user-specific paths, account IDs, API keys, locations, or credentials.

---

## 4. Core Concepts

### 4.1 Request Envelope

A normalized object describing the request being routed.

Fields:

```python
@dataclass
class RouteRequest:
    source: Literal["cli", "gateway", "delegation", "cron", "one_shot", "tui", "api"]
    prompt: str
    context_preview: str = ""
    requested_provider: str | None = None
    requested_model: str | None = None
    explicit_override: bool = False
    toolsets: list[str] | None = None
    has_files: bool = False
    has_images: bool = False
    needs_tools: bool = False
    workdir: str | None = None
```

Do not persist raw `prompt` or `context_preview` in long-term routing state.

### 4.2 Task Classification

HARP classifies work into conservative complexity/risk bands:

```text
trivial       formatting, short answers, command explanation
simple        summaries, rewriting, docs cleanup, low-risk Q&A
standard      normal coding, config explanation, moderate research
complex       multi-file refactor, debugging, architecture, PR review
high_risk     secrets, production/client data, auth, infra, destructive actions
unknown       insufficient signal; treat as high_risk or paid/main
```

Safe default:

```text
unknown -> paid/main
high_risk -> paid/main
```

### 4.3 Model Profile

A configured model entry with static metadata plus learned performance hints.

```yaml
adaptive_routing:
  models:
    - id: gemini-flash-lite-free
      provider: gemini
      model: gemini-2.5-flash-lite
      cost_class: free
      trust_tier: low_sensitive
      rpm_limit: 10
      rpd_limit: 500
      tpm_limit: 250000
      context_tokens: 1000000
      supports_tools: true
      supports_vision: true
      best_for:
        - trivial
        - simple
        - summarization
        - rewrite
      avoid_for:
        - high_risk
        - production_code_edit
        - secrets
```

### 4.4 Route Decision

The router returns an explicit decision:

```python
@dataclass
class RouteDecision:
    selected_provider: str
    selected_model: str
    selected_reasoning_effort: str | None
    is_free: bool
    classification: str
    risk: str
    selection_reason: str
    fallback_chain: list[dict]
    skipped: list[dict]
    state_updates: list[dict]
```

### 4.5 Routing State

Use SQLite, not config, for mutable state.

Suggested path:

```text
$HERMES_HOME/adaptive-routing/state.db
```

Tables:

```sql
CREATE TABLE route_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    classification TEXT,
    reasoning_effort TEXT,
    outcome TEXT NOT NULL,
    error_class TEXT,
    prompt_hash TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    duration_ms INTEGER
);

CREATE TABLE route_cooldowns (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    cooldown_until TEXT NOT NULL,
    reason TEXT NOT NULL,
    last_error_class TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (provider, model)
);

CREATE TABLE model_stats (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_kind TEXT NOT NULL,
    attempted_requests INTEGER NOT NULL DEFAULT 0,
    successful_requests INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, model, window_start, window_kind)
);
```

State must not include API keys, auth headers, raw prompts, raw responses, or local machine paths by default.

---

## 5. Configuration Design

Add a new top-level config section. Default disabled for safe upstream adoption.

```yaml
adaptive_routing:
  enabled: false
  dry_run: false
  log_decisions: true

  apply_to:
    cli: false
    gateway: false
    tui: false
    delegation: true
    cron: false
    one_shot: false

  default_policy: balanced

  policies:
    balanced:
      allow_free_for:
        - trivial
        - simple
      paid_for:
        - standard
        - complex
        - high_risk
        - unknown
      fallback_to_paid: true

    free_first:
      allow_free_for:
        - trivial
        - simple
        - standard
      paid_for:
        - complex
        - high_risk
        - unknown
      fallback_to_paid: true

    paid_only:
      paid_for:
        - trivial
        - simple
        - standard
        - complex
        - high_risk
        - unknown
      fallback_to_paid: true

  reasoning:
    mode: auto
    default_effort: medium
    min_effort: minimal
    max_effort: xhigh
    high_risk_effort: high
    rules:
      trivial: minimal
      simple: low
      standard: medium
      complex: high
      high_risk: high
      unknown: high

  paid_fallback:
    provider: main
    model: ""

  models: []
```

Compatibility rules:

1. If `adaptive_routing.enabled` is false, current behavior is unchanged.
2. Explicit CLI/provider/model overrides win.
3. `--provider paid` or `--provider main` forces configured main provider.
4. `--provider free` requests free routing and falls back according to policy.
5. Raw provider names preserve existing Hermes behavior unless a model profile explicitly maps them.
6. `delegation.provider` / `delegation.model` continue to work when adaptive routing is disabled.
7. When adaptive routing is enabled for delegation, task-level ACP overrides still win.

---

## 6. Routing Flow

```text
Incoming request
  -> Build RouteRequest
  -> If explicit paid/main/raw override, respect it
  -> Classify task complexity/risk
  -> Select reasoning effort
  -> Load model profiles
  -> Filter by capability: tools, vision, context, source
  -> Filter by policy: free/paid allowed for classification
  -> Filter by local quota windows and cooldowns
  -> Pick best route
  -> Build fallback chain: remaining suitable free models, then paid/main
  -> Resolve selected provider via existing runtime_provider
  -> Create or update AIAgent runtime
  -> Record attempt immediately
  -> On success: record usage and quality outcome
  -> On quota/rate-limit: cooldown provider+model and try fallback
```

---

## 7. Smart Reasoning Effort

### 7.1 Mapping

Recommended default mapping:

```text
trivial       -> minimal
simple        -> low
standard      -> medium
complex       -> high
high_risk     -> high
unknown       -> high
manual xhigh  -> xhigh
```

Use `xhigh` only when:

- the user explicitly asks for deep reasoning;
- the task is a hard bug/root-cause analysis;
- previous attempts failed;
- the task is security-critical and high precision matters;
- a reviewer pass finds significant issues.

### 7.2 Provider support

Some providers/models may not support all reasoning levels. The router must normalize:

```text
requested xhigh + provider supports high only -> high
requested low + provider has no reasoning control -> no reasoning config
```

### 7.3 Manual controls

Existing slash command should still work:

```text
/reasoning minimal|low|medium|high|xhigh
```

New option:

```text
/reasoning auto
```

CLI/config:

```bash
hermes config set adaptive_routing.reasoning.mode auto
```

---

## 8. Agentic Behavior

### 8.1 Astra persona concept

Astra is a proposed generic Hermes assistant personality for efficiency-focused automation.

Characteristics:

- concise, technical, direct;
- avoids expensive models unless justified;
- asks fewer questions when a safe default exists;
- routes subtasks to cheaper/free models when safe;
- escalates to main/paid models for risk, uncertainty, or failed attempts;
- reports route decisions only in verbose/debug mode.

This should be implemented as optional persona/config documentation, not as required routing logic.

### 8.2 Agentic escalation loop

For a task that fails on a free model:

```text
free model attempt fails due to quota -> next free model
free model attempt fails due to quality/invalid output -> stronger free model or paid/main
free model attempt hits safety/unknown/private-data rule -> paid/main immediately
paid/main succeeds -> record that classification may need stronger default later
```

---

## 9. Production Safety Rules

1. Main paid provider remains default unless adaptive routing is explicitly enabled.
2. Unknown/high-risk work routes to paid/main.
3. Never log API keys, auth tokens, raw headers, `.env`, `auth.json`, or provider credentials.
4. Store prompt hashes, not raw prompts, in routing state.
5. Do not persist user-specific file paths in shared defaults/docs/tests.
6. Do not automatically use free models for secrets, production/client data, auth, infrastructure, destructive commands, database migrations, CI/CD, M365/Entra/Azure/AWS/DNS/firewall tasks, or unknown risk.
7. Fallback must not retry a quota-exhausted route in a tight loop.
8. Rate-limit cooldown applies to provider+model, not whole provider, unless the error clearly says account/provider-wide.
9. Model not found is not quota. Mark model unavailable until config changes or a TTL expires.
10. Router decisions should be quiet by default and visible in verbose/debug logs.

---

## 10. Implementation Plan

### Phase 0: RFC and test scaffolding

#### Task 0.1: Add this plan to docs

**Objective:** Document the feature before implementation.

**Files:**

- Create: `docs/plans/adaptive-model-router-and-reasoning.md`

**Verification:**

```bash
git diff -- docs/plans/adaptive-model-router-and-reasoning.md
```

Expected: plan only, no credentials or machine-specific paths.

---

### Phase 1: Config schema and normalization

#### Task 1.1: Add default config section

**Objective:** Add disabled-by-default adaptive routing config.

**Files:**

- Modify: `hermes_cli/config.py`
- Test: `tests/hermes_cli/test_config.py` or nearest config test module

**Implementation:**

Add `adaptive_routing` to default config with safe disabled defaults.

**Test cases:**

- default config contains `adaptive_routing.enabled == False`;
- `adaptive_routing.apply_to.delegation == True` can exist while global enabled is false;
- config migration preserves existing user config.

**Commands:**

```bash
PYTHONPATH=. ./venv/bin/python -m pytest tests/hermes_cli/test_config.py -q -o 'addopts='
```

---

#### Task 1.2: Add typed config loader helpers

**Objective:** Normalize adaptive routing config into predictable dictionaries/dataclasses.

**Files:**

- Create: `agent/adaptive_routing_config.py`
- Test: `tests/agent/test_adaptive_routing_config.py`

**Behaviors:**

- Missing section returns disabled config.
- Unknown policy names fall back to `balanced` or disable routing with warning.
- Invalid model entries are skipped with redacted warning.
- Leading `models/` prefix in Gemini model names is normalized only where provider adapter requires it.

**Commands:**

```bash
PYTHONPATH=. ./venv/bin/python -m pytest tests/agent/test_adaptive_routing_config.py -q -o 'addopts='
```

---

### Phase 2: Routing state store

#### Task 2.1: Create SQLite state module

**Objective:** Store local quota windows, cooldowns, and route outcomes.

**Files:**

- Create: `agent/adaptive_routing_state.py`
- Test: `tests/agent/test_adaptive_routing_state.py`

**Implementation requirements:**

- Use `get_hermes_home()`.
- Create parent directory automatically.
- Use SQLite WAL mode if safe.
- Store prompt hashes only.
- Include cleanup method for old attempts.

**Test cases:**

- database initializes under temp `HERMES_HOME`;
- request attempt increments RPM/RPD counters;
- cooldown suppresses a model until expiry;
- expired cooldown is ignored;
- no raw prompt text is stored.

**Commands:**

```bash
PYTHONPATH=. ./venv/bin/python -m pytest tests/agent/test_adaptive_routing_state.py -q -o 'addopts='
```

---

### Phase 3: Task classifier

#### Task 3.1: Implement heuristic classifier

**Objective:** Classify tasks without extra LLM calls.

**Files:**

- Create: `agent/adaptive_task_classifier.py`
- Test: `tests/agent/test_adaptive_task_classifier.py`

**Initial heuristic signals:**

- high risk keywords: token, secret, password, auth, OAuth, SSH key, production, client, firewall, DNS, SSL, database migration, destructive, delete, reset hard;
- complex signals: traceback, failing tests, multi-file, architecture, race condition, PR review, root cause;
- simple signals: summarize, rewrite, explain, format, grammar, short answer;
- tool/file signals: file modification, git, Docker, CI/CD -> at least standard/complex;
- unknown -> unknown.

**Test cases:**

- secret/auth requests classify high_risk;
- summary/rewrite classify simple;
- multi-file debugging classifies complex;
- empty/ambiguous prompt classifies unknown.

**Commands:**

```bash
PYTHONPATH=. ./venv/bin/python -m pytest tests/agent/test_adaptive_task_classifier.py -q -o 'addopts='
```

---

### Phase 4: Reasoning policy

#### Task 4.1: Implement adaptive reasoning selector

**Objective:** Convert classification + config into `reasoning_config`.

**Files:**

- Create: `agent/adaptive_reasoning.py`
- Modify: `hermes_constants.py` only if `auto` must be supported by existing parser
- Test: `tests/agent/test_adaptive_reasoning.py`

**Behaviors:**

- `mode: fixed` returns current `agent.reasoning_effort` behavior.
- `mode: auto` maps classification to configured effort.
- manual `/reasoning high` still overrides auto for active session.
- provider unsupported reasoning levels degrade safely.

**Commands:**

```bash
PYTHONPATH=. ./venv/bin/python -m pytest tests/agent/test_adaptive_reasoning.py -q -o 'addopts='
```

---

### Phase 5: Router policy engine

#### Task 5.1: Implement route planner without provider calls

**Objective:** Select provider/model/fallback chain using config + state only.

**Files:**

- Create: `agent/adaptive_model_router.py`
- Test: `tests/agent/test_adaptive_model_router.py`

**Core function:**

```python
def plan_route(request: RouteRequest, config: dict, state: AdaptiveRoutingState) -> RouteDecision:
    ...
```

**Test cases:**

- disabled config returns no route mutation;
- simple delegation task selects first available free model;
- exhausted first free model selects second free model;
- high-risk task selects paid/main;
- unknown task selects paid/main;
- explicit raw provider override bypasses free router;
- `--provider free` selects free route when safe;
- no free route available returns paid/main fallback when policy allows.

**Commands:**

```bash
PYTHONPATH=. ./venv/bin/python -m pytest tests/agent/test_adaptive_model_router.py -q -o 'addopts='
```

---

#### Task 5.2: Build fallback-chain adapter

**Objective:** Convert route decision into existing Hermes `fallback_model` format.

**Files:**

- Modify: `agent/adaptive_model_router.py`
- Test: `tests/agent/test_adaptive_model_router.py`

**Rules:**

- remaining suitable free models first;
- paid/main last if `fallback_to_paid` true;
- no duplicate selected model in fallback;
- no unavailable/cooldown models in fallback;
- preserve explicit user-configured `fallback_providers` after adaptive chain or as configured by policy.

---

### Phase 6: Runtime integration for delegation

#### Task 6.1: Apply adaptive routing to `delegate_task`

**Objective:** Let subagents use model rotation instead of one pinned model when enabled.

**Files:**

- Modify: `tools/delegate_tool.py`
- Test: `tests/tools/test_delegate_tool_adaptive_routing.py`

**Integration point:**

Current child route is resolved by `_resolve_delegation_credentials()` and passed to `_build_child_agent()`. Add a shared helper before child construction:

```python
route = maybe_plan_adaptive_route(
    source="delegation",
    prompt=task_goal,
    context_preview=task_context,
    requested_provider=delegation_provider,
    requested_model=delegation_model,
)
```

**Test cases:**

- adaptive disabled: existing delegation behavior unchanged;
- adaptive enabled + simple task: child gets first free model;
- adaptive enabled + high-risk task: child inherits/uses paid main;
- per-task ACP override wins;
- child fallback chain includes remaining free models and paid fallback.

**Commands:**

```bash
PYTHONPATH=. ./venv/bin/python -m pytest tests/tools/test_delegate_tool_adaptive_routing.py -q -o 'addopts='
```

---

### Phase 7: Runtime integration for CLI/gateway/cron/one-shot

#### Task 7.1: Add shared runtime mutation helper

**Objective:** Avoid duplicating routing logic across entry points.

**Files:**

- Create or modify: `agent/adaptive_runtime.py`
- Modify: `cli.py`
- Modify: `cron/scheduler.py`
- Modify: `gateway/platforms/api_server.py` if needed
- Modify: `tui_gateway/server.py` if needed
- Test: relevant CLI/cron/gateway tests

**Function shape:**

```python
def apply_adaptive_route_to_runtime(
    *,
    source: str,
    prompt: str,
    config: dict,
    runtime: dict,
    requested_provider: str | None,
    requested_model: str | None,
    existing_fallback_chain: list[dict] | None,
) -> tuple[dict, list[dict], RouteDecision | None]:
    ...
```

**Rules:**

- All entry points call the same helper.
- If helper fails, log warning and preserve existing behavior.
- Include route/fallback in agent cache signature so cached agents do not keep stale route decisions.

---

### Phase 8: Error feedback loop

#### Task 8.1: Record outcomes and cooldowns

**Objective:** Update route state after success/failure.

**Files:**

- Modify: `agent/conversation_loop.py`
- Modify: `agent/agent_runtime_helpers.py` if fallback activation is centralized there
- Test: `tests/agent/test_adaptive_router_feedback.py`

**Behaviors:**

- record attempt immediately when route selected;
- on success, record token usage if available;
- on 429/quota/rate-limit, cooldown provider+model;
- on model-not-found, mark temporarily unavailable;
- on provider-wide quota error, cooldown provider wildcard if error clearly indicates account/provider-wide;
- do not mark task as failed when fallback succeeds.

**Commands:**

```bash
PYTHONPATH=. ./venv/bin/python -m pytest tests/agent/test_adaptive_router_feedback.py tests/run_agent/test_provider_fallback.py -q -o 'addopts='
```

---

### Phase 9: CLI and observability

#### Task 9.1: Add `hermes routing` CLI

**Objective:** Let users inspect routing decisions and state safely.

**Files:**

- Create: `hermes_cli/routing_cmd.py`
- Modify: `hermes_cli/main.py`
- Test: `tests/hermes_cli/test_routing_cmd.py`

**Commands:**

```bash
hermes routing status
hermes routing models
hermes routing cooldowns
hermes routing reset --model PROVIDER:MODEL
hermes routing explain --source delegation "summarize this file"
```

**Output must not include:**

- API keys;
- raw prompts unless user explicitly requests one-shot explain and it is not persisted;
- auth file paths;
- local home paths in docs/tests.

---

#### Task 9.2: Add verbose route logging

**Objective:** Log enough to debug routing without leaking secrets.

**Files:**

- Modify: `hermes_logging.py` or use existing loggers
- Modify: router modules
- Test: logging assertions where practical

Safe log fields:

```text
source, classification, selected_provider, selected_model, reasoning_effort,
skipped provider/model + reason, cooldown_until, fallback_count
```

---

### Phase 10: Documentation

#### Task 10.1: User docs

**Objective:** Explain feature setup safely.

**Files:**

- Create or modify: `website/docs/user-guide/features/adaptive-routing.md`
- Modify sidebar/nav if required

Include:

- what adaptive routing does;
- free-first delegation example;
- smart reasoning example;
- fallback behavior;
- privacy/security notes;
- provider quota caveats;
- ChatGPT/Codex quota opacity caveat;
- how to disable/rollback.

---

#### Task 10.2: Developer docs

**Objective:** Make upstream maintenance easy.

**Files:**

- Create: `website/docs/developer-guide/adaptive-routing.md`
- Add architecture diagram if appropriate

Include:

- module boundaries;
- state schema;
- classification rules;
- integration points;
- testing strategy;
- threat model.

---

### Phase 11: End-to-end validation

#### Task 11.1: Dry-run validation

**Objective:** Prove routing decisions without making LLM calls.

**Command examples:**

```bash
hermes routing explain --source delegation "summarize this README"
hermes routing explain --source delegation "rotate production database password"
```

Expected:

- summary task selects free/simple route;
- production password task selects paid/high-risk route.

---

#### Task 11.2: Live low-risk validation

**Objective:** Make one safe real request through adaptive delegation.

**Command:**

```bash
hermes chat -t delegation -q "Use delegate_task once to summarize what README files are for. Reply with ROUTE_OK if the child succeeds." --quiet
```

Expected:

- child succeeds;
- route state records selected free model;
- no secrets printed;
- fallback not used unless primary route fails.

---

#### Task 11.3: Simulated quota validation

**Objective:** Prove model rotation without burning real quota.

Approach:

- Unit-test state cooldown on first model.
- Planner should pick second model.
- Simulate all free models exhausted.
- Planner should pick paid/main if fallback policy allows.

Command:

```bash
PYTHONPATH=. ./venv/bin/python -m pytest tests/agent/test_adaptive_model_router.py::test_rotates_after_quota_cooldown -q -o 'addopts='
```

---

## 11. Acceptance Criteria

Feature is production-ready when:

- Adaptive routing is disabled by default and causes zero behavior change.
- Enabling for delegation routes low-risk subagents to configured free models.
- Quota/rate-limit errors cooldown only the affected provider+model unless provider-wide.
- Fallback chain tries remaining suitable free models before paid/main.
- High-risk/unknown tasks use paid/main.
- Smart reasoning maps task complexity to effort and respects manual overrides.
- Existing `fallback_providers` still works.
- Existing `delegation.provider/model` still works when adaptive routing is disabled.
- No secrets or raw prompts are persisted.
- Tests cover config, classification, state, routing, delegation, fallback feedback, and CLI explain/status.
- Docs clearly explain limitations, especially opaque ChatGPT/Codex quota.

---

## 12. Suggested Initial MVP

Build the smallest useful version first:

1. Config + state store.
2. Heuristic classifier.
3. Reasoning auto selector.
4. Delegation-only adaptive routing.
5. Fallback-chain generation.
6. Route status/explain CLI.
7. Docs.

Do not start with direct CLI/gateway routing. Delegation is the best first target because subagents are where cost/quota fan-out hurts most.

---

## 13. Example MVP Config

```yaml
adaptive_routing:
  enabled: true
  dry_run: false
  apply_to:
    delegation: true
    cli: false
    gateway: false
    cron: false
    one_shot: false
  default_policy: balanced
  reasoning:
    mode: auto
    default_effort: medium
    rules:
      trivial: minimal
      simple: low
      standard: medium
      complex: high
      high_risk: high
      unknown: high
  paid_fallback:
    provider: main
    model: ""
  models:
    - id: gemini-flash-lite-free
      provider: gemini
      model: gemini-2.5-flash-lite
      cost_class: free
      trust_tier: low_sensitive
      rpm_limit: 10
      rpd_limit: 500
      tpm_limit: 250000
      supports_tools: true
      supports_vision: true
      best_for: [trivial, simple, summarization, rewrite]
      avoid_for: [high_risk, secrets, production]

    - id: gemini-flash-free
      provider: gemini
      model: gemini-2.5-flash
      cost_class: free
      trust_tier: low_sensitive
      rpm_limit: 5
      rpd_limit: 20
      tpm_limit: 250000
      supports_tools: true
      supports_vision: true
      best_for: [simple, standard, code_explanation]
      avoid_for: [high_risk, secrets, production]
```

---

## 14. Rollback Plan

Immediate rollback:

```bash
hermes config set adaptive_routing.enabled false
```

If a specific model is causing issues:

```bash
hermes routing reset --model gemini:gemini-2.5-flash-lite
```

If the feature is removed from code:

- remove `adaptive_routing` from config or leave ignored;
- delete `$HERMES_HOME/adaptive-routing/state.db` if desired;
- existing `model`, `delegation`, and `fallback_providers` continue to work.

---

## 15. PR Strategy for Upstream

Recommended PR split:

1. PR 1: Config + state + classifier + unit tests.
2. PR 2: Router policy + fallback-chain adapter + unit tests.
3. PR 3: Delegation integration + tests.
4. PR 4: Smart reasoning auto mode + tests.
5. PR 5: CLI observability + docs.
6. PR 6: Optional CLI/gateway/cron expansion after MVP is stable.

Keep every PR generic:

- no personal usernames;
- no local filesystem paths;
- no private quota numbers unless they are public provider docs;
- no hard-coded provider keys;
- no assumptions about a specific subscription plan.

---

## 16. Open Questions

1. Should adaptive routing default to delegation-only for the first release?
2. Should `--provider free` be accepted before the full router is enabled, or only after `adaptive_routing.enabled`?
3. Should route state be in a new SQLite DB or in existing `state.db`?
4. Should prompt hashes be salted per Hermes home to avoid cross-user correlation?
5. Should model quality feedback be manual-only at first, or inferred from retry/fallback/validation failures?
6. Should route decisions appear in final response footers when `display.runtime_footer.enabled` is true?

---

## 17. Final Recommendation

Implement HARP in delegation-only mode first. That gives the biggest efficiency gain with the lowest risk:

```text
main agent = high-capability orchestrator
subagents = adaptive free/cheap models when safe
fallback = remaining free models, then paid/main
reasoning = auto based on task complexity
```

Once delegation routing is stable, extend the same shared helper to cron, one-shot, gateway, and direct CLI turns.
