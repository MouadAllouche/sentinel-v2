import { MitreBadge, RiskScoreMeter } from "@/components/badges/ExplanationBadges";
import { SeverityBadge } from "@/components/badges/SeverityBadge";
import { CaveatBanner } from "@/components/incidents/CaveatBanner";
import { StatusMenu } from "@/components/incidents/StatusMenu";
import { Input } from "@/components/ui/primitives";
import type { Role } from "@/lib/auth";
import { formatGap } from "@/lib/incident/helpers";

/** The caveat is part of the header so it is present on every tab and deep link. */
export function IncidentHeader({
  incident,
  currentRole,
  onStatusChange,
  onAssigneeChange,
  error,
}: {
  incident: {
    id: number;
    title: string;
    severity: string;
    status: string;
    risk_score: number;
    first_seen?: string;
    last_seen?: string;
    assignee?: string | null;
    mitre?: string[];
  };
  currentRole: Role;
  onStatusChange: (status: string, reason?: string) => void;
  onAssigneeChange?: (assignee: string) => void;
  error?: string | null;
}) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{incident.title}</h1>
          <p className="text-sm text-slate-500">Incident #{incident.id}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <SeverityBadge severity={incident.severity} />
          <div className="w-40">
            <RiskScoreMeter value={incident.risk_score} />
          </div>
          <StatusMenu status={incident.status} currentRole={currentRole} onChange={onStatusChange} error={error} />
        </div>
      </div>
      <div className="flex flex-wrap gap-4 text-sm text-slate-600 dark:text-slate-300">
        <span>Status: {incident.status.replaceAll("_", " ")}</span>
        <span>
          Assignee: {currentRole === "admin" && onAssigneeChange ? (
            <Input
              aria-label="Assignee"
              className="inline-block w-40"
              defaultValue={incident.assignee ?? ""}
              onBlur={(event) => {
                if (event.target.value !== (incident.assignee ?? "")) onAssigneeChange(event.target.value);
              }}
            />
          ) : (
            incident.assignee ?? "unassigned"
          )}
        </span>
        <span>First seen: {incident.first_seen ?? "unknown"}</span>
        <span>Last seen: {incident.last_seen ?? "unknown"}</span>
        <span>
          Duration: {incident.first_seen && incident.last_seen
            ? formatGap(incident.first_seen, incident.last_seen)
            : "unknown"}
        </span>
      </div>
      {incident.mitre?.length ? (
        <div className="flex flex-wrap gap-1">
          {incident.mitre.map((technique) => (
            <MitreBadge key={technique} technique={technique} />
          ))}
        </div>
      ) : null}
      <CaveatBanner />
    </div>
  );
}
