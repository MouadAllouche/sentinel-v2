export interface IncidentFilters {
  status: string[];
  severity: string[];
  assignee: string;
  search: string;
  since: string;
  until: string;
  needsAttention: boolean;
  sort: "risk" | "recent";
  cursor: string | null;
}

export const emptyIncidentFilters: IncidentFilters = {
  status: [],
  severity: [],
  assignee: "",
  search: "",
  since: "",
  until: "",
  needsAttention: false,
  sort: "risk",
  cursor: null,
};

export function parseIncidentFilters(search: string): IncidentFilters {
  const params = new URLSearchParams(search);
  const filters: IncidentFilters = {
    ...emptyIncidentFilters,
    status: params.getAll("status"),
    severity: params.getAll("severity"),
  };
  filters.assignee = params.get("assignee") ?? "";
  filters.search = params.get("search") ?? "";
  filters.since = params.get("since") ?? "";
  filters.until = params.get("until") ?? "";
  filters.needsAttention = params.get("needs_attention") === "true";
  filters.sort = params.get("sort") === "recent" ? "recent" : "risk";
  filters.cursor = params.get("cursor");
  return filters;
}

export function incidentFiltersToSearch(filters: IncidentFilters): string {
  const params = new URLSearchParams();
  for (const value of filters.status) params.append("status", value);
  for (const value of filters.severity) params.append("severity", value);
  if (filters.assignee) params.set("assignee", filters.assignee);
  if (filters.search) params.set("search", filters.search);
  if (filters.since) params.set("since", filters.since);
  if (filters.until) params.set("until", filters.until);
  if (filters.needsAttention) params.set("needs_attention", "true");
  if (filters.sort !== "risk") params.set("sort", filters.sort);
  if (filters.cursor) params.set("cursor", filters.cursor);
  return params.toString();
}
