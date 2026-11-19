import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CaveatBanner } from "@/components/incidents/CaveatBanner";
import { EntityGraph } from "@/components/incidents/EntityGraph";
import { ExplanationPanel } from "@/components/incidents/ExplanationPanel";
import { IncidentHeader } from "@/components/incidents/IncidentHeader";
import { MergedBanner } from "@/components/incidents/MergedBanner";
import { NotesPanel } from "@/components/incidents/NotesPanel";
import { ScoreReasonsTable } from "@/components/incidents/ScoreReasonsTable";
import { StatusHistory } from "@/components/incidents/StatusHistory";
import { StatusMenu } from "@/components/incidents/StatusMenu";
import { Timeline } from "@/components/incidents/Timeline";
import { WhatIfPanel } from "@/components/incidents/WhatIfPanel";

const incident = {
  id: 7,
  title: "Possible credential guessing",
  severity: "high",
  status: "open",
  risk_score: 100,
  first_seen: "2026-11-19T10:00:00+00:00",
  last_seen: "2026-11-19T10:10:00+00:00",
  mitre: ["T1110"],
  primary_ip: "203.0.113.45",
  updated_at: "2026-11-19T10:10:00+00:00",
};

const entries = [
  {
    timestamp: "2026-11-19T10:00:03+00:00",
    event_id: 1,
    event_type: "failed_login",
    severity: "low",
    summary: "failed password for root",
    kind: "observed",
    relation_to_previous: null,
    rule_findings: [],
  },
  {
    timestamp: "2026-11-19T10:03:15+00:00",
    event_id: null,
    event_type: "inferred",
    severity: "medium",
    summary: "Possible credential guessing",
    kind: "inferred",
    relation_to_previous: {
      reason: "time proximity only",
      strength: "weak",
      link_kind: "temporal",
    },
    rule_findings: [{ rule_id: "ssh-bruteforce-by-ip", tier_label: "Low" }],
  },
];

describe("incident investigation components", () => {
  it("always shows the grouping caveat on the header", () => {
    render(<IncidentHeader incident={incident} currentRole="viewer" onStatusChange={vi.fn()} />);
    expect(screen.getByText(/not proof of a single actor/i)).toBeInTheDocument();
    expect(screen.getAllByText(/indicative/i).length).toBeGreaterThan(0);
    expect(CaveatBanner).toBeDefined();
  });

  it("offers only allowed transitions and requires a reason", async () => {
    const onChange = vi.fn();
    render(<StatusMenu status="investigating" currentRole="admin" onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /change status/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /resolved/i }));
    expect(screen.getByRole("button", { name: /confirm/i })).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox", { name: "Reason" }), "verified false alarm");
    await userEvent.click(screen.getByRole("button", { name: /confirm/i }));
    expect(onChange).toHaveBeenCalledWith("resolved", "verified false alarm");
  });

  it("hides status controls for viewers", () => {
    render(<StatusMenu status="open" currentRole="viewer" onChange={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /change status/i })).toBeNull();
  });

  it("shows a conflict message when the incident changed", () => {
    render(<StatusMenu status="open" currentRole="admin" onChange={vi.fn()} error="conflict" />);
    expect(screen.getByText(/incident changed, reload/i)).toBeInTheDocument();
  });

  it("orders the timeline, formats gaps and labels weak links in text", () => {
    render(<Timeline entries={[...entries].reverse()} />);
    const list = screen.getByRole("list", { name: /incident timeline/i });
    expect(list.querySelectorAll("li")[0]?.textContent).toContain("failed password");
    expect(screen.getByText(/\+3m 12s/)).toBeInTheDocument();
    expect(screen.getByText(/Observed/)).toBeInTheDocument();
    expect(screen.getByText(/Inferred/)).toBeInTheDocument();
    expect(screen.getByText(/time proximity only/)).toBeInTheDocument();
    expect(screen.getByTestId("relation-weak").className).toContain("border-dashed");
  });

  it("collapses repeated events in the timeline", async () => {
    render(
      <Timeline
        collapsed
        entries={[
          { timestamp: "2026-11-19T10:00:03+00:00", event_id: 1, event_type: "failed_login", severity: "low", summary: "a" },
          { timestamp: "2026-11-19T10:01:00+00:00", event_id: 2, event_type: "failed_login", severity: "low", summary: "b" },
        ]}
      />,
    );
    expect(screen.getByText(/×2 failed_login between/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /expand 2 events/i }));
    expect(screen.getByText("b")).toBeInTheDocument();
  });

  it("lists strong and weak grouping reasons with caveats", () => {
    render(
      <ExplanationPanel
        explanation={{
          grouping: { strong: ["Same source IP 203.0.113.45"], weak: ["time proximity only"] },
          rules: [{ rule_id: "ssh-bruteforce-by-ip", tier_label: "Low" }],
          caveats: ["Grouping is based on shared attributes and time proximity and is not proof."],
        }}
      />,
    );
    expect(screen.getByText(/same source ip/i)).toBeInTheDocument();
    expect(screen.getByText(/weak: time proximity only/i)).toBeInTheDocument();
    expect(screen.getByText(/not proof/i)).toBeInTheDocument();
  });

  it("shows the running total in the reasons table", () => {
    render(
      <ScoreReasonsTable
        reasons={[{ rule_id: "r1", tier_label: "Low", points: 15, severity: "low", explanation: "x" }]}
        summary={{ raw_score: 15, score: 15, capped: false, severity: "low", severity_basis: "score band" }}
      />,
    );
    expect(screen.getByText(/running total/i)).toBeInTheDocument();
    expect(screen.getByText(/score band/i)).toBeInTheDocument();
  });

  it("recalculates the what-if score and labels it a simulation", async () => {
    render(
      <WhatIfPanel
        reasons={[
          { rule_id: "world-writable-sensitive-file", points: 40, severity: "critical" },
          { rule_id: "success-after-failures", points: 20, severity: "high" },
        ]}
        thresholds={{ medium: 20, high: 40, critical: 70 }}
      />,
    );
    expect(screen.getByText(/simulation, not saved/i)).toBeInTheDocument();
    expect(screen.getByTestId("what-if-score")).toHaveTextContent("60");
    await userEvent.click(screen.getByLabelText(/world-writable-sensitive-file/i));
    expect(screen.getByTestId("what-if-score")).toHaveTextContent("20");
  });

  it("renders an accessible entity table alongside the graph", () => {
    render(
      <EntityGraph
        nodes={[{ id: "source_ip:203.0.113.45", kind: "source_ip", value: "203.0.113.45", count: 3 }]}
        edges={[
          {
            a: "source_ip:203.0.113.45",
            b: "username:root",
            strength: "weak",
            reason: "time proximity only",
          },
        ]}
      />,
    );
    expect(screen.getByRole("table", { name: /entities and relationships/i })).toBeInTheDocument();
    expect(screen.getByText(/time proximity only/)).toBeInTheDocument();
  });

  it("renders notes inertly and hides the add form for viewers", () => {
    const { container, rerender } = render(
      <NotesPanel notes={[{ id: 1, author: "admin", body: "<script>x</script> **safe**", created_at: "2026-11-19T10:00:00+00:00" }]} currentRole="viewer" onAdd={vi.fn()} />,
    );
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText(/safe/)).toBeInTheDocument();
    rerender(
      <NotesPanel notes={[]} currentRole="admin" onAdd={vi.fn()} />,
    );
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("shows status history with actor and reason", () => {
    render(
      <StatusHistory
        entries={[{ id: 1, from_status: "open", to_status: "investigating", actor: "admin", reason: "reviewing", at: "2026-11-19T10:00:00+00:00" }]}
      />,
    );
    expect(screen.getByText(/reviewing/)).toBeInTheDocument();
    expect(screen.getByText(/admin/)).toBeInTheDocument();
  });

  it("links merged incidents to their target", () => {
    render(<MergedBanner targetId={9} />);
    expect(screen.getByRole("link", { name: /incident #9/i })).toHaveAttribute("href", "/incidents/9");
  });
});
