export interface EventLike {
  id: number;
  timestamp: string;
  event_type: string;
  severity: string;
  description: string;
  severity_source?: string;
  source?: string;
  source_ip?: string | null;
  username?: string | null;
  process_name?: string | null;
  score?: number;
  enrichment?: Record<string, unknown>;
  [key: string]: unknown;
}

/** Severity provenance is always shown as text; no colour-only meaning. */
export function severitySourceText(event: Partial<EventLike>): string {
  const source = String(event.severity_source ?? "fallback");
  if (source === "default") return "default severity";
  if (source.startsWith("override:")) return `override ${source.slice("override:".length)}`;
  if (source.startsWith("rule:")) return `rule ${source.slice("rule:".length)}`;
  return "fallback";
}

export function groupBySeverity(events: Array<{ severity: string }>): Record<string, number> {
  return events.reduce<Record<string, number>>((counts, event) => {
    counts[event.severity] = (counts[event.severity] ?? 0) + 1;
    return counts;
  }, {});
}

const TYPE_GROUPS: Record<string, string[]> = {
  Authentication: [
    "failed_login", "successful_login", "invalid_user", "preauth_disconnect",
    "user_created", "user_deleted", "password_changed", "group_member_added",
  ],
  Network: ["network_connection", "new_listening_port", "port_scan"],
  Process: ["process_started", "suspicious_process", "sudo_command", "su_command"],
  Configuration: ["config_drift", "permission_change", "package_installed", "package_removed"],
  System: ["system_info"],
  Detection: ["anomaly", "rule_triggered"],
};

export function eventTypeGroup(eventType: string): string {
  for (const [group, types] of Object.entries(TYPE_GROUPS)) {
    if (types.includes(eventType)) return group;
  }
  return "System";
}

export const EVENT_TYPE_GROUPS = TYPE_GROUPS;

export const EVENT_SOURCES = [
  "auth_log", "journald", "dpkg", "network", "listening", "process", "filesystem",
  "system", "baseline", "rules",
] as const;
