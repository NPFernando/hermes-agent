import type { StatusResponse } from "@/lib/api";
import type { useI18n } from "@/i18n";

export function gatewayLine(
  status: StatusResponse,
  t: ReturnType<typeof useI18n>["t"],
): { label: string; tone: string } {
  const g = t.app.gatewayStrip;
  const byState: Record<string, { label: string; tone: string }> = {
    running: { label: g.running, tone: "text-success" },
    starting: { label: g.starting, tone: "text-warning" },
    startup_failed: { label: g.failed, tone: "text-destructive" },
    stopped: { label: g.stopped, tone: "text-muted-foreground" },
  };
  if (status.gateway_state && byState[status.gateway_state]) {
    return byState[status.gateway_state];
  }
  return status.gateway_running
    ? { label: g.running, tone: "text-success" }
    : { label: g.off, tone: "text-muted-foreground" };
}

export function harpLine(status: StatusResponse): { label: string; tone: string } {
  const harp = status.harp_routing?.status ?? {};
  const enabled = harp.enabled === true;
  const state = String(harp.state ?? "").toLowerCase();

  if (!enabled) {
    return { label: "off", tone: "text-muted-foreground" };
  }

  const byState: Record<string, { label: string; tone: string }> = {
    applied: { label: "applied", tone: "text-success" },
    auto_reenabled: { label: "reenabled", tone: "text-warning" },
    provider_cooldown: { label: "cooldown", tone: "text-warning" },
    failed: { label: "failed", tone: "text-destructive" },
    auto_disabled: { label: "disabled", tone: "text-destructive" },
    no_decision: { label: "no decision", tone: "text-muted-foreground" },
  };

  return byState[state] ?? { label: "enabled", tone: "text-success" };
}
