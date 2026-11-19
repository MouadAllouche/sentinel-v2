import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AuditPage } from "@/components/audit/AuditPage";
import { BehaviorPage } from "@/components/behavior/BehaviorPage";
import { DriftPage } from "@/components/drift/DriftPage";
import { HealthPage } from "@/components/health/HealthPage";
import { ChannelEditor } from "@/components/notifications/ChannelEditor";
import { RetentionPanel } from "@/components/settings/RetentionPanel";
import { UsersPage } from "@/components/users/UsersPage";

const admin = "admin" as const;
const viewer = "viewer" as const;

describe("behavior, drift and admin pages", () => {
  it("shows maturity, anomaly explanation and URL-synced metric selection", async () => {
    render(
      <BehaviorPage
        filters={{ metric: "failed_logins_per_hour", subject: "", range: "24h" }}
        onFiltersChange={vi.fn()}
        baselines={[{ metric: "failed_logins_per_hour", subject: "global", samples: 6, status: "learning" }]}
        anomalies={[{
          id: 1, timestamp: "2026-11-19T10:00:00+00:00", metric: "failed_logins_per_hour",
          subject: "global", observed: 25, mean: 2, stddev: 1, z: 23,
          description: "Unusually many failed logins were observed.", severity: "medium",
        }]}
        knownIps={[]}
        role={viewer}
      />,
    );
    expect(screen.getAllByText(/not enough data/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/unusually many failed logins/i)).toBeInTheDocument();
    expect(screen.getByText(/unusual is not necessarily malicious/i)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Metric"), "sudo_by_user");
  });

  it("shows drift status as text, locks metadata-only and hides file contents", async () => {
    render(
      <DriftPage
        paths={[{
          id: 1, path: "/etc/shadow", kind: "file", enabled: true, sensitivity: "high",
          category: "system", metadata_only: true, baseline_status: "drifted",
          last_checked: "2026-11-19T10:00:00+00:00", warnings: ["hash unavailable: permission denied"],
        }]}
        snapshots={[]}
        onSelect={vi.fn()}
        onAccept={vi.fn()}
        onCheck={vi.fn()}
        role={admin}
      />,
    );
    expect(screen.getByText("drifted")).toBeInTheDocument();
    expect(screen.getByLabelText(/metadata only/i)).toBeDisabled();
    expect(screen.queryByText(/root:x:/)).toBeNull();
    await userEvent.click(screen.getByRole("row", { name: /\/etc\/shadow/ }));
    await userEvent.click(screen.getByRole("button", { name: /accept as new baseline/i }));
    expect(screen.getByRole("button", { name: /confirm/i })).toBeDisabled();
  });

  it("validates env-var names and shows set/not set without values", async () => {
    const onSave = vi.fn();
    render(
      <ChannelEditor
        value={{ name: "Test", kind: "webhook", enabled: false, config: {}, min_severity: "high" }}
        envVars={{ SENTINEL_WEBHOOK_SECRET: true }}
        onSave={onSave}
      />,
    );
    expect(screen.getByText(/set/i)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Secret env var"), "lowercase");
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("validates retention and requires typed confirmation for apply", async () => {
    const onApply = vi.fn();
    render(
      <RetentionPanel
        policy={{ events: { low_days: 90, medium_days: 30, high_days: 60, critical_days: 120 } }}
        onChange={vi.fn()}
        onSave={vi.fn()}
        dryRun={{ pruned: 12 }}
        onPreview={vi.fn()}
        onApply={onApply}
        role={admin}
      />,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /apply/i })).toBeDisabled();
  });

  it("guards the last admin and shows a one-time password", async () => {
    const onCreate = vi.fn();
    render(
      <UsersPage
        users={[{ id: 1, username: "admin", role: "admin", disabled: false, last_login: "2026-11-19T10:00:00+00:00" }]}
        role={admin}
        onCreate={onCreate}
        onChangeRole={vi.fn()}
        onDisable={vi.fn()}
        onResetPassword={vi.fn()}
        onRevokeSessions={vi.fn()}
      />,
    );
    expect(screen.getByLabelText(/disable admin/i)).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /create user/i }));
    await userEvent.type(screen.getByLabelText("New username"), "viewer2");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(screen.getByText(/shown once/i)).toBeInTheDocument();
  });

  it("renders audit diffs and applies filters", async () => {
    const onFiltersChange = vi.fn();
    render(
      <AuditPage
        rows={[{
          id: 1, ts: "2026-11-19T10:00:00+00:00", actor: "admin", action: "rule.update",
          target_type: "rule", target_id: "r1", before_json: '{"a":1}', after_json: '{"a":2}',
        }]}
        filters={{ actor: "", action: "", targetType: "", since: "", until: "" }}
        onFiltersChange={onFiltersChange}
        onExport={vi.fn()}
        role={admin}
      />,
    );
    expect(screen.getByText(/changed/i)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Actor"), "admin");
    expect(onFiltersChange).toHaveBeenCalled();
  });

  it("maps health warnings to hints", () => {
    render(
      <HealthPage
        health={{ status: "degraded", reasons: ["auth.log: permission denied"], db: { size_bytes: 12 }, last_cycle: null }}
        cycles={[]}
        collectors={[]}
      />,
    );
    expect(screen.getByText(/add the service user to group adm/i)).toBeInTheDocument();
  });
});
