---
title: Provider Routing
description: Configure OpenRouter provider preferences to optimize for cost, speed, or quality.
sidebar_label: Provider Routing
sidebar_position: 7
---

# Provider Routing

When using [OpenRouter](https://openrouter.ai) as your LLM provider, Hermes Agent supports **provider routing** — fine-grained control over which underlying AI providers handle your requests and how they're prioritized.

OpenRouter routes requests to many providers (e.g., Anthropic, Google, AWS Bedrock, Together AI). Provider routing lets you optimize for cost, speed, quality, or enforce specific provider requirements.

:::tip
Traffic routed through [Nous Portal](/integrations/nous-portal) still respects per-model routing and priority configs — and Portal subscribers get 10% off token-billed providers.
:::

## Configuration

Add a `provider_routing` section to your `~/.hermes/config.yaml`:

```yaml
provider_routing:
  sort: "price"           # How to rank providers
  only: []                # Whitelist: only use these providers
  ignore: []              # Blacklist: never use these providers
  order: []               # Explicit provider priority order
  require_parameters: false  # Only use providers that support all parameters
  data_collection: null   # Control data collection ("allow" or "deny")
```

:::info
Provider routing only applies when using OpenRouter. It has no effect with direct provider connections (e.g., connecting directly to the Anthropic API).
:::

## Options

### `sort`

Controls how OpenRouter ranks available providers for your request.

| Value | Description |
|-------|-------------|
| `"price"` | Cheapest provider first |
| `"throughput"` | Fastest tokens-per-second first |
| `"latency"` | Lowest time-to-first-token first |

```yaml
provider_routing:
  sort: "price"
```

### `only`

Whitelist of provider names. When set, **only** these providers will be used. All others are excluded.

```yaml
provider_routing:
  only:
    - "Anthropic"
    - "Google"
```

### `ignore`

Blacklist of provider names. These providers will **never** be used, even if they offer the cheapest or fastest option.

```yaml
provider_routing:
  ignore:
    - "Together"
    - "DeepInfra"
```

### `order`

Explicit priority order. Providers listed first are preferred. Unlisted providers are used as fallbacks.

```yaml
provider_routing:
  order:
    - "Anthropic"
    - "Google"
    - "AWS Bedrock"
```

### `require_parameters`

When `true`, OpenRouter will only route to providers that support **all** parameters in your request (like `temperature`, `top_p`, `tools`, etc.). This avoids silent parameter drops.

```yaml
provider_routing:
  require_parameters: true
```

### `data_collection`

Controls whether providers can use your prompts for training. Options are `"allow"` or `"deny"`.

```yaml
provider_routing:
  data_collection: "deny"
```

## Practical Examples

### Optimize for Cost

Route to the cheapest available provider. Good for high-volume usage and development:

```yaml
provider_routing:
  sort: "price"
```

### Optimize for Speed

Prioritize low-latency providers for interactive use:

```yaml
provider_routing:
  sort: "latency"
```

### Optimize for Throughput

Best for long-form generation where tokens-per-second matters:

```yaml
provider_routing:
  sort: "throughput"
```

### Lock to Specific Providers

Ensure all requests go through a specific provider for consistency:

```yaml
provider_routing:
  only:
    - "Anthropic"
```

### Avoid Specific Providers

Exclude providers you don't want to use (e.g., for data privacy):

```yaml
provider_routing:
  ignore:
    - "Together"
    - "Lepton"
  data_collection: "deny"
```

### Preferred Order with Fallbacks

Try your preferred providers first, fall back to others if unavailable:

```yaml
provider_routing:
  order:
    - "Anthropic"
    - "Google"
  require_parameters: true
```

## How It Works

Provider routing preferences are passed to the OpenRouter API via the `extra_body.provider` field on every API call. This applies to both:

- **CLI mode** — configured in `~/.hermes/config.yaml`, loaded at startup
- **Gateway mode** — same config file, loaded when the gateway starts

The routing config is read from `config.yaml` and passed as parameters when creating the `AIAgent`:

```
providers_allowed  ← from provider_routing.only
providers_ignored  ← from provider_routing.ignore
providers_order    ← from provider_routing.order
provider_sort      ← from provider_routing.sort
provider_require_parameters ← from provider_routing.require_parameters
provider_data_collection    ← from provider_routing.data_collection
```

:::tip
You can combine multiple options. For example, sort by price but exclude certain providers and require parameter support:

```yaml
provider_routing:
  sort: "price"
  ignore: ["Together"]
  require_parameters: true
  data_collection: "deny"
```
:::

## Default Behavior

When no `provider_routing` section is configured (the default), OpenRouter uses its own default routing logic, which generally balances cost and availability automatically.

:::tip Provider Routing vs. Fallback Models
Provider routing controls which **sub-providers within OpenRouter** handle your requests. For automatic failover to an entirely different provider when your primary model fails, see [Fallback Providers](/user-guide/features/fallback-providers).
:::

## Optional Universal HARP selector (gateway)

Hermes can optionally ask an external Universal HARP selector for a provider/model decision **before** normal gateway runtime resolution.

- Disabled by default (`harp_routing.enabled: false`)
- Applies to gateway runtime resolution
- Fail-open: if selector execution fails, Hermes falls back to normal provider resolution
- Runtime visibility: use `/harp-status` (gateway) for last decision + recent history
- Reset in-memory + persisted history: `/harp-status reset`
- Machine-readable output: `/harp-status --json`
- Bounded history views: `/harp-status --json --tail 50`
- Incremental polling: `/harp-status --json --since 1722880000`
- Cursor polling: `/harp-status --json --since-id <decision-or-audit-id>`
- Local signature validation helper: `/harp-verify --body '<raw-json>' --signature 'sha256=...' --secret '<key>'`
- File-based verify helper: `/harp-verify --body-file /tmp/payload.json --signature-file /tmp/sig.txt --secret-env HARP_SECRET`
- Header-file verify helper: `/harp-verify --body-file /tmp/payload.json --headers-file /tmp/headers.json --secret-env HARP_SECRET`
- Strict verify mode (signature + `sent_at` skew + nonce replay cache): add `--strict`
- Machine-readable verify output: add `--json`
- Include response schema metadata: add `--json-schema` (with `--json`)
  - JSON output includes `schema_id` and `changelog_url` for contract evolution tracking.
- Backend export: `GET /api/harp-status/export?format=json|csv`
- CSV export presets: `GET /api/harp-status/export?format=csv&columns=minimal|full`
- Metrics series: `GET /api/harp-status/metrics?window_hours=24&bucket=1m|5m|1h`
  - Response includes reliability summaries such as failure-streak `max` and `p95`, plus scoped windows (`last_1h`, `last_24h`).
  - Delta warning support: add `failed_delta_warning_threshold=<n>` for SLA-style warning flags.
  - Tiered severities: `failed_delta_info_threshold`, `failed_delta_warn_threshold`, `failed_delta_critical_threshold`.
  - Flap control: `severity_cooldown_seconds` + `severity_state_key` apply cooldown/hysteresis to severity downgrade transitions.
- Preflight lint: `GET /api/harp-status/lint` validates signing timeline/config before export requests.
  - Strict CI gate mode: `GET /api/harp-status/lint?strict=true` escalates warnings into failures.
- Lint history: `GET /api/harp-status/lint-history?tail=20`
  - Entries include compact `reason_codes` for trend analysis.
- Severity state reset: `POST /api/harp-status/severity-state/reset?severity_state_key=<key>` (omit key to reset all)
- Ops snapshot export: `GET /api/harp-status/ops-snapshot/export?format=json|csv&tail=50`
  - Includes export manifest/signature headers when signing is configured.
- Reset audit filters: `GET /api/harp-status/severity-reset-audit?tail=50&limit=50&sort=newest|oldest&cursor=<epoch>&cursor_token=<opaque>&actor=<tag>&allowed=true|false&since=<epoch>&viewer_tag=<tag>`
  - Response includes pagination metadata: `has_more`, `next_cursor_token`, and `total_estimate`.
- Reset audit stats: `GET /api/harp-status/severity-reset-audit/stats?window_hours=24&window_bucket=1m|5m|1h&actor=<tag>&actor_tag=<admin-tag>`
- Reset audit compaction/migration: `POST /api/harp-status/severity-reset-audit/compact?dry_run=true|false&actor_tag=<admin-tag>`
- Compaction audit timeline: `GET /api/harp-status/severity-reset-audit/compaction-audit?tail=20&actor_tag=<admin-tag>&trigger=auto|manual`
- Compaction drift alerts: `GET /api/harp-status/severity-reset-audit/compaction-alerts?tail=20&limit=20&sort=newest|oldest&cursor=<epoch>&cursor_token=<opaque>&actor_tag=<admin-tag>`
- Compaction webhook delivery audit: `GET /api/harp-status/severity-reset-audit/compaction-webhook-audit?tail=20&limit=20&sort=newest|oldest&cursor=<epoch>&cursor_token=<opaque>&actor_tag=<admin-tag>&sent=true|false&min_latency_ms=<n>&error_contains=<text>`
- Compaction export: `GET /api/harp-status/severity-reset-audit/export?stream=alerts|webhook|unmute|verify_unlock&format=json|csv&limit=200&sort=newest|oldest&cursor_token=<opaque>&actor_tag=<admin-tag>`
- Webhook unmute: `POST /api/harp-status/severity-reset-audit/webhook-unmute?actor_tag=<admin-tag>&reason=<text>`
- Webhook unmute audit: `GET /api/harp-status/severity-reset-audit/unmute-audit?tail=20&limit=20&sort_by=timestamp|actor_tag|reason&sort=newest|oldest&cursor_token=<opaque>&actor_tag=<admin-tag>&actor=<tag>&was_muted=true|false&reason_contains=<text>&since=<epoch>`
- Export page digest verification: `GET /api/harp-status/severity-reset-audit/verify-export-page-digest?stream=<...>&row_count=<n>&has_more=true|false&next_cursor=<epoch>&next_cursor_token=<opaque>&digest=sha256:<...>&issue_receipt=true&verifier_id=<id>&nonce=<nonce>`
  - When `issue_receipt=true`, successful verification returns a signed receipt payload (if ops signing secret is configured).
- Verification audit: `GET /api/harp-status/severity-reset-audit/verify-audit?tail=20&limit=20&sort=newest|oldest&cursor_token=<opaque>&actor_tag=<admin-tag>&verifier_id=<id>&since=<epoch>`
  - Includes aggregate duplicate-nonce metrics by stream (`nonce_duplicate_count_by_stream`).
- Verifier unlock: `POST /api/harp-status/severity-reset-audit/verify-verifier-unlock?actor_tag=<admin-tag>&verifier_id=<id>&reason=<text>`
- Verifier unlock audit: `GET /api/harp-status/severity-reset-audit/verify-verifier-unlock-audit?tail=20&limit=20&sort=newest|oldest&cursor_token=<opaque>&actor_tag=<admin-tag>&verifier_id=<id>&since=<epoch>`
- Verifier lock audit: `GET /api/harp-status/severity-reset-audit/verify-lock-audit?tail=20&limit=20&sort=newest|oldest&cursor_token=<opaque>&actor_tag=<admin-tag>&verifier_id=<id>&action=locked|unlocked&since=<epoch>`
- Verifier active-lock alerts timeline: `GET /api/harp-status/severity-reset-audit/verify-lock-alerts?tail=20&limit=20&sort=newest|oldest&cursor_token=<opaque>&actor_tag=<admin-tag>&active=true|false&since=<epoch>`
- Verifier active-lock alerts export: `GET /api/harp-status/severity-reset-audit/verify-lock-alerts/export?format=json|csv&tail=200&limit=200&sort=newest|oldest&cursor_token=<opaque>&actor_tag=<admin-tag>&active=true|false&since=<epoch>`
- Verify lock bundle export: `GET /api/harp-status/severity-reset-audit/verify-lock-bundle/export?format=json|csv&tail=200&actor_tag=<admin-tag>`
  - Stats/compact responses may include `compaction_health.warnings` such as `overdue`, `partitions_exceeded`, `rows_exceeded`.
  - Warning payloads include severity details (`code`, `severity`) and webhook delivery status metadata.
  - Compaction health includes webhook SLO summary (`success_rate`, `p95_latency_ms`, `failure_streak`) and windows (`all_time`, `last_1h`, `last_24h`).
  - Compaction health also includes anomaly flags (for example `p95_latency_spike`, `fast_fail_burst`, `success_rate_drop`).
  - Compaction health includes unmute counters (`unmute_count_24h`, `manual_unmute_rate`).
  - Compaction health includes top manual-unmute actors in the last 24h (`top_unmute_actors_24h`).
  - Verify audit lock summary includes trend windows (`lock_entries_windows`: 1h/24h/7d).
  - Verify audit lock summary includes `active_locks_alert_dwell_seconds` when active-lock alerting is enabled.
  - Verify audit lock summary includes `active_locks_alert_dwell_severity` (`none|warn|critical`) based on dwell thresholds.
  - JSON exports include `X-HARP-Reset-Audit-Page-Digest: sha256=<...>` for page metadata integrity.
  - If ops signing is enabled, stats/compact/compaction-audit responses include `X-HARP-Reset-Audit-Signature` (and optional `X-HARP-Reset-Audit-Key-Id`).
  - High-severity drift transitions (`partitions_exceeded` or `rows_exceeded`) can be forwarded to a webhook.

```yaml
harp_routing:
  enabled: true
  selector_script: /home/ubuntu/workspace/projects/universal-harp-engine/scripts/harp-select-route.py
  task: code_generation
  risk: standard
  timeout_seconds: 5
  history_size: 20
  history_max_age_days: 14
  auto_disable_failure_threshold: 5
  auto_disable_window_seconds: 300
  provider_cooldown_base_seconds: 0
  provider_penalties:
    openai-codex: 0
    openrouter: 60
  provider_penalty_decay: fixed  # fixed|linear|exponential
  alert_on_auto_disable: false
  alert_history_size: 50
  alert_webhook_url: ""
  alert_webhook_secret: ""
  alert_webhook_timeout_seconds: 5
  alert_webhook_max_retries: 2
  alert_webhook_max_skew_seconds: 300
  alert_export_signing_secret: ""  # optional; falls back to alert_webhook_secret
  alert_export_signing_key_id: ""  # optional; auto-derived from signing secret if empty
  alert_export_signing_key_version: "v1"
  alert_export_signing_key_deprecated: false
  alert_export_signing_not_before: ""   # ISO timestamp, optional
  alert_export_signing_sunset_at: ""    # ISO timestamp, optional
  severity_state_max_age_seconds: 86400
  severity_state_max_keys: 200
  lint_history_size: 100
  severity_reset_admin_tags: []      # optional allowlist for reset actor_tag
  severity_reset_audit_size: 200
  severity_reset_reason_deny_regex: ""  # optional regex to reject low-signal reset reasons
  severity_reset_allowed_reasons: []    # optional explicit reason taxonomy (allowlist)
  severity_reset_reason_redact_regex: ""  # optional regex redaction before ops snapshot export
  severity_reset_reason_privileged_tags: []  # viewer tags allowed to see unmasked audit reasons
  severity_reset_reason_partial_tags: []  # viewer tags allowed to see partial reason previews
  severity_reset_reason_preview_chars: 12  # preview length for partial visibility
  severity_reset_audit_retention_days: 30  # daily partition retention for reset-audit history
  severity_reset_cursor_signing_secret: ""  # optional HMAC secret for tamper-evident cursor_token
  severity_reset_auto_compact_enabled: false
  severity_reset_auto_compact_interval_seconds: 86400
  severity_reset_compaction_audit_size: 100
  severity_reset_auto_compact_actor_tag: "system-auto-compact"
  severity_reset_compaction_overdue_seconds: 0
  severity_reset_compaction_max_partitions: 0
  severity_reset_compaction_max_rows: 0
  severity_reset_compaction_alerts_size: 100
  severity_reset_compaction_alerts_retention_days: 30
  severity_reset_ops_signing_secret: ""
  severity_reset_ops_signing_key_id: ""
  severity_reset_compaction_alert_webhook_url: ""
  severity_reset_compaction_alert_webhook_secret: ""
  severity_reset_compaction_alert_webhook_timeout_seconds: 5
  severity_reset_compaction_alert_webhook_max_retries: 1
  severity_reset_compaction_alert_webhook_cooldown_seconds: 300
  severity_reset_compaction_webhook_audit_size: 100
  severity_reset_compaction_webhook_audit_retention_days: 30
  severity_reset_compaction_warning_severity_map:
    overdue: warn
    partitions_exceeded: critical
    rows_exceeded: critical
  severity_reset_compaction_anomaly_p95_multiplier: 1.5
  severity_reset_compaction_anomaly_min_attempts: 5
  severity_reset_compaction_anomaly_success_drop_delta: 0.2
  severity_reset_compaction_anomaly_fast_fail_min_failed: 3
  severity_reset_compaction_anomaly_fast_fail_max_success_rate: 0.5
  severity_reset_compaction_auto_backoff_enabled: false
  severity_reset_compaction_auto_backoff_trigger_count: 3
  severity_reset_compaction_auto_backoff_window_seconds: 1800
  severity_reset_compaction_auto_backoff_seconds: 600
  severity_reset_compaction_unmute_audit_size: 100
  severity_reset_compaction_backoff_notify_enabled: false
  severity_reset_compaction_backoff_notify_dedupe_seconds: 300
  severity_reset_unmute_reason_deny_regex: ""
  severity_reset_unmute_allowed_reasons: []
  severity_reset_unmute_reason_redact_regex: ""  # optional redaction for unmute reason in display/export
  severity_reset_top_unmute_actors_limit: 5
  severity_reset_verify_audit_size: 100
  severity_reset_actor_normalization_regex_map: {}  # optional regex->alias map applied during actor aggregates
  severity_reset_verify_nonce_window_seconds: 3600
  severity_reset_verify_nonce_cache_size: 1000
  severity_reset_verify_allowed_verifiers: []  # optional allowlist for verifier_id
  severity_reset_verifier_normalization_regex_map: {}  # optional regex->alias for verifier_id
  severity_reset_verify_nonce_alert_threshold: 0
  severity_reset_verify_nonce_alert_window_seconds: 600
  severity_reset_verify_nonce_alerts_size: 100
  severity_reset_verify_verifier_auto_lock_enabled: false
  severity_reset_verify_verifier_auto_lock_threshold: 5
  severity_reset_verify_verifier_auto_lock_window_seconds: 3600
  severity_reset_verify_verifier_lock_seconds: 1800
  severity_reset_verify_unlock_audit_size: 100
  severity_reset_verify_unlock_allowed_reasons: []
  severity_reset_verify_unlock_reason_deny_regex: ""
  severity_reset_verify_lock_notify_enabled: false
  severity_reset_verify_lock_notify_dedupe_seconds: 300
  severity_reset_verify_lock_notify_audit_size: 200
  severity_reset_verify_auto_unlock_notify_suppression_seconds: 300
  severity_reset_verify_active_locks_alert_threshold: 0
  severity_reset_verify_active_locks_alerts_size: 100
  severity_reset_verify_active_locks_alert_dwell_warn_seconds: 300
  severity_reset_verify_active_locks_alert_dwell_critical_seconds: 1800
  severity_reset_verify_nonce_event_history_seconds: 86400
  severity_reset_verify_nonce_event_history_size: 5000
  severity_reset_verify_lock_audit_size: 500
  auto_reenable_cooldown_seconds: 0
  auto_reenable_min_clean_decisions: 10
```

Expected selector output contract:

```text
PROVIDER: <provider-id>
MODEL: <model-id>
```

If either line is missing, or the script exits non-zero/timeouts, Hermes ignores the selector result and continues with the existing runtime/fallback flow.

`provider_penalty_decay` controls how repeated failures increase per-provider cooldown:
- `fixed`: always use `provider_cooldown_base_seconds + provider_penalties[provider]`
- `linear`: multiply the provider penalty by consecutive failure streak
- `exponential`: double the provider penalty for each additional consecutive failure

When `alert_on_auto_disable` is enabled, Hermes now keeps a persisted alert audit trail in the HARP status store and includes it in `/harp-status --json`.
Critical alerts can also be forwarded to an external webhook (`alert_webhook_url`) with retry metadata and a stable `audit_id` per alert.
If `alert_webhook_secret` is set, Hermes signs the JSON payload with `HMAC-SHA256` and sends `X-HARP-Signature: sha256=<hex>` plus `X-HARP-Audit-Id`.
Webhook payloads also include replay-protection fields (`nonce`, `sent_at`) so receivers can reject duplicates or stale deliveries.
`alert_webhook_max_skew_seconds` is included in payload/header as the sender's expected tolerance (`max_skew_seconds`, `X-HARP-Max-Skew-Seconds`).

Receiver verification checklist:
1. Recompute HMAC-SHA256 over the exact raw request body using `alert_webhook_secret`; compare with `X-HARP-Signature`.
2. Reject payloads where `sent_at` is older than your acceptable skew window (for example, 5 minutes).
3. Store seen `nonce` values for a short TTL and reject duplicates to block replay.

Export manifests:
- `/api/harp-status/export` now includes `X-HARP-Export-Generated-At` and `X-HARP-Export-Checksum-SHA256`.
- If `alert_export_signing_secret` (or fallback `alert_webhook_secret`) is set, it also includes `X-HARP-Export-Signature: sha256=<hmac(generated_at:checksum)>`.
- Per-environment override: set `HARP_EXPORT_SIGNING_SECRET` to override config at runtime.
- Signed exports include key metadata header: `X-HARP-Export-Key-Id` (from `alert_export_signing_key_id` or derived fingerprint).
- Signed exports also include `X-HARP-Export-Key-Alg` and `X-HARP-Export-Key-Version` for key lifecycle policy checks.
- Signed exports include deprecation state header: `X-HARP-Export-Key-Deprecated: true|false`.
- Signed exports may include timeline metadata headers: `X-HARP-Export-Key-Not-Before`, `X-HARP-Export-Key-Sunset-At`.
- Timeline consistency is enforced: export returns `400` if `sunset_at < not_before`.

Key rotation playbook (example):
1. Introduce a new signing secret and set `alert_export_signing_key_version` to the new version while keeping old verifier trust.
2. Mark previous key as deprecated (`alert_export_signing_key_deprecated: true`) and monitor consumers for successful migration.
3. Remove old trust once all consumers accept the new `Key-Version`/`Key-Id`.

Python verifier snippet:

```python
import hashlib, hmac

def verify_harp_webhook(raw_body: bytes, headers: dict, secret: str) -> bool:
    provided = (headers.get("X-HARP-Signature") or "").strip()
    if not provided.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)
```

Node.js verifier snippet:

```js
import crypto from "node:crypto";

export function verifyHarpWebhook(rawBody, signatureHeader, secret) {
  if (!signatureHeader?.startsWith("sha256=")) return false;
  const digest = crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
  const expected = `sha256=${digest}`;
  return crypto.timingSafeEqual(Buffer.from(signatureHeader), Buffer.from(expected));
}
```

### Troubleshooting (`harp_routing`)

If HARP routing is enabled but not applied, Hermes should fail open and continue normally.

Common cases:

1. **Selector path is wrong**
   - Symptom: no selector decision applied
   - Action: verify `harp_routing.selector_script` points to an existing `.py` file

2. **Selector timed out**
   - Symptom: decision is skipped for that resolution attempt
   - Action: increase `harp_routing.timeout_seconds` (for example `5` → `10`)

3. **Selector exited non-zero**
   - Symptom: decision is skipped and normal runtime resolution continues
   - Action: run the selector manually and fix the underlying error:
     ```bash
     python3 /path/to/harp-select-route.py --task code_generation --risk standard
     ```

4. **Output contract mismatch**
   - Symptom: script runs but decision is ignored
   - Action: ensure stdout includes both lines exactly once:
     - `PROVIDER: <provider-id>`
     - `MODEL: <model-id>`

5. **Provider credential resolution fails after selector decision**
   - Symptom: selected provider cannot be resolved in Hermes
   - Action: authenticate/configure that provider (`hermes auth`) or keep using fallback providers until creds are valid.

### Canary rollout checklist (`harp_routing`)

Use an explicit staged rollout:

1. Start with `harp_routing.enabled: false` and validate baseline behavior.
2. Enable `harp_routing.enabled: true` on a low-risk gateway profile only.
3. Monitor `/status` output for `HARP routing: applied (...)` and verify provider/model choices.
4. If selector behavior is unexpected, disable immediately:

```yaml
harp_routing:
  enabled: false
```

5. Keep fallback providers configured so fail-open/failover remains available during rollout.
6. If you enable auto-reenable, choose conservative values and monitor `/harp-status` before broad rollout.

### Log signal examples

When selector decisions apply:

```text
HARP routing selected provider=openai-codex model=gpt-5.5 for session=...
```

When selector provider resolution fails and Hermes falls back:

```text
HARP routing decision failed provider resolution (provider=openai-codex): ...
```

When auto-disable triggers (critical):

```text
Auto-disabled harp_routing after repeated failures
```

When auto-reenable triggers after cooldown (warning):

```text
Auto-reenabled harp_routing after clean cooldown window
```
