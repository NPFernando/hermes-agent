import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  Brain,
  Check,
  Clock,
  Copy,
  Cpu,
  Database,
  Download,
  Globe,
  HardDrive,
  KeyRound,
  Link2,
  Play,
  Plus,
  Power,
  RotateCw,
  Server,
  Share2,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  Terminal,
  Trash2,
  X,
} from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { H2 } from "@nous-research/ui/ui/components/typography/h2";
import { Card, CardContent } from "@nous-research/ui/ui/components/card";
import { Input } from "@nous-research/ui/ui/components/input";
import { Label } from "@nous-research/ui/ui/components/label";
import { Select, SelectOption } from "@nous-research/ui/ui/components/select";
import { Toast } from "@nous-research/ui/ui/components/toast";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { useConfirmDelete } from "@nous-research/ui/hooks/use-confirm-delete";
import { ConfirmDialog } from "@nous-research/ui/ui/components/confirm-dialog";
import { useModalBehavior } from "@/hooks/useModalBehavior";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import { cn, themedBody } from "@/lib/utils";
import { api } from "@/lib/api";
import type {
  StatusResponse,
  MemoryStatus,
  CredentialPoolProvider,
  CheckpointsResponse,
  HooksResponse,
  HookEntry,
  SystemStats,
  UpdateCheckResponse,
  CuratorStatus,
  PortalStatus,
  DebugShareResponse,
  HarpStatusResponse,
  HarpStatusMetricsResponse,
  HarpStatusLintResponse,
  HarpSeverityResetAuditStatsResponse,
} from "@/lib/api";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function formatDuration(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function sparkline(values: number[]): string {
  if (!values.length) return "";
  const ticks = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (max <= min) return values.map(() => "▅").join("");
  return values
    .map((v) => {
      const idx = Math.max(0, Math.min(ticks.length - 1, Math.round(((v - min) / (max - min)) * (ticks.length - 1))));
      return ticks[idx];
    })
    .join("");
}

function lockAlertSeverityTone(severity?: string): "destructive" | "warning" | "secondary" {
  if (severity === "critical") return "destructive";
  if (severity === "warn") return "warning";
  return "secondary";
}

/**
 * Live action-log viewer for the spawn-based admin actions (doctor, audit,
 * backup, import, skills update, checkpoints prune, gateway start/stop).
 * Polls /api/actions/<name>/status until the process exits.
 */
function ActionLogViewer({
  action,
  onClose,
}: {
  action: string;
  onClose: () => void;
}) {
  const [lines, setLines] = useState<string[]>([]);
  const [running, setRunning] = useState(true);
  const [exitCode, setExitCode] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const st = await api.getActionStatus(action, 400);
        if (cancelled) return;
        setLines(st.lines);
        setRunning(st.running);
        setExitCode(st.exit_code);
        if (st.running) timer.current = setTimeout(poll, 1200);
      } catch {
        if (!cancelled) setRunning(false);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [action]);

  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-muted-foreground" />
            <span className="font-mono text-sm">{action}</span>
            {running ? (
              <Badge tone="warning">running</Badge>
            ) : (
              <Badge tone={exitCode === 0 ? "success" : "destructive"}>
                {exitCode === 0 ? "done" : `exit ${exitCode}`}
              </Badge>
            )}
          </div>
          <Button ghost size="icon" onClick={onClose} aria-label="Close log">
            <X />
          </Button>
        </div>
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words bg-background/50 border border-border p-3 text-xs font-mono text-muted-foreground">
          {lines.length ? lines.join("\n") : "Starting…"}
        </pre>
      </CardContent>
    </Card>
  );
}

const HOOK_EVENTS_FALLBACK = [
  "pre_tool_call",
  "post_tool_call",
  "pre_llm_call",
  "post_llm_call",
  "on_session_start",
  "on_session_end",
];

export default function SystemPage() {
  const { toast, showToast } = useToast();

  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [memory, setMemory] = useState<MemoryStatus | null>(null);
  const [pool, setPool] = useState<CredentialPoolProvider[]>([]);
  const [checkpoints, setCheckpoints] = useState<CheckpointsResponse | null>(
    null,
  );
  const [hooks, setHooks] = useState<HooksResponse | null>(null);
  const [curator, setCurator] = useState<CuratorStatus | null>(null);
  const [portal, setPortal] = useState<PortalStatus | null>(null);
  const [harpStatus, setHarpStatus] = useState<HarpStatusResponse | null>(null);
  const [harpMetrics, setHarpMetrics] = useState<HarpStatusMetricsResponse | null>(null);
  const [harpLint, setHarpLint] = useState<HarpStatusLintResponse | null>(null);
  const [harpLintHistoryCount, setHarpLintHistoryCount] = useState(0);
  const [harpResetAudit, setHarpResetAudit] = useState<
    Array<{
      audit_id?: string;
      timestamp: number;
      allowed: boolean;
      actor_tag: string;
      reason: string;
      scope: string;
      key: string;
      removed: number;
      deny_reason_hit?: boolean;
      reason_masked?: boolean;
    }>
  >([]);
  const [harpUnmuteWasMutedFilter, setHarpUnmuteWasMutedFilter] = useState("all");
  const [harpUnmuteReasonFilter, setHarpUnmuteReasonFilter] = useState("");
  const [harpUnmuteSortBy, setHarpUnmuteSortBy] = useState<"timestamp" | "actor_tag" | "reason">("timestamp");
  const [harpResetAuditCursorToken, setHarpResetAuditCursorToken] = useState<string | null>(null);
  const [harpResetAuditHasMore, setHarpResetAuditHasMore] = useState(false);
  const [harpResetAuditReasonVisibility, setHarpResetAuditReasonVisibility] =
    useState<"full" | "partial" | "masked">("full");
  const [harpResetAuditStats, setHarpResetAuditStats] =
    useState<HarpSeverityResetAuditStatsResponse | null>(null);
  const [harpCompactingAudit, setHarpCompactingAudit] = useState(false);
  const [harpCompactionAudit, setHarpCompactionAudit] = useState<
    Array<{
      timestamp: number;
      trigger: string;
      actor_tag: string;
      before: number;
      after: number;
      partitions: number;
    }>
  >([]);
  const [harpCompactionAlerts, setHarpCompactionAlerts] = useState<
    Array<{
      timestamp: number;
      warnings: string[];
      warning_details?: Array<{ code: string; severity: string }>;
      rows: number;
      partitions: number;
      last_compact_ts?: number;
      high_severity?: boolean;
      previous_warnings?: string[];
    }>
  >([]);
  const [harpCompactionWebhookAudit, setHarpCompactionWebhookAudit] = useState<
    Array<{
      timestamp: number;
      warnings: string[];
      attempts: number;
      sent: boolean;
      last_error: string;
      latency_ms?: number | null;
    }>
  >([]);
  const [harpUnmuteAudit, setHarpUnmuteAudit] = useState<
    Array<{
      timestamp: number;
      actor_tag: string;
      reason: string;
      was_muted: boolean;
      previous_muted_until?: number | null;
    }>
  >([]);
  const [harpVerifyAudit, setHarpVerifyAudit] = useState<
    Array<{
      timestamp: number;
      actor_tag: string;
      ok: boolean;
      stream: string;
      verifier_id?: string;
      nonce?: string;
    }>
  >([]);
  const [harpVerifyNonceDuplicateCount, setHarpVerifyNonceDuplicateCount] = useState(0);
  const [harpVerifyNonceDuplicateByStream, setHarpVerifyNonceDuplicateByStream] = useState<Record<string, number>>(
    {},
  );
  const [harpVerifyActiveLocks, setHarpVerifyActiveLocks] = useState<Record<string, number>>({});
  const [harpVerifyLockSummary, setHarpVerifyLockSummary] = useState<{
    locked_verifier_count: number;
    soonest_unlock_at?: number | null;
    lock_entries_24h: number;
    lock_entries_windows?: {
      last_1h: number;
      last_24h: number;
      last_7d: number;
    };
    active_locks_alert?: boolean;
    active_locks_threshold?: number;
    active_locks_alert_dwell_seconds?: number;
    active_locks_alert_dwell_severity?: "none" | "warn" | "critical" | string;
  } | null>(null);
  const [harpVerifyLockNotifyMetrics, setHarpVerifyLockNotifyMetrics] = useState<{
    attempted: number;
    sent: number;
    failed: number;
    success_rate: number;
    p95_latency_ms?: number | null;
    windows?: {
      last_1h: {
        attempted: number;
        sent: number;
        failed: number;
        success_rate: number;
        p95_latency_ms?: number | null;
      };
      last_24h: {
        attempted: number;
        sent: number;
        failed: number;
        success_rate: number;
        p95_latency_ms?: number | null;
      };
    };
  } | null>(null);
  const [harpVerifyLockAlerts, setHarpVerifyLockAlerts] = useState<
    Array<{
      timestamp: number;
      active: boolean;
      locked_verifier_count: number;
      threshold: number;
    }>
  >([]);
  const [harpVerifyDuplicateHeatmap, setHarpVerifyDuplicateHeatmap] = useState<
    Record<string, { last_10m: number; last_1h: number; last_24h: number }>
  >({});
  const [harpVerifierUnlockAudit, setHarpVerifierUnlockAudit] = useState<
    Array<{
      timestamp: number;
      actor_tag: string;
      verifier_id: string;
      reason: string;
      was_locked: boolean;
      previous_locked_until?: number | null;
    }>
  >([]);
  const [harpVerifierUnlockId, setHarpVerifierUnlockId] = useState("");
  const [harpVerifyLockAudit, setHarpVerifyLockAudit] = useState<
    Array<{ timestamp: number; action: string; verifier_id: string; locked_until?: number | null }>
  >([]);
  const [harpVerifyLockBundleFormat, setHarpVerifyLockBundleFormat] = useState<"json" | "csv">("json");
  const [harpVerifyLockAlertsExportFormat, setHarpVerifyLockAlertsExportFormat] = useState<"json" | "csv">("json");
  const [harpVerifyLockAlertsActiveFilter, setHarpVerifyLockAlertsActiveFilter] = useState("all");
  const [harpCompactionActorFilter, setHarpCompactionActorFilter] = useState("ops-admin");
  const [harpCompactionTriggerFilter, setHarpCompactionTriggerFilter] = useState("all");
  const [harpCompactionSinceWindow, setHarpCompactionSinceWindow] = useState("24h");
  const [harpWebhookStatusFilter, setHarpWebhookStatusFilter] = useState("all");
  const [harpWebhookLatencyMinFilter, setHarpWebhookLatencyMinFilter] = useState("");
  const [harpWebhookErrorFilter, setHarpWebhookErrorFilter] = useState("");
  const [harpCompactionExportStream, setHarpCompactionExportStream] = useState<
    "alerts" | "webhook" | "unmute" | "verify_unlock"
  >(
    "alerts",
  );
  const [harpCompactionExportFormat, setHarpCompactionExportFormat] = useState<"json" | "csv">("json");
  const backoffTransitionRef = useRef<string>("");
  const [harpAuditActorFilter, setHarpAuditActorFilter] = useState("");
  const [harpAuditAllowedFilter, setHarpAuditAllowedFilter] = useState("all");
  const [harpAuditKeyFilter, setHarpAuditKeyFilter] = useState("");
  const [harpAuditSinceWindow, setHarpAuditSinceWindow] = useState("all");
  const [harpAuditSort, setHarpAuditSort] = useState<"newest" | "oldest">("newest");
  const [harpSeverityFilter, setHarpSeverityFilter] = useState("all");
  const [harpClock, setHarpClock] = useState(() => Date.now());
  const [harpTail, setHarpTail] = useState("20");
  const [harpAutoRefresh, setHarpAutoRefresh] = useState(true);
  const [harpCursor, setHarpCursor] = useState<string>("");
  const [harpCsvColumns, setHarpCsvColumns] = useState<"minimal" | "full">("full");
  const harpCursorRef = useRef<string>("");
  const harpStatusRef = useRef<HarpStatusResponse | null>(null);
  const harpResetAuditCursorTokenRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [activeAction, setActiveAction] = useState<string | null>(null);

  // Add-credential form.
  const [credProvider, setCredProvider] = useState("openrouter");
  const [credKey, setCredKey] = useState("");
  const [credLabel, setCredLabel] = useState("");
  const [addingCred, setAddingCred] = useState(false);

  const [importPath, setImportPath] = useState("");
  // Restore-from-backup is destructive (overwrites the live config) and the
  // spawned `hermes import` runs non-interactively (stdin is /dev/null), so
  // its CLI "Continue? [y/N]" prompt would auto-abort. The dashboard owns the
  // consent: confirm here, then call the endpoint with force=true.
  const [importConfirmOpen, setImportConfirmOpen] = useState(false);

  // Create-hook modal.
  const [hookModalOpen, setHookModalOpen] = useState(false);
  const closeHookModal = useCallback(() => setHookModalOpen(false), []);
  const hookModalRef = useModalBehavior({
    open: hookModalOpen,
    onClose: closeHookModal,
  });
  const [hookEvent, setHookEvent] = useState("pre_tool_call");
  const [hookCommand, setHookCommand] = useState("");
  const [hookMatcher, setHookMatcher] = useState("");
  const [hookTimeout, setHookTimeout] = useState("");
  const [hookApprove, setHookApprove] = useState(true);
  const [creatingHook, setCreatingHook] = useState(false);

  // ── Update check ───────────────────────────────────────────────────
  const [updateInfo, setUpdateInfo] = useState<UpdateCheckResponse | null>(
    null,
  );
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [updateConfirmOpen, setUpdateConfirmOpen] = useState(false);

  const loadAll = useCallback(() => {
    Promise.allSettled([
      api.getStatus(),
      api.getSystemStats(),
      api.getMemory(),
      api.getCredentialPool(),
      api.getCheckpoints(),
      api.getHooks(),
      api.getCurator(),
      api.getPortal(),
      // Cached (non-forced) check so the version row shows update status on
      // load without a separate effect / a forced network round-trip.
      api.checkHermesUpdate(false),
    ])
      .then(([s, st, m, p, c, h, cur, prt, upd]) => {
        if (s.status === "fulfilled") setStatus(s.value);
        if (st.status === "fulfilled") setStats(st.value);
        if (m.status === "fulfilled") setMemory(m.value);
        if (p.status === "fulfilled") setPool(p.value.providers);
        if (c.status === "fulfilled") setCheckpoints(c.value);
        if (h.status === "fulfilled") setHooks(h.value);
        if (cur.status === "fulfilled") setCurator(cur.value);
        if (prt.status === "fulfilled") setPortal(prt.value);
        if (upd.status === "fulfilled") setUpdateInfo(upd.value);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    harpCursorRef.current = harpCursor;
  }, [harpCursor]);

  useEffect(() => {
    harpStatusRef.current = harpStatus;
  }, [harpStatus]);

  useEffect(() => {
    harpResetAuditCursorTokenRef.current = harpResetAuditCursorToken;
  }, [harpResetAuditCursorToken]);

  const loadHarpResetAudit = useCallback(
    (append = false) => {
      const now = Date.now() / 1000;
      const sinceMap: Record<string, number> = {
        "1h": now - 3600,
        "24h": now - 86400,
        "7d": now - 604800,
      };
      const compactionSinceMap: Record<string, number> = {
        "1h": now - 3600,
        "24h": now - 86400,
        "7d": now - 604800,
      };
      const windowHoursMap: Record<string, number> = {
        "1h": 1,
        "24h": 24,
        "7d": 168,
      };
      const bucketMap: Record<string, "1m" | "5m" | "1h"> = {
        "1h": "1m",
        "24h": "5m",
        "7d": "1h",
      };
      const allowedFilter =
        harpAuditAllowedFilter === "allowed"
          ? true
          : harpAuditAllowedFilter === "denied"
            ? false
            : undefined;
      api
        .getHarpSeverityResetAudit(20, {
          sort: harpAuditSort,
          viewerTag: "dashboard",
          limit: 20,
          actor: harpAuditActorFilter.trim() || undefined,
          allowed: allowedFilter,
          since: sinceMap[harpAuditSinceWindow],
          cursorToken: append ? harpResetAuditCursorTokenRef.current ?? undefined : undefined,
        })
        .then((data) => {
          setHarpResetAuditReasonVisibility(data.reason_visibility ?? "full");
          setHarpResetAuditCursorToken(data.next_cursor_token ?? null);
          setHarpResetAuditHasMore(Boolean(data.has_more ?? data.next_cursor_token));
          if (!append) {
            setHarpResetAudit(data.audit);
            return;
          }
          setHarpResetAudit((prev) => {
            const seen = new Set(
              prev.map(
                (row) =>
                  row.audit_id ??
                  `${row.timestamp}-${row.actor_tag}-${row.scope}-${row.key}-${row.removed}`,
              ),
            );
            const merged = [...prev];
            for (const row of data.audit) {
              const key =
                row.audit_id ??
                `${row.timestamp}-${row.actor_tag}-${row.scope}-${row.key}-${row.removed}`;
              if (seen.has(key)) continue;
              seen.add(key);
              merged.push(row);
            }
            return merged;
          });
        })
        .catch(() => {});
      api
        .getHarpSeverityResetAuditStats(
          windowHoursMap[harpAuditSinceWindow] ?? 24,
          harpAuditActorFilter.trim() || undefined,
          {
            actorTag: "ops-admin",
            windowBucket: bucketMap[harpAuditSinceWindow] ?? "1h",
          },
        )
        .then((stats) => {
          setHarpResetAuditStats(stats);
          const transition = stats.compaction_health?.backoff_transition;
          if (transition?.timestamp) {
            const key = `${transition.timestamp}:${transition.from}->${transition.to}`;
            if (backoffTransitionRef.current !== key) {
              backoffTransitionRef.current = key;
              showToast(
                transition.to === "muted"
                  ? "Compaction webhook entered auto-backoff mute"
                  : "Compaction webhook exited backoff mute",
                transition.to === "muted" ? "error" : "success",
              );
            }
          }
        })
        .catch(() => {});
      api
        .getHarpSeverityResetCompactionAudit(10, {
          actorTag: harpCompactionActorFilter.trim() || "ops-admin",
          trigger:
            harpCompactionTriggerFilter === "all"
              ? undefined
              : (harpCompactionTriggerFilter as "auto" | "manual"),
          since: compactionSinceMap[harpCompactionSinceWindow],
        })
        .then((data) => setHarpCompactionAudit(data.audit))
        .catch(() => {});
      api
        .getHarpSeverityResetCompactionAlerts(10, {
          actorTag: harpCompactionActorFilter.trim() || "ops-admin",
          since: compactionSinceMap[harpCompactionSinceWindow],
        })
        .then((data) => setHarpCompactionAlerts(data.alerts))
        .catch(() => {});
      api
        .getHarpSeverityResetCompactionWebhookAudit(10, {
          actorTag: harpCompactionActorFilter.trim() || "ops-admin",
          since: compactionSinceMap[harpCompactionSinceWindow],
          sent:
            harpWebhookStatusFilter === "sent"
              ? true
              : harpWebhookStatusFilter === "failed"
                ? false
                : undefined,
          minLatencyMs: harpWebhookLatencyMinFilter.trim()
            ? Number.parseInt(harpWebhookLatencyMinFilter.trim(), 10)
            : undefined,
          errorContains: harpWebhookErrorFilter.trim() || undefined,
        })
        .then((data) => setHarpCompactionWebhookAudit(data.audit))
        .catch(() => {});
      api
        .getHarpSeverityResetUnmuteAudit(10, {
          actorTag: harpCompactionActorFilter.trim() || "ops-admin",
          since: compactionSinceMap[harpCompactionSinceWindow],
          wasMuted:
            harpUnmuteWasMutedFilter === "true"
              ? true
              : harpUnmuteWasMutedFilter === "false"
                ? false
                : undefined,
          reasonContains: harpUnmuteReasonFilter.trim() || undefined,
          sortBy: harpUnmuteSortBy,
        })
        .then((data) => setHarpUnmuteAudit(data.audit))
        .catch(() => {});
      api
        .getHarpSeverityResetVerifyAudit(10, {
          actorTag: harpCompactionActorFilter.trim() || "ops-admin",
          since: compactionSinceMap[harpCompactionSinceWindow],
          limit: 10,
          sort: "newest",
        })
        .then((data) => {
          setHarpVerifyAudit(data.audit);
          setHarpVerifyNonceDuplicateCount(data.nonce_duplicate_count || 0);
          setHarpVerifyNonceDuplicateByStream(data.nonce_duplicate_count_by_stream || {});
          setHarpVerifyActiveLocks(data.active_verifier_locks || {});
          setHarpVerifyDuplicateHeatmap(data.duplicate_heatmap || {});
          setHarpVerifyLockSummary(data.lock_summary || null);
          setHarpVerifyLockNotifyMetrics(data.lock_notify_metrics || null);
        })
        .catch(() => {});
      api
        .getHarpSeverityResetVerifyUnlockAudit(10, {
          actorTag: harpCompactionActorFilter.trim() || "ops-admin",
          since: compactionSinceMap[harpCompactionSinceWindow],
          limit: 10,
          sort: "newest",
        })
        .then((data) => setHarpVerifierUnlockAudit(data.audit))
        .catch(() => {});
      api
        .getHarpSeverityResetVerifyLockAudit(10, {
          actorTag: harpCompactionActorFilter.trim() || "ops-admin",
          since: compactionSinceMap[harpCompactionSinceWindow],
          limit: 10,
          sort: "newest",
        })
        .then((data) => setHarpVerifyLockAudit(data.audit))
        .catch(() => {});
      api
        .getHarpSeverityResetVerifyLockAlerts(10, {
          actorTag: harpCompactionActorFilter.trim() || "ops-admin",
          active:
            harpVerifyLockAlertsActiveFilter === "on"
              ? true
              : harpVerifyLockAlertsActiveFilter === "off"
                ? false
                : undefined,
          since: compactionSinceMap[harpCompactionSinceWindow],
          limit: 10,
          sort: "newest",
        })
        .then((data) => setHarpVerifyLockAlerts(data.alerts || []))
        .catch(() => {});
    },
    [
      harpAuditSort,
      harpAuditActorFilter,
      harpAuditAllowedFilter,
      harpAuditSinceWindow,
      harpCompactionActorFilter,
      harpCompactionTriggerFilter,
      harpCompactionSinceWindow,
      harpWebhookStatusFilter,
      harpWebhookLatencyMinFilter,
      harpWebhookErrorFilter,
      harpUnmuteWasMutedFilter,
      harpUnmuteReasonFilter,
      harpUnmuteSortBy,
      harpVerifyLockAlertsActiveFilter,
      showToast,
    ],
  );

  const loadHarpStatus = useCallback((incremental = false) => {
    const tail = Number.parseInt(harpTail, 10);
    const safeTail = Number.isFinite(tail) ? Math.max(1, Math.min(200, tail)) : 20;
    const sinceId = incremental && harpCursorRef.current ? harpCursorRef.current : undefined;
    api
      .getHarpStatus({
        tail: safeTail,
        sinceId,
        severity: harpSeverityFilter,
      })
      .then((data) => {
        const prev = harpStatusRef.current;
        if (incremental && prev) {
          const history = [...prev.history, ...data.history].slice(-safeTail);
          const alerts = [...prev.alerts, ...data.alerts].slice(-safeTail);
          setHarpStatus({ ...data, history, alerts });
        } else {
          setHarpStatus(data);
        }
        if (data.next_since_id) {
          setHarpCursor(data.next_since_id);
          harpCursorRef.current = data.next_since_id;
        }
      })
      .catch(() => {});
    api
      .getHarpStatusMetrics(24, "1h", 1, 1, 1, 2, 300, "dashboard-main")
      .then((data) => setHarpMetrics(data))
      .catch(() => {});
    api
      .getHarpStatusLint(false)
      .then((data) => setHarpLint(data))
      .catch(() => {});
    api
      .getHarpStatusLintHistory(10)
      .then((data) => setHarpLintHistoryCount(data.history.length))
      .catch(() => {});
  }, [harpTail, harpSeverityFilter]);

  useEffect(() => {
    harpCursorRef.current = "";
    loadHarpStatus(false);
  }, [harpTail, harpSeverityFilter, loadHarpStatus]);

  useEffect(() => {
    const timer = window.setInterval(() => setHarpClock(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    loadHarpResetAudit(false);
  }, [
    loadHarpResetAudit,
    harpAuditSort,
    harpAuditActorFilter,
    harpAuditAllowedFilter,
    harpAuditSinceWindow,
    harpCompactionActorFilter,
    harpCompactionTriggerFilter,
    harpCompactionSinceWindow,
    harpWebhookStatusFilter,
    harpWebhookLatencyMinFilter,
    harpWebhookErrorFilter,
    harpUnmuteWasMutedFilter,
    harpUnmuteReasonFilter,
    harpUnmuteSortBy,
  ]);

  useEffect(() => {
    if (!harpAutoRefresh) return;
    const timer = setInterval(() => {
      loadHarpStatus(true);
    }, 5000);
    return () => clearInterval(timer);
  }, [harpAutoRefresh, loadHarpStatus]);

  // ── Gateway lifecycle ──────────────────────────────────────────────
  const runGateway = async (verb: "start" | "stop" | "restart") => {
    try {
      if (verb === "start") {
        await api.startGateway();
        setActiveAction("gateway-start");
      } else if (verb === "stop") {
        await api.stopGateway();
        setActiveAction("gateway-stop");
      } else {
        await api.restartGateway();
        setActiveAction("gateway-restart");
      }
      showToast(`Gateway ${verb} started`, "success");
      setTimeout(loadAll, 3000);
      setTimeout(loadHarpStatus, 3000);
    } catch (e) {
      showToast(`Gateway ${verb} failed: ${e}`, "error");
    }
  };

  const unmuteCompactionWebhook = async () => {
    try {
      await api.unmuteHarpSeverityResetWebhook(harpCompactionActorFilter.trim() || "ops-admin", "manual-unmute");
      showToast("Compaction webhook unmuted", "success");
      loadHarpResetAudit(false);
    } catch (e) {
      showToast(`Webhook unmute failed: ${e}`, "error");
    }
  };

  const unlockVerifier = async () => {
    if (!harpVerifierUnlockId.trim()) return;
    try {
      await api.unlockHarpSeverityResetVerifier(
        harpCompactionActorFilter.trim() || "ops-admin",
        harpVerifierUnlockId.trim(),
        "manual-unlock",
      );
      showToast("Verifier unlocked", "success");
      loadHarpResetAudit(false);
    } catch (e) {
      showToast(`Verifier unlock failed: ${e}`, "error");
    }
  };

  const downloadVerifyLockBundle = async () => {
    try {
      const result = await api.getHarpSeverityResetVerifyLockBundleExport(
        harpVerifyLockBundleFormat,
        200,
        harpCompactionActorFilter.trim() || "ops-admin",
      );
      if (harpVerifyLockBundleFormat === "json") {
        const data = result as { json: unknown };
        const blob = new Blob([JSON.stringify(data.json, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "harp-verify-lock-bundle.json";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } else {
        const data = result as { blob: Blob; filename: string };
        const url = URL.createObjectURL(data.blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = data.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (e) {
      showToast(`Verify lock bundle export failed: ${e}`, "error");
    }
  };

  const compactResetAudit = async () => {
    try {
      setHarpCompactingAudit(true);
      const result = await api.compactHarpSeverityResetAudit(false, "ops-admin");
      showToast(
        `Audit compacted (${result.before} → ${result.after}, ${result.partitions} partitions)`,
        "success",
      );
      loadHarpResetAudit(false);
    } catch (e) {
      showToast(`Audit compact failed: ${e}`, "error");
    } finally {
      setHarpCompactingAudit(false);
    }
  };

  const downloadCompactionExport = async () => {
    try {
      const now = Date.now() / 1000;
      const sinceMap: Record<string, number> = {
        "1h": now - 3600,
        "24h": now - 86400,
        "7d": now - 604800,
      };

      const sentFilter =
        harpWebhookStatusFilter === "sent"
          ? true
          : harpWebhookStatusFilter === "failed"
            ? false
            : undefined;
      const result = await api.getHarpSeverityResetCompactionExport({
        stream: harpCompactionExportStream,
        format: harpCompactionExportFormat,
        limit: 200,
        sort: "newest",
        actorTag: harpCompactionActorFilter.trim() || "ops-admin",
        verifierId:
          harpCompactionExportStream === "verify_unlock" && harpVerifierUnlockId.trim()
            ? harpVerifierUnlockId.trim()
            : undefined,
        since: sinceMap[harpCompactionSinceWindow],
        sent: sentFilter,
        minLatencyMs: harpWebhookLatencyMinFilter.trim()
          ? Number.parseInt(harpWebhookLatencyMinFilter.trim(), 10)
          : undefined,
        errorContains: harpWebhookErrorFilter.trim() || undefined,
      });
      if (harpCompactionExportFormat === "csv") {
        const csv = result as { blob: Blob; filename: string };
        const url = URL.createObjectURL(csv.blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = csv.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        return;
      }
      const jsonPayload = result as { json: unknown };
      const blob = new Blob([JSON.stringify(jsonPayload.json, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `harp-compaction-${harpCompactionExportStream}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      showToast(`Compaction export failed: ${e}`, "error");
    }
  };

  const downloadVerifyLockAlerts = async () => {
    try {
      const now = Date.now() / 1000;
      const sinceMap: Record<string, number> = {
        "1h": now - 3600,
        "24h": now - 86400,
        "7d": now - 604800,
      };
      const result = await api.getHarpSeverityResetVerifyLockAlertsExport({
        format: harpVerifyLockAlertsExportFormat,
        tail: 200,
        limit: 200,
        sort: "newest",
        actorTag: harpCompactionActorFilter.trim() || "ops-admin",
        active:
          harpVerifyLockAlertsActiveFilter === "on"
            ? true
            : harpVerifyLockAlertsActiveFilter === "off"
              ? false
              : undefined,
        since: sinceMap[harpCompactionSinceWindow],
      });
      if (harpVerifyLockAlertsExportFormat === "json") {
        const data = result as { json: unknown };
        const blob = new Blob([JSON.stringify(data.json, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "harp-verify-lock-alerts.json";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        return;
      }
      const data = result as { blob: Blob; filename: string };
      const url = URL.createObjectURL(data.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      showToast(`Verify lock alerts export failed: ${e}`, "error");
    }
  };

  const downloadHarpExport = async (format: "json" | "csv") => {
    try {
      const tail = Number.parseInt(harpTail, 10);
      const safeTail = Number.isFinite(tail) ? Math.max(1, Math.min(200, tail)) : 20;
      const result = await api.getHarpStatusExport({
        format,
        columns: format === "csv" ? harpCsvColumns : undefined,
        tail: safeTail,
        severity: harpSeverityFilter,
      });
      const url = URL.createObjectURL(result.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = result.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      showToast(`HARP export failed: ${e}`, "error");
    }
  };

  // ── Curator ────────────────────────────────────────────────────────
  const toggleCuratorPaused = async () => {
    if (!curator) return;
    try {
      await api.setCuratorPaused(!curator.paused);
      showToast(curator.paused ? "Curator resumed" : "Curator paused", "success");
      loadAll();
    } catch (e) {
      showToast(`Curator toggle failed: ${e}`, "error");
    }
  };

  // ── Memory ─────────────────────────────────────────────────────────
  // Memory provider selection lives on the /plugins page now (see the
  // read-only display + link below); the dropdown was intentionally
  // dropped from this card during the admin-panel refresh.
  const memoryReset = useConfirmDelete({
    onDelete: useCallback(
      async (target: string) => {
        try {
          const res = await api.resetMemory(
            target as "all" | "memory" | "user",
          );
          showToast(`Reset: ${res.deleted.join(", ") || "nothing"}`, "success");
          loadAll();
        } catch (e) {
          showToast(`Reset failed: ${e}`, "error");
          throw e;
        }
      },
      [loadAll, showToast],
    ),
  });

  // ── Credential pool ────────────────────────────────────────────────
  const addCredential = async () => {
    if (!credProvider.trim() || !credKey.trim()) {
      showToast("Provider and API key required", "error");
      return;
    }
    setAddingCred(true);
    try {
      await api.addCredentialPoolEntry(
        credProvider.trim(),
        credKey.trim(),
        credLabel.trim() || undefined,
      );
      showToast("Credential added", "success");
      setCredKey("");
      setCredLabel("");
      loadAll();
    } catch (e) {
      showToast(`Failed to add credential: ${e}`, "error");
    } finally {
      setAddingCred(false);
    }
  };

  const credDelete = useConfirmDelete({
    onDelete: useCallback(
      async (key: string) => {
        const [provider, idxStr] = key.split("|");
        try {
          await api.removeCredentialPoolEntry(provider, Number(idxStr));
          showToast("Credential removed", "success");
          loadAll();
        } catch (e) {
          showToast(`Failed to remove: ${e}`, "error");
          throw e;
        }
      },
      [loadAll, showToast],
    ),
  });

  // ── Operations ─────────────────────────────────────────────────────
  const runOp = async (fn: () => Promise<{ name: string }>, label: string) => {
    try {
      const res = await fn();
      setActiveAction(res.name);
      showToast(`${label} started`, "success");
    } catch (e) {
      showToast(`${label} failed: ${e}`, "error");
    }
  };

  // ── Debug share ────────────────────────────────────────────────────
  // Unlike the fire-and-forget ops above, `debug share` produces shareable
  // paste URLs that are the whole point — so we surface them as real,
  // copyable links rather than a log tail.
  const [shareRedact, setShareRedact] = useState(true);
  const [sharing, setSharing] = useState(false);
  const [shareResult, setShareResult] = useState<DebugShareResponse | null>(
    null,
  );
  const [copiedLabel, setCopiedLabel] = useState<string | null>(null);

  const copyToClipboard = useCallback(
    async (text: string, label: string) => {
      try {
        await navigator.clipboard.writeText(text);
        setCopiedLabel(label);
        setTimeout(
          () => setCopiedLabel((cur) => (cur === label ? null : cur)),
          1500,
        );
      } catch {
        showToast("Couldn't copy to clipboard", "error");
      }
    },
    [showToast],
  );

  const runDebugShare = useCallback(async () => {
    setSharing(true);
    setShareResult(null);
    try {
      const res = await api.runDebugShare({ redact: shareRedact });
      setShareResult(res);
      const n = Object.keys(res.urls).length;
      showToast(
        `Uploaded ${n} paste${n === 1 ? "" : "s"}${
          res.redacted ? " (redacted)" : ""
        }`,
        "success",
      );
    } catch (e) {
      showToast(`Debug share failed: ${e}`, "error");
    } finally {
      setSharing(false);
    }
  }, [shareRedact, showToast]);


  // ── Update check / apply ───────────────────────────────────────────
  const checkForUpdate = useCallback(
    async (force = false) => {
      setCheckingUpdate(true);
      try {
        const info = await api.checkHermesUpdate(force);
        setUpdateInfo(info);
        if (force) {
          if (info.update_available) {
            showToast(
              info.behind && info.behind > 0
                ? `Update available — ${info.behind} commit${info.behind === 1 ? "" : "s"} behind`
                : "Update available",
              "success",
            );
          } else if (info.behind === 0) {
            showToast("You're on the latest version", "success");
          } else if (info.message) {
            showToast(info.message, "error");
          }
        }
      } catch (e) {
        showToast(`Update check failed: ${e}`, "error");
      } finally {
        setCheckingUpdate(false);
      }
    },
    [showToast],
  );

  // Auto-check (cached) runs inside loadAll on mount; this is the
  // user-triggered forced re-check from the "Check for updates" button.
  const applyUpdate = async () => {
    setUpdateConfirmOpen(false);
    try {
      const resp = await api.updateHermes();
      if (!resp.ok && resp.error === "docker_update_unsupported") {
        showToast(
          resp.message ??
            "Updates don't apply inside Docker — re-pull the image instead.",
          "error",
        );
        return;
      }
      setActiveAction(resp.name ?? "hermes-update");
      showToast("Update started", "success");
    } catch (e) {
      showToast(`Update failed: ${e}`, "error");
    }
  };

  const checkpointsPrune = useConfirmDelete({
    onDelete: useCallback(async () => {
      try {
        const res = await api.pruneCheckpoints();
        setActiveAction(res.name);
        showToast("Checkpoint prune started", "success");
      } catch (e) {
        showToast(`Prune failed: ${e}`, "error");
        throw e;
      }
    }, [showToast]),
  });

  // ── Hooks ──────────────────────────────────────────────────────────
  const createHook = async () => {
    if (!hookCommand.trim()) {
      showToast("Command is required", "error");
      return;
    }
    setCreatingHook(true);
    try {
      await api.createHook({
        event: hookEvent,
        command: hookCommand.trim(),
        matcher: hookMatcher.trim() || undefined,
        timeout: hookTimeout.trim() ? Number(hookTimeout) : undefined,
        approve: hookApprove,
      });
      showToast("Hook created", "success");
      setHookCommand("");
      setHookMatcher("");
      setHookTimeout("");
      setHookModalOpen(false);
      loadAll();
    } catch (e) {
      showToast(`Failed to create hook: ${e}`, "error");
    } finally {
      setCreatingHook(false);
    }
  };

  const hookDelete = useConfirmDelete({
    onDelete: useCallback(
      async (key: string) => {
        const sep = key.indexOf("|");
        const event = key.slice(0, sep);
        const command = key.slice(sep + 1);
        try {
          await api.deleteHook(event, command);
          showToast("Hook removed", "success");
          loadAll();
        } catch (e) {
          showToast(`Failed to remove hook: ${e}`, "error");
          throw e;
        }
      },
      [loadAll, showToast],
    ),
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner className="text-2xl text-primary" />
      </div>
    );
  }

  const gatewayRunning = status?.gateway_running;
  const validEvents = hooks?.valid_events?.length
    ? hooks.valid_events
    : HOOK_EVENTS_FALLBACK;

  return (
    <div className="flex flex-col gap-8">
      <Toast toast={toast} />

      <ConfirmDialog
        open={updateConfirmOpen}
        onCancel={() => setUpdateConfirmOpen(false)}
        onConfirm={() => void applyUpdate()}
        title="Update Hermes?"
        description={
          updateInfo && updateInfo.behind && updateInfo.behind > 0
            ? `This will run 'hermes update' (${updateInfo.update_command}) and pull ${updateInfo.behind} new commit${updateInfo.behind === 1 ? "" : "s"}. The gateway restarts when the update finishes; the current session keeps its prompt cache until then.`
            : `This will run 'hermes update' (${updateInfo?.update_command ?? "hermes update"}) and restart the gateway when it finishes.`
        }
        confirmLabel="Update now"
      />

      <DeleteConfirmDialog
        open={memoryReset.isOpen}
        onCancel={memoryReset.cancel}
        onConfirm={memoryReset.confirm}
        title="Reset memory"
        description="This permanently erases the selected built-in memory files. This cannot be undone."
        loading={memoryReset.isDeleting}
      />
      <DeleteConfirmDialog
        open={credDelete.isOpen}
        onCancel={credDelete.cancel}
        onConfirm={credDelete.confirm}
        title="Remove credential"
        description="Remove this pooled API key? The agent will no longer rotate through it."
        loading={credDelete.isDeleting}
      />
      <DeleteConfirmDialog
        open={checkpointsPrune.isOpen}
        onCancel={checkpointsPrune.cancel}
        onConfirm={checkpointsPrune.confirm}
        title="Prune checkpoints"
        description="Delete the rollback checkpoint shadow store? Existing /rollback points will be lost."
        loading={checkpointsPrune.isDeleting}
      />
      <DeleteConfirmDialog
        open={hookDelete.isOpen}
        onCancel={hookDelete.cancel}
        onConfirm={hookDelete.confirm}
        title="Remove shell hook"
        description="Remove this hook from config and revoke its consent? It stops firing on the next restart."
        loading={hookDelete.isDeleting}
      />

      {/* Create-hook modal */}
      {hookModalOpen && (
        <div
          ref={hookModalRef}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-background/85 backdrop-blur-sm p-4"
          onClick={(e) => e.target === e.currentTarget && setHookModalOpen(false)}
          role="dialog"
          aria-modal="true"
        >
          <div className={cn(themedBody, "relative w-full max-w-lg border border-border bg-card shadow-2xl flex flex-col")}>
            <Button
              ghost
              size="icon"
              onClick={() => setHookModalOpen(false)}
              className="absolute right-2 top-2 text-muted-foreground hover:text-foreground"
              aria-label="Close"
            >
              <X />
            </Button>
            <header className="p-5 pb-3 border-b border-border">
              <h2 className="font-mondwest text-display text-base tracking-wider">
                New shell hook
              </h2>
            </header>
            <div className="p-5 grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="hook-event">Event</Label>
                <Select
                  id="hook-event"
                  value={hookEvent}
                  onValueChange={(v) => setHookEvent(v)}
                >
                  {validEvents.map((ev) => (
                    <SelectOption key={ev} value={ev}>
                      {ev}
                    </SelectOption>
                  ))}
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="hook-command">Command (absolute path)</Label>
                <Input
                  id="hook-command"
                  autoFocus
                  placeholder="/usr/local/bin/my-hook.sh"
                  value={hookCommand}
                  onChange={(e) => setHookCommand(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="hook-matcher">Matcher (optional)</Label>
                  <Input
                    id="hook-matcher"
                    placeholder="e.g. terminal"
                    value={hookMatcher}
                    onChange={(e) => setHookMatcher(e.target.value)}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="hook-timeout">Timeout (s)</Label>
                  <Input
                    id="hook-timeout"
                    placeholder="10"
                    value={hookTimeout}
                    onChange={(e) => setHookTimeout(e.target.value)}
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input
                  type="checkbox"
                  checked={hookApprove}
                  onChange={(e) => setHookApprove(e.target.checked)}
                />
                Approve now (grant consent so it fires; otherwise it stays
                configured but inactive)
              </label>
              <p className="text-xs text-warning">
                Shell hooks run arbitrary commands on this host. Only add scripts
                you trust. Takes effect on the next gateway/session restart.
              </p>
              <div className="flex justify-end">
                <Button
                  className="uppercase"
                  size="sm"
                  onClick={createHook}
                  disabled={creatingHook}
                  prefix={creatingHook ? <Spinner /> : undefined}
                >
                  {creatingHook ? "Creating" : "Create hook"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Live action log */}
      {activeAction && (
        <ActionLogViewer
          action={activeAction}
          onClose={() => setActiveAction(null)}
        />
      )}

      {/* ── Host / system stats ───────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <Server className="h-4 w-4" /> Host
        </H2>
        <Card>
          <CardContent className="py-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-y-3 gap-x-6 text-sm">
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground">OS</div>
                <div>{stats?.os} {stats?.os_release}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground">Arch</div>
                <div>{stats?.arch}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground">Host</div>
                <div className="truncate">{stats?.hostname}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground">Python</div>
                <div>{stats?.python_impl} {stats?.python_version}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground">Hermes</div>
                <div className="flex items-center gap-2">
                  <span>v{stats?.hermes_version}</span>
                  {updateInfo &&
                    (updateInfo.update_available ? (
                      <Badge tone="warning">
                        {updateInfo.behind && updateInfo.behind > 0
                          ? `${updateInfo.behind} behind`
                          : "update available"}
                      </Badge>
                    ) : updateInfo.behind === 0 ? (
                      <Badge tone="success">latest</Badge>
                    ) : null)}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                  <Cpu className="h-3 w-3" /> CPU
                </div>
                <div>
                  {stats?.cpu_count ?? "—"} cores
                  {typeof stats?.cpu_percent === "number"
                    ? ` · ${stats.cpu_percent.toFixed(0)}%`
                    : ""}
                </div>
              </div>
              {stats?.memory && (
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">Memory</div>
                  <div>
                    {formatBytes(stats.memory.used)} / {formatBytes(stats.memory.total)} ({stats.memory.percent}%)
                  </div>
                </div>
              )}
              {stats?.disk && (
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                    <HardDrive className="h-3 w-3" /> Disk
                  </div>
                  <div>
                    {formatBytes(stats.disk.used)} / {formatBytes(stats.disk.total)} ({stats.disk.percent}%)
                  </div>
                </div>
              )}
              {typeof stats?.uptime_seconds === "number" && (
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">Uptime</div>
                  <div>{formatDuration(stats.uptime_seconds)}</div>
                </div>
              )}
              {stats?.load_avg && stats.load_avg.length >= 3 && (
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">Load avg</div>
                  <div>{stats.load_avg.map((n) => n.toFixed(2)).join(" / ")}</div>
                </div>
              )}
            </div>
            {stats && !stats.psutil && (
              <p className="mt-3 text-xs text-muted-foreground">
                Install the <span className="font-mono">psutil</span> extra for
                CPU / memory / disk metrics.
              </p>
            )}
            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-4">
              <Button
                size="sm"
                ghost
                disabled={checkingUpdate}
                prefix={
                  checkingUpdate ? (
                    <Spinner className="h-3.5 w-3.5" />
                  ) : (
                    <RotateCw className="h-3.5 w-3.5" />
                  )
                }
                onClick={() => void checkForUpdate(true)}
              >
                Check for updates
              </Button>
              {updateInfo?.update_available && updateInfo.can_apply && (
                <Button
                  size="sm"
                  prefix={<Download className="h-3.5 w-3.5" />}
                  onClick={() => setUpdateConfirmOpen(true)}
                >
                  Update now
                </Button>
              )}
              {updateInfo &&
                !updateInfo.can_apply &&
                updateInfo.update_available && (
                  <span className="text-xs text-muted-foreground">
                    Update with{" "}
                    <span className="font-mono">{updateInfo.update_command}</span>
                  </span>
                )}
              {updateInfo?.message && !updateInfo.update_available && (
                <span className="text-xs text-muted-foreground">
                  {updateInfo.message}
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      </section>

      {/* ── Portal ────────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <Globe className="h-4 w-4" /> Nous Portal
        </H2>
        <Card>
          <CardContent className="flex flex-col gap-3 py-4">
            <div className="flex items-center gap-3">
              <Badge tone={portal?.logged_in ? "success" : "secondary"}>
                {portal?.logged_in ? "logged in" : "not logged in"}
              </Badge>
              {portal?.provider && (
                <span className="text-sm text-muted-foreground">
                  inference provider: {portal.provider}
                </span>
              )}
              <a
                href={portal?.subscription_url || "https://portal.nousresearch.com/manage-subscription"}
                target="_blank"
                rel="noreferrer"
                className="ml-auto text-xs text-primary underline"
              >
                Manage subscription
              </a>
            </div>
            {portal?.features && portal.features.length > 0 && (
              <div className="flex flex-col gap-1 border-t border-border pt-3">
                <span className="text-xs uppercase tracking-wider text-muted-foreground">
                  Tool Gateway routing
                </span>
                {portal.features.map((f) => (
                  <div key={f.label} className="flex items-center justify-between text-sm">
                    <span>{f.label}</span>
                    <span className="text-muted-foreground">{f.state}</span>
                  </div>
                ))}
              </div>
            )}
            {!portal?.logged_in && (
              <p className="text-xs text-muted-foreground">
                Log in with <span className="font-mono">hermes portal</span>.
              </p>
            )}
          </CardContent>
        </Card>
      </section>

      {/* ── Curator ───────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <Sparkles className="h-4 w-4" /> Skill curator
        </H2>
        <Card>
          <CardContent className="flex items-center justify-between py-4">
            <div className="flex items-center gap-3">
              <Badge tone={curator?.paused ? "warning" : curator?.enabled ? "success" : "secondary"}>
                {curator?.paused ? "paused" : curator?.enabled ? "active" : "disabled"}
              </Badge>
              <span className="text-sm text-muted-foreground">
                {curator?.interval_hours ? `every ${curator.interval_hours}h` : ""}
                {curator?.last_run_at ? ` · last run ${new Date(curator.last_run_at).toLocaleString()}` : " · never run"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" ghost onClick={toggleCuratorPaused}>
                {curator?.paused ? "Resume" : "Pause"}
              </Button>
              <Button
                size="sm"
                ghost
                prefix={<Play className="h-3.5 w-3.5" />}
                onClick={() => runOp(api.runCurator, "Curator review")}
              >
                Run now
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-3 py-4">
            <div className="flex flex-wrap items-center gap-3">
              <Badge tone={harpStatus?.enabled ? "success" : "secondary"}>
                {harpStatus?.enabled ? "HARP enabled" : "HARP disabled"}
              </Badge>
              <span className="text-sm text-muted-foreground">
                state: {harpStatus?.status?.state ?? "unknown"}
                {harpStatus?.status?.provider ? ` · ${harpStatus.status.provider}` : ""}
                {harpStatus?.status?.model ? `/${harpStatus.status.model}` : ""}
              </span>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="grid gap-2">
                <Label htmlFor="harp-severity-filter">Alert severity</Label>
                <Select
                  id="harp-severity-filter"
                  value={harpSeverityFilter}
                  onValueChange={(v) => {
                    setHarpSeverityFilter(v);
                    setHarpCursor("");
                    harpCursorRef.current = "";
                  }}
                >
                  <SelectOption value="all">all</SelectOption>
                  <SelectOption value="warning">warning</SelectOption>
                  <SelectOption value="critical">critical</SelectOption>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="harp-tail">Rows</Label>
                <Input
                  id="harp-tail"
                  value={harpTail}
                  onChange={(e) => {
                    setHarpTail(e.target.value);
                    setHarpCursor("");
                    harpCursorRef.current = "";
                  }}
                  placeholder="20"
                />
              </div>
              <div className="flex items-end">
                <Button size="sm" ghost onClick={() => loadHarpStatus()}>
                  Refresh HARP
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="grid gap-2">
                <Label htmlFor="harp-csv-columns">CSV columns</Label>
                <Select
                  id="harp-csv-columns"
                  value={harpCsvColumns}
                  onValueChange={(v) => setHarpCsvColumns(v as "minimal" | "full")}
                >
                  <SelectOption value="full">full</SelectOption>
                  <SelectOption value="minimal">minimal</SelectOption>
                </Select>
              </div>
              <div className="flex items-end sm:col-span-2">
                <span className="text-xs text-muted-foreground font-mono">
                  webhook attempted={harpStatus?.webhook_metrics?.attempted ?? 0} · sent={harpStatus?.webhook_metrics?.sent ?? 0} · failed={harpStatus?.webhook_metrics?.failed ?? 0} · success={(harpStatus?.webhook_metrics?.success_ratio ?? 0).toFixed(2)}
                  {" · 1h="}
                  {(harpStatus?.webhook_metrics?.windows?.last_1h?.success_ratio ?? 0).toFixed(2)}
                  {" · 24h="}
                  {(harpStatus?.webhook_metrics?.windows?.last_24h?.success_ratio ?? 0).toFixed(2)}
                </span>
              </div>
            </div>

            <div className="rounded border border-border p-3">
              <div className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
                Lint + severity state
              </div>
              <div className="space-y-1 text-xs font-mono text-muted-foreground">
                <div>
                  lint_ok={String(harpLint?.ok ?? false)} issues={harpLint?.issues?.length ?? 0} warnings={harpLint?.warnings?.length ?? 0}
                </div>
                <div>
                  state_key={harpMetrics?.reliability?.deltas?.last_1h_vs_prev_1h?.severity_state_key ?? "dashboard-main"} severity={harpMetrics?.reliability?.deltas?.last_1h_vs_prev_1h?.severity ?? "none"} raw={harpMetrics?.reliability?.deltas?.last_1h_vs_prev_1h?.severity_raw ?? "none"}
                </div>
                <div>lint_history_entries={harpLintHistoryCount}</div>
                <div className="pt-1">
                  <Button
                    size="sm"
                    ghost
                    onClick={() =>
                      api
                        .resetHarpSeverityState(
                          "dashboard-main",
                          "dashboard",
                          "manual-reset-from-system-page",
                        )
                        .then(() => loadHarpStatus(false))
                        .catch(() => {})
                    }
                  >
                    Reset severity state
                  </Button>
                </div>
              </div>
            </div>

            <div className="rounded border border-border p-3">
              <div className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
                Severity reset audit
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-4">
                <Input
                  value={harpAuditActorFilter}
                  onChange={(e) => setHarpAuditActorFilter(e.target.value)}
                  placeholder="actor (exact)"
                />
                <Select
                  value={harpAuditAllowedFilter}
                  onValueChange={(v) => setHarpAuditAllowedFilter(v)}
                >
                  <SelectOption value="all">all</SelectOption>
                  <SelectOption value="allowed">allowed</SelectOption>
                  <SelectOption value="denied">denied</SelectOption>
                </Select>
                <Input
                  value={harpAuditKeyFilter}
                  onChange={(e) => setHarpAuditKeyFilter(e.target.value)}
                  placeholder="filter key"
                />
                <Select
                  value={harpAuditSinceWindow}
                  onValueChange={(v) => setHarpAuditSinceWindow(v)}
                >
                  <SelectOption value="all">all time</SelectOption>
                  <SelectOption value="1h">last 1h</SelectOption>
                  <SelectOption value="24h">last 24h</SelectOption>
                  <SelectOption value="7d">last 7d</SelectOption>
                </Select>
              </div>
              <div className="mb-2 w-48">
                <Select
                  value={harpAuditSort}
                  onValueChange={(v) => setHarpAuditSort(v as "newest" | "oldest")}
                >
                  <SelectOption value="newest">newest</SelectOption>
                  <SelectOption value="oldest">oldest</SelectOption>
                </Select>
              </div>
              <div className="mb-2 flex items-center gap-2">
                <Badge tone="secondary">reason visibility: {harpResetAuditReasonVisibility}</Badge>
                {harpResetAuditStats?.compaction_health && (
                  <Badge
                    tone={
                      (harpResetAuditStats.compaction_health.active_warning_count || 0) > 0
                        ? "warning"
                        : "success"
                    }
                  >
                    active warnings {harpResetAuditStats.compaction_health.active_warning_count || 0}
                  </Badge>
                )}
                {harpResetAuditStats?.compaction_health?.last_webhook_delivery && (
                  <Badge
                    tone={
                      harpResetAuditStats.compaction_health.last_webhook_delivery.sent
                        ? "success"
                        : harpResetAuditStats.compaction_health.last_webhook_delivery.skipped_cooldown
                          ? "secondary"
                          : "warning"
                    }
                  >
                    webhook{" "}
                    {harpResetAuditStats.compaction_health.last_webhook_delivery.sent
                      ? "sent"
                      : harpResetAuditStats.compaction_health.last_webhook_delivery.skipped_cooldown
                        ? "cooldown"
                        : "not sent"}
                  </Badge>
                )}
                {harpResetAuditStats?.compaction_health?.webhook_slo_anomalies &&
                  harpResetAuditStats.compaction_health.webhook_slo_anomalies.length > 0 && (
                    <Badge tone="warning">
                      anomalies {harpResetAuditStats.compaction_health.webhook_slo_anomalies.join(",")}
                    </Badge>
                  )}
                {harpResetAuditStats?.compaction_health?.webhook_muted_until &&
                  harpResetAuditStats.compaction_health.webhook_muted_until * 1000 > harpClock && (
                    <Badge tone="destructive">
                      webhook muted until{" "}
                      {new Date(harpResetAuditStats.compaction_health.webhook_muted_until * 1000).toLocaleTimeString()}
                    </Badge>
                  )}
                <Button
                  size="sm"
                  ghost
                  disabled={!harpResetAuditHasMore}
                  onClick={() => loadHarpResetAudit(true)}
                >
                  Load more
                </Button>
                <Button size="sm" ghost disabled={harpCompactingAudit} onClick={compactResetAudit}>
                  {harpCompactingAudit ? "Compacting…" : "Compact audit"}
                </Button>
                <Button size="sm" ghost onClick={unmuteCompactionWebhook}>
                  Unmute webhook
                </Button>
              </div>
              {harpResetAuditStats && (
                <div className="mb-2 text-xs text-muted-foreground">
                  total={harpResetAuditStats.totals.total} · allowed={harpResetAuditStats.totals.allowed} · denied=
                  {harpResetAuditStats.totals.denied} · unique actors={harpResetAuditStats.totals.unique_actors} ·
                  buckets={harpResetAuditStats.series?.length ?? 0}
                  {harpResetAuditStats.compaction_health?.warnings?.length
                    ? ` · compaction warnings=${harpResetAuditStats.compaction_health.warnings.join(",")}`
                    : ""}
                  {harpResetAuditStats.compaction_health?.webhook_slo
                    ? ` · webhook success=${Math.round((harpResetAuditStats.compaction_health.webhook_slo.success_rate || 0) * 100)}% · p95=${harpResetAuditStats.compaction_health.webhook_slo.p95_latency_ms ?? "-"}ms · streak=${harpResetAuditStats.compaction_health.webhook_slo.failure_streak ?? 0}`
                    : ""}
                  {harpResetAuditStats.compaction_health?.webhook_slo_windows
                    ? ` · success(1h/24h)=${Math.round((harpResetAuditStats.compaction_health.webhook_slo_windows.last_1h.success_rate || 0) * 100)}%/${Math.round((harpResetAuditStats.compaction_health.webhook_slo_windows.last_24h.success_rate || 0) * 100)}%`
                    : ""}
                  {typeof harpResetAuditStats.compaction_health?.unmute_count_24h === "number"
                    ? ` · unmute24h=${harpResetAuditStats.compaction_health.unmute_count_24h} · unmute_rate=${Math.round((harpResetAuditStats.compaction_health.manual_unmute_rate || 0) * 100)}%`
                    : ""}
                </div>
              )}
              {harpResetAuditStats?.compaction_health?.webhook_slo_windows && (
                <div className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-2 text-xs">
                  <div className="rounded border border-border p-2">
                    <div className="text-muted-foreground">Webhook success-rate trend (1h,24h,all)</div>
                    <div className="font-mono">
                      {sparkline([
                        (harpResetAuditStats.compaction_health.webhook_slo_windows.last_1h.success_rate || 0) * 100,
                        (harpResetAuditStats.compaction_health.webhook_slo_windows.last_24h.success_rate || 0) * 100,
                        (harpResetAuditStats.compaction_health.webhook_slo_windows.all_time.success_rate || 0) * 100,
                      ])}{" "}
                      {Math.round(
                        (harpResetAuditStats.compaction_health.webhook_slo_windows.last_1h.success_rate || 0) * 100,
                      )}
                      {harpResetAuditStats?.compaction_health?.webhook_anomaly_state && (
                        <div className="mb-2 text-xs text-muted-foreground">
                          {Object.entries(harpResetAuditStats.compaction_health.webhook_anomaly_state).map(([code, info]) => (
                            <span key={code} className="mr-3">
                              {code}: count={info.count} first={new Date(info.first_seen * 1000).toLocaleTimeString()} last=
                              {new Date(info.last_seen * 1000).toLocaleTimeString()}
                            </span>
                          ))}
                        </div>
                      )}
                      % /
                      {Math.round(
                        (harpResetAuditStats.compaction_health.webhook_slo_windows.last_24h.success_rate || 0) * 100,
                      )}
                      % /{" "}
                      {Math.round(
                        (harpResetAuditStats.compaction_health.webhook_slo_windows.all_time.success_rate || 0) * 100,
                      )}
                      %
                    </div>
                  </div>
                  <div className="rounded border border-border p-2">
                    <div className="text-muted-foreground">Webhook p95 latency trend (1h,24h,all)</div>
                    <div className="font-mono">
                      {sparkline([
                        harpResetAuditStats.compaction_health.webhook_slo_windows.last_1h.p95_latency_ms || 0,
                        harpResetAuditStats.compaction_health.webhook_slo_windows.last_24h.p95_latency_ms || 0,
                        harpResetAuditStats.compaction_health.webhook_slo_windows.all_time.p95_latency_ms || 0,
                      ])}{" "}
                      {harpResetAuditStats.compaction_health.webhook_slo_windows.last_1h.p95_latency_ms ?? "-"}ms /
                      {harpResetAuditStats.compaction_health.webhook_slo_windows.last_24h.p95_latency_ms ?? "-"}ms /{" "}
                      {harpResetAuditStats.compaction_health.webhook_slo_windows.all_time.p95_latency_ms ?? "-"}ms
                    </div>
                  </div>
                </div>
              )}
              <div className="mb-2 space-y-1 text-xs font-mono text-muted-foreground">
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                    <Input
                      value={harpCompactionActorFilter}
                      onChange={(e) => setHarpCompactionActorFilter(e.target.value)}
                      placeholder="compaction actor_tag"
                    />
                    <Select
                      value={harpCompactionTriggerFilter}
                      onValueChange={(v) => setHarpCompactionTriggerFilter(v)}
                    >
                      <SelectOption value="all">all triggers</SelectOption>
                      <SelectOption value="auto">auto</SelectOption>
                      <SelectOption value="manual">manual</SelectOption>
                    </Select>
                    <Select
                      value={harpCompactionSinceWindow}
                      onValueChange={(v) => setHarpCompactionSinceWindow(v)}
                    >
                      <SelectOption value="1h">last 1h</SelectOption>
                      <SelectOption value="24h">last 24h</SelectOption>
                      <SelectOption value="7d">last 7d</SelectOption>
                    </Select>
                  </div>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                    <Select
                      value={harpWebhookStatusFilter}
                      onValueChange={(v) => setHarpWebhookStatusFilter(v)}
                    >
                      <SelectOption value="all">webhook all</SelectOption>
                      <SelectOption value="sent">webhook sent</SelectOption>
                      <SelectOption value="failed">webhook failed</SelectOption>
                    </Select>
                    <Input
                      value={harpWebhookLatencyMinFilter}
                      onChange={(e) => setHarpWebhookLatencyMinFilter(e.target.value)}
                      placeholder="min latency ms"
                    />
                    <Input
                      value={harpWebhookErrorFilter}
                      onChange={(e) => setHarpWebhookErrorFilter(e.target.value)}
                      placeholder="error contains"
                    />
                  </div>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                    <Select
                      value={harpUnmuteWasMutedFilter}
                      onValueChange={(v) => setHarpUnmuteWasMutedFilter(v)}
                    >
                      <SelectOption value="all">unmute all</SelectOption>
                      <SelectOption value="true">was muted=true</SelectOption>
                      <SelectOption value="false">was muted=false</SelectOption>
                    </Select>
                    <Input
                      value={harpUnmuteReasonFilter}
                      onChange={(e) => setHarpUnmuteReasonFilter(e.target.value)}
                      placeholder="unmute reason contains"
                    />
                    <Select
                      value={harpUnmuteSortBy}
                      onValueChange={(v) => setHarpUnmuteSortBy(v as "timestamp" | "actor_tag" | "reason")}
                    >
                      <SelectOption value="timestamp">unmute sort: timestamp</SelectOption>
                      <SelectOption value="actor_tag">unmute sort: actor_tag</SelectOption>
                      <SelectOption value="reason">unmute sort: reason</SelectOption>
                    </Select>
                  </div>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                    <Input
                      value={harpVerifierUnlockId}
                      onChange={(e) => setHarpVerifierUnlockId(e.target.value)}
                      placeholder="verifier id to unlock"
                    />
                    <Button size="sm" ghost onClick={unlockVerifier}>
                      Unlock verifier
                    </Button>
                    <div className="flex items-center gap-2">
                      <Select
                        value={harpVerifyLockBundleFormat}
                        onValueChange={(v) => setHarpVerifyLockBundleFormat(v as "json" | "csv")}
                      >
                        <SelectOption value="json">lock bundle json</SelectOption>
                        <SelectOption value="csv">lock bundle csv</SelectOption>
                      </Select>
                      <Button size="sm" ghost onClick={downloadVerifyLockBundle}>
                        Export lock bundle
                      </Button>
                    </div>
                    <div className="flex items-center gap-2">
                      <Select
                        value={harpVerifyLockAlertsExportFormat}
                        onValueChange={(v) => setHarpVerifyLockAlertsExportFormat(v as "json" | "csv")}
                      >
                        <SelectOption value="json">lock alerts json</SelectOption>
                        <SelectOption value="csv">lock alerts csv</SelectOption>
                      </Select>
                      <Button size="sm" ghost onClick={downloadVerifyLockAlerts}>
                        Export lock alerts
                      </Button>
                    </div>
                    <Select
                      value={harpVerifyLockAlertsActiveFilter}
                      onValueChange={(v) => setHarpVerifyLockAlertsActiveFilter(v)}
                    >
                      <SelectOption value="all">lock alerts: all</SelectOption>
                      <SelectOption value="on">lock alerts: active only</SelectOption>
                      <SelectOption value="off">lock alerts: cleared only</SelectOption>
                    </Select>
                  </div>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                    <Select
                      value={harpCompactionExportStream}
                      onValueChange={(v) =>
                        setHarpCompactionExportStream(v as "alerts" | "webhook" | "unmute" | "verify_unlock")
                      }
                    >
                      <SelectOption value="alerts">export alerts</SelectOption>
                      <SelectOption value="webhook">export webhook</SelectOption>
                      <SelectOption value="unmute">export unmute</SelectOption>
                      <SelectOption value="verify_unlock">export verify unlock</SelectOption>
                    </Select>
                    <Select
                      value={harpCompactionExportFormat}
                      onValueChange={(v) => setHarpCompactionExportFormat(v as "json" | "csv")}
                    >
                      <SelectOption value="json">json</SelectOption>
                      <SelectOption value="csv">csv</SelectOption>
                    </Select>
                    <Button size="sm" ghost onClick={downloadCompactionExport}>
                      <Download className="h-4 w-4" />
                      Export
                    </Button>
                  </div>
                  {harpCompactionAudit.map((row, idx) => (
                    <div key={`${row.timestamp}-${idx}`}>
                      compact {row.trigger} · {new Date((row.timestamp || 0) * 1000).toLocaleTimeString()} · actor=
                      {row.actor_tag || "-"} · {row.before}{"→"}{row.after} rows · partitions={row.partitions}
                    </div>
                  ))}
                  {harpCompactionAlerts.map((row, idx) => (
                    <div key={`alert-${row.timestamp}-${idx}`}>
                      <Badge
                        tone={
                          (row.warning_details || []).some((x) => x.severity === "critical")
                            ? "destructive"
                            : (row.warning_details || []).some((x) => x.severity === "warn")
                              ? "warning"
                              : "secondary"
                        }
                      >
                        {(row.warning_details || []).some((x) => x.severity === "critical")
                          ? "critical"
                          : (row.warning_details || []).some((x) => x.severity === "warn")
                            ? "warn"
                            : "info"}
                      </Badge>{" "}
                      alert {new Date((row.timestamp || 0) * 1000).toLocaleTimeString()} · warnings=
                      {(row.warnings || []).join(",") || "none"} · rows={row.rows} · partitions={row.partitions}
                      {row.high_severity ? " · high" : ""} · severity=
                      {(row.warning_details || []).map((x) => `${x.code}:${x.severity}`).join(",")}
                    </div>
                  ))}
                  {harpCompactionWebhookAudit
                    .filter((row) => {
                      if (harpWebhookStatusFilter === "sent" && !row.sent) return false;
                      if (harpWebhookStatusFilter === "failed" && row.sent) return false;
                      if (harpWebhookLatencyMinFilter.trim()) {
                        const minLatency = Number.parseInt(harpWebhookLatencyMinFilter.trim(), 10);
                        if (Number.isFinite(minLatency) && minLatency > 0) {
                          if ((row.latency_ms ?? 0) < minLatency) return false;
                        }
                      }
                      if (
                        harpWebhookErrorFilter.trim() &&
                        !(row.last_error || "")
                          .toLowerCase()
                          .includes(harpWebhookErrorFilter.trim().toLowerCase())
                      ) {
                        return false;
                      }
                      return true;
                    })
                    .map((row, idx) => (
                    <div key={`webhook-${row.timestamp}-${idx}`}>
                      webhook {new Date((row.timestamp || 0) * 1000).toLocaleTimeString()} ·{" "}
                      {row.sent ? "sent" : "failed"} · attempts={row.attempts} · latency=
                      {row.latency_ms != null ? `${row.latency_ms}ms` : "-"}
                      {row.last_error ? ` · error=${row.last_error}` : ""}
                    </div>
                  ))}
                  {harpUnmuteAudit.map((row, idx) => (
                    <div key={`unmute-${row.timestamp}-${idx}`}>
                      unmute {new Date((row.timestamp || 0) * 1000).toLocaleTimeString()} · actor=
                      {row.actor_tag || "-"} · was_muted={row.was_muted ? "true" : "false"} · reason=
                      {row.reason || "-"}
                    </div>
                  ))}
                  {harpVerifyAudit.map((row, idx) => (
                    <div key={`verify-${row.timestamp}-${idx}`}>
                      verify {new Date((row.timestamp || 0) * 1000).toLocaleTimeString()} · stream={row.stream} · ok=
                      {row.ok ? "true" : "false"} · verifier={row.verifier_id || "-"} · nonce={row.nonce || "-"}
                    </div>
                  ))}
                  {Object.keys(harpVerifyDuplicateHeatmap).length > 0 && (
                    <div>
                      verify duplicate heatmap:{" "}
                      {Object.entries(harpVerifyDuplicateHeatmap)
                        .map(
                          ([k, v]) =>
                            `${k}(10m:${v.last_10m},1h:${v.last_1h},24h:${v.last_24h})`,
                        )
                        .join(" · ")}
                    </div>
                  )}
                  {harpVerifierUnlockAudit.map((row, idx) => (
                    <div key={`verify-unlock-${row.timestamp}-${idx}`}>
                      verify unlock {new Date((row.timestamp || 0) * 1000).toLocaleTimeString()} · verifier=
                      {row.verifier_id || "-"} · actor={row.actor_tag || "-"} · was_locked=
                      {row.was_locked ? "true" : "false"}
                    </div>
                  ))}
                  {harpVerifyLockAudit.map((row, idx) => (
                    <div key={`verify-lock-${row.timestamp}-${idx}`}>
                      verify lock {new Date((row.timestamp || 0) * 1000).toLocaleTimeString()} · action={row.action} ·
                      verifier={row.verifier_id || "-"}
                      {row.locked_until ? ` · until=${new Date(row.locked_until * 1000).toLocaleTimeString()}` : ""}
                    </div>
                  ))}
                  {harpVerifyNonceDuplicateCount > 0 && (
                    <div>
                      verify nonce duplicates={harpVerifyNonceDuplicateCount}
                      {Object.keys(harpVerifyNonceDuplicateByStream).length > 0
                        ? ` · by stream: ${Object.entries(harpVerifyNonceDuplicateByStream)
                            .map(([k, v]) => `${k}:${v}`)
                            .join(", ")}`
                        : ""}
                    </div>
                  )}
                  {Object.keys(harpVerifyActiveLocks).length > 0 && (
                    <div>
                      verifier locks:{" "}
                      {Object.entries(harpVerifyActiveLocks)
                        .map(([k, v]) => `${k}→${new Date(v * 1000).toLocaleTimeString()}`)
                        .join(", ")}
                    </div>
                  )}
                  {harpVerifyLockSummary && (
                    <div>
                      lock summary: locked={harpVerifyLockSummary.locked_verifier_count}
                      {harpVerifyLockSummary.soonest_unlock_at
                        ? ` · soonest unlock=${new Date(harpVerifyLockSummary.soonest_unlock_at * 1000).toLocaleTimeString()}`
                        : ""}
                      {` · lock entries 24h=${harpVerifyLockSummary.lock_entries_24h}`}
                      {harpVerifyLockSummary.lock_entries_windows
                        ? ` · windows(1h/24h/7d)=${harpVerifyLockSummary.lock_entries_windows.last_1h}/${harpVerifyLockSummary.lock_entries_windows.last_24h}/${harpVerifyLockSummary.lock_entries_windows.last_7d}`
                        : ""}
                      {typeof harpVerifyLockSummary.active_locks_alert === "boolean"
                        ? ` · active-lock-alert=${harpVerifyLockSummary.active_locks_alert ? "on" : "off"}`
                        : ""}
                      {harpVerifyLockSummary.active_locks_threshold
                        ? ` · threshold=${harpVerifyLockSummary.active_locks_threshold}`
                        : ""}
                      {harpVerifyLockSummary.active_locks_alert &&
                      typeof harpVerifyLockSummary.active_locks_alert_dwell_seconds === "number"
                        ? ` · dwell=${Math.round(harpVerifyLockSummary.active_locks_alert_dwell_seconds)}s`
                        : ""}
                      {harpVerifyLockSummary.active_locks_alert_dwell_severity &&
                      harpVerifyLockSummary.active_locks_alert_dwell_severity !== "none"
                        ? ` · dwell-severity=${harpVerifyLockSummary.active_locks_alert_dwell_severity}`
                        : ""}
                    </div>
                  )}
                  {harpVerifyLockNotifyMetrics && (
                    <div>
                      lock notify metrics: attempted={harpVerifyLockNotifyMetrics.attempted} · sent=
                      {harpVerifyLockNotifyMetrics.sent} · failed={harpVerifyLockNotifyMetrics.failed} · success=
                      {Math.round((harpVerifyLockNotifyMetrics.success_rate || 0) * 100)}% · p95=
                      {harpVerifyLockNotifyMetrics.p95_latency_ms ?? "-"}ms
                      {harpVerifyLockNotifyMetrics.windows
                        ? ` · windows(1h/24h success)=${Math.round((harpVerifyLockNotifyMetrics.windows.last_1h.success_rate || 0) * 100)}%/${Math.round((harpVerifyLockNotifyMetrics.windows.last_24h.success_rate || 0) * 100)}%`
                        : ""}
                    </div>
                  )}
                  {harpVerifyLockAlerts.map((row, idx) => (
                    <div key={`verify-lock-alert-${row.timestamp}-${idx}`}>
                      verify lock alert {new Date((row.timestamp || 0) * 1000).toLocaleTimeString()} · active=
                      {row.active ? "true" : "false"} · locked={row.locked_verifier_count} · threshold=
                      {row.threshold}
                    </div>
                  ))}
                  {harpCompactionAudit.length === 0 &&
                    harpCompactionAlerts.length === 0 &&
                    harpCompactionWebhookAudit.length === 0 &&
                    harpUnmuteAudit.length === 0 &&
                    harpVerifyAudit.length === 0 &&
                    harpVerifyLockAlerts.length === 0 && (
                    <div>No compaction activity.</div>
                  )}
                </div>
              <div className="space-y-1 text-xs font-mono text-muted-foreground">
                {harpResetAudit.filter((row) => {
                  if (harpAuditKeyFilter && !(row.key || "").includes(harpAuditKeyFilter)) return false;
                  return true;
                }).length === 0 && <div>No reset audit entries.</div>}
                {harpResetAudit
                  .filter((row) => {
                    if (harpAuditKeyFilter && !(row.key || "").includes(harpAuditKeyFilter)) return false;
                    return true;
                  })
                  .map((row, idx) => (
                  <div key={`${row.timestamp}-${idx}`}>
                    {new Date((row.timestamp || 0) * 1000).toLocaleTimeString()} ·{" "}
                    {row.allowed ? "allowed" : "denied"} · actor={row.actor_tag || "-"} · scope={row.scope}
                    {row.key ? `/${row.key}` : ""} · removed={row.removed} · reason={row.reason || "-"}
                  </div>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={harpAutoRefresh ? "success" : "secondary"}>
                auto-refresh {harpAutoRefresh ? "on" : "off"}
              </Badge>
              <Button size="sm" ghost onClick={() => setHarpAutoRefresh((v) => !v)}>
                Toggle auto-refresh
              </Button>
              <Badge tone={harpLint?.ok ? "success" : "warning"}>
                lint {harpLint?.ok ? "ok" : "needs attention"}
              </Badge>
              {harpMetrics?.reliability?.deltas?.last_1h_vs_prev_1h?.severity && (
                <Badge tone="secondary">
                  severity {harpMetrics.reliability.deltas.last_1h_vs_prev_1h.severity}
                </Badge>
              )}
              {harpVerifyLockSummary?.active_locks_alert && (
                <Badge tone={lockAlertSeverityTone(harpVerifyLockSummary.active_locks_alert_dwell_severity)}>
                  active-lock alert ({harpVerifyLockSummary.locked_verifier_count}
                  {harpVerifyLockSummary.active_locks_threshold
                    ? `>${harpVerifyLockSummary.active_locks_threshold}`
                    : ""}
                  {typeof harpVerifyLockSummary.active_locks_alert_dwell_seconds === "number"
                    ? `, ${Math.round(harpVerifyLockSummary.active_locks_alert_dwell_seconds)}s`
                    : ""}
                  {harpVerifyLockSummary.active_locks_alert_dwell_severity &&
                  harpVerifyLockSummary.active_locks_alert_dwell_severity !== "none"
                    ? `, ${harpVerifyLockSummary.active_locks_alert_dwell_severity}`
                    : ""}
                  )
                </Badge>
              )}
              {harpCursor && (
                <span className="text-xs text-muted-foreground font-mono">
                  cursor: {harpCursor.slice(0, 12)}
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                ghost
                prefix={<Download className="h-3.5 w-3.5" />}
                onClick={() => void downloadHarpExport("json")}
              >
                Export JSON
              </Button>
              <Button
                size="sm"
                ghost
                prefix={<Download className="h-3.5 w-3.5" />}
                onClick={() => void downloadHarpExport("csv")}
              >
                Export CSV
              </Button>
            </div>

            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              <div className="rounded border border-border p-3">
                <div className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
                  Recent decisions
                </div>
                <div className="max-h-44 overflow-auto space-y-1 text-xs font-mono">
                  {(harpStatus?.history ?? []).slice(-8).map((row, idx) => (
                    <div key={`${row.timestamp}-${row.state}-${idx}`} className="text-muted-foreground">
                      {new Date((row.timestamp || 0) * 1000).toLocaleTimeString()} · {row.state}
                      {row.provider ? ` · ${row.provider}` : ""}
                      {row.model ? `/${row.model}` : ""}
                    </div>
                  ))}
                  {!harpStatus?.history?.length && (
                    <div className="text-muted-foreground">No decisions yet.</div>
                  )}
                </div>
              </div>

              <div className="rounded border border-border p-3">
                <div className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
                  Alert audit trail
                </div>
                <div className="max-h-44 overflow-auto space-y-1 text-xs font-mono">
                  {(harpStatus?.alerts ?? []).slice(-8).map((row, idx) => (
                    <div key={`${row.timestamp}-${row.audit_id ?? idx}`} className="text-muted-foreground">
                      {new Date((row.timestamp || 0) * 1000).toLocaleTimeString()} · {row.severity}
                      {row.audit_id ? ` · ${row.audit_id.slice(0, 8)}` : ""}
                      {row.webhook_status ? ` · webhook:${row.webhook_status}` : ""}
                    </div>
                  ))}
                  {!harpStatus?.alerts?.length && (
                    <div className="text-muted-foreground">No alerts yet.</div>
                  )}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* ── Gateway ───────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <Power className="h-4 w-4" /> Gateway
        </H2>
        <Card>
          <CardContent className="flex items-center justify-between py-4">
            <div className="flex items-center gap-3">
              <Badge tone={gatewayRunning ? "success" : "secondary"}>
                {gatewayRunning ? "running" : "stopped"}
              </Badge>
              <span className="text-sm text-muted-foreground">
                {status?.gateway_state ?? "—"}
                {status?.gateway_pid ? ` · pid ${status.gateway_pid}` : ""}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                className="uppercase"
                onClick={() => runGateway("start")}
                disabled={gatewayRunning}
                prefix={<Play className="h-3.5 w-3.5" />}
              >
                Start
              </Button>
              <Button
                size="sm"
                className="uppercase"
                onClick={() => runGateway("restart")}
                prefix={<RotateCw className="h-3.5 w-3.5" />}
              >
                Restart
              </Button>
              <Button
                size="sm"
                className="uppercase text-warning"
                ghost
                onClick={() => runGateway("stop")}
                disabled={!gatewayRunning}
                prefix={<Power className="h-3.5 w-3.5" />}
              >
                Stop
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* ── Memory ────────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <Brain className="h-4 w-4" /> Memory
        </H2>
        <Card>
          <CardContent className="flex flex-col gap-4 py-4">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span>
                External provider:{" "}
                <span className="font-mono text-foreground">
                  {memory?.active || "built-in only"}
                </span>
              </span>
              <Link to="/plugins" className="underline">
                Change in Plugins →
              </Link>
              <span className="ml-auto">
                New credentials:{" "}
                <span className="font-mono">hermes memory setup</span>
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
              <span className="text-xs text-muted-foreground">
                Built-in files — MEMORY.md:{" "}
                {formatBytes(memory?.builtin_files.memory ?? 0)} · USER.md:{" "}
                {formatBytes(memory?.builtin_files.user ?? 0)}
              </span>
              <div className="flex items-center gap-2 ml-auto">
                <Button size="sm" ghost className="text-destructive" onClick={() => memoryReset.requestDelete("memory")}>
                  Reset MEMORY.md
                </Button>
                <Button size="sm" ghost className="text-destructive" onClick={() => memoryReset.requestDelete("user")}>
                  Reset USER.md
                </Button>
                <Button size="sm" ghost className="text-destructive" onClick={() => memoryReset.requestDelete("all")}>
                  Reset all
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* ── Credential pool ───────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <KeyRound className="h-4 w-4" /> Credential pool
        </H2>
        <Card>
          <CardContent className="flex flex-col gap-4 py-4">
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
              <div className="grid gap-2">
                <Label htmlFor="cred-provider">Provider</Label>
                <Input id="cred-provider" value={credProvider} onChange={(e) => setCredProvider(e.target.value)} placeholder="openrouter" />
              </div>
              <div className="grid gap-2 sm:col-span-2">
                <Label htmlFor="cred-key">API key</Label>
                <Input id="cred-key" type="password" value={credKey} onChange={(e) => setCredKey(e.target.value)} placeholder="sk-…" />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="cred-label">Label</Label>
                <Input id="cred-label" value={credLabel} onChange={(e) => setCredLabel(e.target.value)} placeholder="optional" />
              </div>
            </div>
            <div className="flex justify-end">
              <Button size="sm" className="uppercase" onClick={addCredential} disabled={addingCred} prefix={addingCred ? <Spinner /> : undefined}>
                Add key
              </Button>
            </div>
            {pool.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No pooled credentials. Add one above to enable key rotation.
              </p>
            )}
            {pool.map((prov) => (
              <div key={prov.provider} className="flex flex-col gap-2">
                <span className="text-xs uppercase tracking-wider text-muted-foreground">
                  {prov.provider}
                </span>
                {prov.entries.map((entry) => (
                  <div key={`${prov.provider}-${entry.index}`} className="flex items-center gap-3 border border-border bg-background/40 px-3 py-2">
                    <span className="text-sm font-medium">{entry.label}</span>
                    <span className="font-mono text-xs text-muted-foreground">{entry.token_preview}</span>
                    <Badge tone="outline">{entry.auth_type}</Badge>
                    {entry.last_status && <Badge tone="secondary">{entry.last_status}</Badge>}
                    <Button ghost size="icon" className="ml-auto text-destructive" aria-label="Remove credential" onClick={() => credDelete.requestDelete(`${prov.provider}|${entry.index}`)}>
                      <Trash2 />
                    </Button>
                  </div>
                ))}
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      {/* ── Operations ────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <Activity className="h-4 w-4" /> Operations
        </H2>
        <Card>
          <CardContent className="flex flex-wrap gap-2 py-4">
            <Button size="sm" ghost prefix={<Stethoscope className="h-3.5 w-3.5" />} onClick={() => runOp(api.runDoctor, "Doctor")}>
              Run doctor
            </Button>
            <Button size="sm" ghost prefix={<ShieldCheck className="h-3.5 w-3.5" />} onClick={() => runOp(api.runSecurityAudit, "Security audit")}>
              Security audit
            </Button>
            <Button size="sm" ghost prefix={<Database className="h-3.5 w-3.5" />} onClick={() => runOp(() => api.runBackup(), "Backup")}>
              Create backup
            </Button>
            <Button size="sm" ghost prefix={<RotateCw className="h-3.5 w-3.5" />} onClick={() => runOp(api.updateSkillsFromHub, "Skills update")}>
              Update skills
            </Button>
            <Button size="sm" ghost prefix={<Activity className="h-3.5 w-3.5" />} onClick={() => runOp(api.runPromptSize, "Prompt size")}>
              Prompt size
            </Button>
            <Button size="sm" ghost prefix={<Database className="h-3.5 w-3.5" />} onClick={() => runOp(api.runDump, "Support dump")}>
              Support dump
            </Button>
            <Button size="sm" ghost prefix={<RotateCw className="h-3.5 w-3.5" />} onClick={() => runOp(api.runConfigMigrate, "Config migrate")}>
              Migrate config
            </Button>
          </CardContent>
        </Card>

        {/* Debug share — uploads a redacted report + logs, returns shareable
            links. Separated from the buttons above because its output is
            persistent, copyable URLs, not a fire-and-forget log tail. */}
        <Card>
          <CardContent className="flex flex-col gap-3 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-start gap-2">
                <Share2 className="h-4 w-4 mt-0.5 text-muted-foreground" />
                <div className="flex flex-col">
                  <span className="text-sm font-medium">Share debug report</span>
                  <span className="text-xs text-muted-foreground max-w-prose">
                    Uploads system info + logs to a public paste service and
                    returns links to send the Hermes team. Pastes auto-delete
                    after 6 hours.
                  </span>
                </div>
              </div>
              <Button
                size="sm"
                disabled={sharing}
                prefix={
                  sharing ? (
                    <Spinner className="h-3.5 w-3.5" />
                  ) : (
                    <Share2 className="h-3.5 w-3.5" />
                  )
                }
                onClick={() => void runDebugShare()}
              >
                {sharing ? "Uploading…" : "Generate share link"}
              </Button>
            </div>

            <label className="flex items-center gap-2 text-xs text-muted-foreground select-none">
              <input
                type="checkbox"
                className="accent-current"
                checked={shareRedact}
                disabled={sharing}
                onChange={(e) => setShareRedact(e.target.checked)}
              />
              Redact credential-shaped tokens before upload (recommended)
            </label>

            {shareResult && (
              <div className="flex flex-col gap-2 border-t border-border pt-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge tone="success">uploaded</Badge>
                    {shareResult.redacted ? (
                      <Badge tone="outline">redacted</Badge>
                    ) : (
                      <Badge tone="warning">not redacted</Badge>
                    )}
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      auto-deletes in{" "}
                      {Math.round(shareResult.auto_delete_seconds / 3600)}h
                    </span>
                  </div>
                  {Object.keys(shareResult.urls).length > 1 && (
                    <Button
                      size="sm"
                      ghost
                      prefix={
                        copiedLabel === "__all__" ? (
                          <Check className="h-3.5 w-3.5" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )
                      }
                      onClick={() =>
                        void copyToClipboard(
                          Object.entries(shareResult.urls)
                            .map(([label, url]) => `${label}: ${url}`)
                            .join("\n"),
                          "__all__",
                        )
                      }
                    >
                      Copy all
                    </Button>
                  )}
                </div>

                {Object.entries(shareResult.urls).map(([label, url]) => (
                  <div
                    key={label}
                    className="flex items-center gap-2 bg-background/50 border border-border px-3 py-2"
                  >
                    <Link2 className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <span className="font-mono text-xs shrink-0 w-24 truncate text-muted-foreground">
                      {label}
                    </span>
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono text-xs truncate flex-1 text-primary hover:underline"
                    >
                      {url}
                    </a>
                    <Button
                      ghost
                      size="icon"
                      aria-label={`Copy ${label} link`}
                      onClick={() => void copyToClipboard(url, label)}
                    >
                      {copiedLabel === label ? <Check /> : <Copy />}
                    </Button>
                  </div>
                ))}

                {shareResult.failures.length > 0 && (
                  <span className="text-xs text-destructive">
                    Some logs failed to upload: {shareResult.failures.join("; ")}
                  </span>
                )}
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-end">
            <div className="grid gap-2 flex-1">
              <Label htmlFor="import-path">Restore from backup archive</Label>
              <Input id="import-path" value={importPath} onChange={(e) => setImportPath(e.target.value)} placeholder="/path/to/hermes-backup.zip" />
            </div>
            <Button
              size="sm"
              ghost
              disabled={!importPath.trim()}
              onClick={() => {
                if (!importPath.trim()) return;
                setImportConfirmOpen(true);
              }}
            >
              Import
            </Button>
            <ConfirmDialog
              open={importConfirmOpen}
              title="Restore from backup?"
              description={`This will overwrite your current Hermes configuration, skills, sessions, and data with the contents of ${importPath.trim() || "the archive"}. This cannot be undone.`}
              destructive
              confirmLabel="Restore"
              cancelLabel="Cancel"
              onCancel={() => setImportConfirmOpen(false)}
              onConfirm={() => {
                setImportConfirmOpen(false);
                runOp(() => api.runImport(importPath.trim(), true), "Import");
              }}
            />
          </CardContent>
        </Card>
      </section>

      {/* ── Checkpoints ───────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <Database className="h-4 w-4" /> Checkpoints
        </H2>
        <Card>
          <CardContent className="flex items-center justify-between py-4">
            <span className="text-sm text-muted-foreground">
              {checkpoints?.sessions.length ?? 0} session(s) ·{" "}
              {formatBytes(checkpoints?.total_bytes ?? 0)}
            </span>
            <Button size="sm" ghost className="text-destructive" disabled={!checkpoints?.sessions.length} prefix={<Trash2 className="h-3.5 w-3.5" />} onClick={() => checkpointsPrune.requestDelete("all")}>
              Prune
            </Button>
          </CardContent>
        </Card>
      </section>

      {/* ── Shell hooks ───────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
            <Terminal className="h-4 w-4" /> Shell hooks
          </H2>
          <Button size="sm" className="uppercase" prefix={<Plus className="h-3.5 w-3.5" />} onClick={() => setHookModalOpen(true)}>
            New hook
          </Button>
        </div>
        {(!hooks || hooks.hooks.length === 0) && (
          <Card>
            <CardContent className="py-6 text-center text-sm text-muted-foreground">
              No shell hooks configured.
            </CardContent>
          </Card>
        )}
        {hooks?.hooks.map((h: HookEntry, i) => (
          <Card key={`${h.event}-${i}`}>
            <CardContent className="flex items-center gap-3 py-3">
              <Badge tone="outline">{h.event}</Badge>
              {h.matcher && (
                <span className="text-xs text-muted-foreground">matcher: {h.matcher}</span>
              )}
              <span className="font-mono text-xs truncate flex-1">{h.command}</span>
              {h.executable === false && (
                <Badge tone="destructive">not executable</Badge>
              )}
              <Badge tone={h.allowed ? "success" : "warning"}>
                {h.allowed ? "allowed" : "not approved"}
              </Badge>
              <Button
                ghost
                size="icon"
                className="text-destructive"
                aria-label="Remove hook"
                onClick={() =>
                  hookDelete.requestDelete(`${h.event}|${h.command ?? ""}`)
                }
              >
                <Trash2 />
              </Button>
            </CardContent>
          </Card>
        ))}
      </section>
    </div>
  );
}
