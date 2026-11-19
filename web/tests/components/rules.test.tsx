import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import type { TierLike } from "@/lib/rules/helpers";
import { describe, expect, it, vi } from "vitest";
import { AllowlistDialog } from "@/components/allowlist/AllowlistDialog";
import { ConditionBuilder } from "@/components/conditions/ConditionBuilder";
import { PreviewPanel } from "@/components/rules/PreviewPanel";
import { RulesList } from "@/components/rules/RulesList";
import { SaveDiffDialog } from "@/components/rules/SaveDiffDialog";
import { TierEditor } from "@/components/rules/TierEditor";
import { VersionHistory } from "@/components/rules/VersionHistory";
import { OverrideList } from "@/components/severity/OverrideList";
import { ReapplyPanel } from "@/components/severity/ReapplyPanel";
import { SeverityDefaults } from "@/components/severity/SeverityDefaults";

const tier = { label: "Low", count: 5, window_seconds: 600, severity: "medium", points: 5 };

describe("rules, severity and allowlist UI", () => {
  it("adds, removes and reorders tiers with unit conversion", async () => {
    let tiers: TierLike[] = [tier, { ...tier, label: "High", count: 20, severity: "high" }];
    function Stateful() {
      const [value, setValue] = useState<TierLike[]>(tiers);
      tiers = value;
      return <TierEditor tiers={value} onChange={setValue} match={{ event_types: ["failed_login"], group_by: ["source_ip"] }} />;
    }
    render(<Stateful />);
    expect(screen.getByText(/if ≥ 5 failed logins/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /add tier/i }));
    expect(tiers).toHaveLength(3);
    await userEvent.click(screen.getAllByRole("button", { name: /move up/i })[1]!);
    expect(tiers[0]?.label).toBe("High");
    await userEvent.click(screen.getAllByRole("button", { name: /remove tier/i })[0]!);
    expect(tiers).toHaveLength(2);
  });

  it("refuses more than ten tiers", async () => {
    const many = Array.from({ length: 10 }, (_, index) => ({ ...tier, label: `T${index}` }));
    render(<TierEditor tiers={many} onChange={vi.fn()} match={{ event_types: [], group_by: [] }} />);
    expect(screen.getByRole("button", { name: /add tier/i })).toBeDisabled();
  });

  it("disables builder controls for viewers", () => {
    render(<TierEditor tiers={[tier]} onChange={vi.fn()} match={{ event_types: [] }} disabled />);
    expect(screen.getByLabelText("Tier 1 count")).toBeDisabled();
    expect(screen.getByRole("button", { name: /add tier/i })).toBeDisabled();
  });

  it("builds nested conditions and shows plain-language describe text", async () => {
    const onChange = vi.fn();
    render(<ConditionBuilder value={{ all: [] }} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /add condition/i }));
    expect(onChange).toHaveBeenCalled();
    expect(screen.getByText(/describe|where/i)).toBeInTheDocument();
  });

  it("hides admin actions for viewers and shows generated summaries", () => {
    render(
      <RulesList
        rules={[{ id: "ssh", name: "SSH", enabled: true, kind: "threshold", summary: "Failed logins: ≥5 in 10 min → medium", builtin: true, version: 2 }]}
        filters={{ kind: "", enabled: null, search: "", builtin: null, noisy: false }}
        onFiltersChange={vi.fn()}
        onToggle={vi.fn()}
        onDuplicate={vi.fn()}
        onReset={vi.fn()}
        onDelete={vi.fn()}
        onImport={vi.fn()}
        onExport={vi.fn()}
        currentRole="viewer"
      />,
    );
    expect(screen.getByText(/failed logins: ≥5 in 10 min/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /new rule/i })).toBeNull();
  });

  it("renders preview states with the noise heuristic", () => {
    const { rerender } = render(<PreviewPanel result={null} loading={false} onRangeChange={vi.fn()} />);
    expect(screen.getByText(/no data in this range/i)).toBeInTheDocument();
    rerender(
      <PreviewPanel
        result={{ total_findings: 17, noise_per_day: 1.7, by_severity: { medium: 17 }, groups: [], samples: [] }}
        loading={false}
        onRangeChange={vi.fn()}
      />,
    );
    expect(screen.getAllByText(/17/).length).toBeGreaterThan(0);
    expect(screen.getByText(/1\.7 findings\/day/)).toBeInTheDocument();
  });

  it("shows a save diff before confirming", async () => {
    const onConfirm = vi.fn();
    render(
      <SaveDiffDialog
        diffs={[{ path: "name", before: "Old", after: "New" }]}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getAllByText(/"New"/).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: /confirm/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("restores a previous version", async () => {
    const onRestore = vi.fn();
    render(
      <VersionHistory
        versions={[{ version: 1, created_at: "2026-11-19T10:00:00+00:00", actor: "admin" }]}
        onRestore={onRestore}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /restore version 1/i }));
    expect(onRestore).toHaveBeenCalledWith(1);
  });

  it("batches severity default changes and requires typed reset confirmation", async () => {
    const onSave = vi.fn();
    render(
      <SeverityDefaults
        rows={[{ event_type: "failed_login", severity: "low", points: 5, events_24h: 12, modified: true, enabled: true }]}
        dirty
        onSave={onSave}
        onResetAll={vi.fn()}
        onChange={vi.fn()}
        onResetRow={vi.fn()}
        currentRole="admin"
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    expect(onSave).toHaveBeenCalled();
  });

  it("edits severity defaults through the table", async () => {
    const onChange = vi.fn();
    render(
      <SeverityDefaults
        rows={[{ event_type: "failed_login", severity: "low", points: 5, events_24h: 12, modified: true, enabled: true }]}
        dirty={false}
        onSave={vi.fn()}
        onResetAll={vi.fn()}
        onChange={onChange}
        onResetRow={vi.fn()}
        currentRole="admin"
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Severity for failed_login"), "medium");
    expect(onChange).toHaveBeenCalledWith(0, { severity: "medium" });
  });

  it("reorders overrides with keyboard-accessible controls", async () => {
    const onReorder = vi.fn();
    render(
      <OverrideList
        overrides={[{ id: 1, name: "First" }, { id: 2, name: "Second" }]}
        onReorder={onReorder}
        currentRole="admin"
      />,
    );
    await userEvent.click(screen.getAllByRole("button", { name: /move down/i })[0]!);
    expect(onReorder).toHaveBeenCalledWith([2, 1]);
  });

  it("requires typed confirmation for re-apply", async () => {
    const onApply = vi.fn();
    render(
      <ReapplyPanel
        preview={{ changed: 12, by_severity: { low: 5, medium: 7 } }}
        onPreview={vi.fn()}
        onApply={onApply}
        currentRole="admin"
      />,
    );
    const button = screen.getByRole("button", { name: /apply to existing events/i });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/type confirm/i), "confirm");
    expect(button).toBeEnabled();
    await userEvent.click(button);
    expect(onApply).toHaveBeenCalled();
  });

  it("requires a reason and validates expiry in the allowlist dialog", async () => {
    const onSave = vi.fn();
    render(<AllowlistDialog onSave={onSave} onCancel={vi.fn()} />);
    const confirm = screen.getByRole("button", { name: /save entry/i });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Allowlist value"), "203.0.113.45");
    await userEvent.type(screen.getByLabelText(/reason/i), "expected scanner");
    expect(confirm).toBeEnabled();
    await userEvent.selectOptions(screen.getByLabelText(/expiry/i), "never");
    expect(screen.getByText(/never expires/i)).toBeInTheDocument();
    await userEvent.click(confirm);
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ reason: "expected scanner" }));
  });
});
