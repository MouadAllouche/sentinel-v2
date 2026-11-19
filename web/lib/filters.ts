/** URL-synced filter state for the Events explorer (UI state, not API types). */
export interface EventFilters {
  event_type: string[];
  severity: string[];
  source: string[];
  username: string;
  source_ip: string;
  source_cidr: string;
  process_name: string;
  since: string;
  until: string;
  preset: string;
  search: string;
  allowlisted: boolean | null;
  in_incident: boolean | null;
  incident_id: number | null;
  timezone: "utc" | "local";
  limit: number;
  cursor: string | null;
}

export const emptyFilters: EventFilters = {
  event_type: [],
  severity: [],
  source: [],
  username: "",
  source_ip: "",
  source_cidr: "",
  process_name: "",
  since: "",
  until: "",
  preset: "24h",
  search: "",
  allowlisted: true,
  in_incident: null,
  incident_id: null,
  timezone: "utc",
  limit: 50,
  cursor: null,
};

const ARRAY_KEYS = ["event_type", "severity", "source"] as const;
const TEXT_KEYS = ["username", "source_ip", "source_cidr", "process_name", "since", "until", "preset", "search"] as const;

export function isValidCidr(value: string): boolean {
  const [address, prefixText, extra] = value.split("/");
  if (!address || !prefixText || extra !== undefined) return false;
  if (address.includes(":")) {
    if (!/^[0-9a-fA-F:]+$/.test(address)) return false;
    const prefix = Number(prefixText);
    return Number.isInteger(prefix) && prefix >= 0 && prefix <= 128;
  }
  const octets = address.split(".");
  if (octets.length !== 4) return false;
  if (!octets.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255)) return false;
  const prefix = Number(prefixText);
  return Number.isInteger(prefix) && prefix >= 0 && prefix <= 32;
}

export function parseEventFilters(search: string, nowIso?: string): EventFilters {
  const params = new URLSearchParams(search);
  const filters: EventFilters = { ...emptyFilters, event_type: [], severity: [], source: [] };
  for (const key of ARRAY_KEYS) filters[key] = params.getAll(key);
  for (const key of TEXT_KEYS) filters[key] = params.get(key) ?? "";
  const allowlisted = params.get("allowlisted");
  filters.allowlisted = allowlisted === null ? true : allowlisted === "true";
  const inIncident = params.get("in_incident");
  filters.in_incident = inIncident === null ? null : inIncident === "true";
  filters.timezone = params.get("timezone") === "local" ? "local" : "utc";
  if (!filters.since && !filters.until && filters.preset && filters.preset !== "custom") {
    const range = rangeForPreset(filters.preset, nowIso ?? new Date().toISOString());
    filters.since = range.since;
    filters.until = range.until;
  }
  const incidentId = params.get("incident_id");
  filters.incident_id = incidentId === null ? null : Number.parseInt(incidentId, 10);
  const limit = params.get("limit");
  filters.limit = limit ? Number.parseInt(limit, 10) : 50;
  filters.cursor = params.get("cursor");
  return filters;
}

export function filtersToSearch(filters: EventFilters): string {
  const params = new URLSearchParams();
  for (const key of ARRAY_KEYS) for (const value of filters[key]) params.append(key, value);
  for (const key of TEXT_KEYS) if (filters[key]) params.set(key, filters[key]);
  if (filters.allowlisted !== null) params.set("allowlisted", String(filters.allowlisted));
  if (filters.in_incident !== null) params.set("in_incident", String(filters.in_incident));
  if (filters.timezone === "local") params.set("timezone", "local");
  if (filters.incident_id !== null) params.set("incident_id", String(filters.incident_id));
  if (filters.limit && filters.limit !== 50) params.set("limit", String(filters.limit));
  if (filters.cursor) params.set("cursor", filters.cursor);
  return params.toString();
}

export function formatDelta(current: number, previous: number): string {
  if (previous === 0) return current === 0 ? "0 (0%)" : "new";
  const difference = current - previous;
  const percent = Math.round((difference / previous) * 100);
  const sign = difference > 0 ? "+" : "";
  return `${sign}${difference} (${sign}${percent}%)`;
}

const PRESET_MS: Record<string, number> = {
  "15m": 15 * 60_000,
  "1h": 60 * 60_000,
  "24h": 24 * 60 * 60_000,
  "48h": 48 * 60 * 60_000,
  "7d": 7 * 24 * 60 * 60_000,
  "30d": 30 * 24 * 60 * 60_000,
};

export function rangeForPreset(
  preset: string,
  nowIso: string,
): { since: string; until: string } {
  const duration = PRESET_MS[preset] ?? PRESET_MS["24h"]!;
  const until = nowIso.replace("Z", "+00:00");
  const since = new Date(new Date(nowIso).getTime() - duration)
    .toISOString()
    .replace(/\.\d{3}Z$/, "+00:00");
  return { since, until };
}
