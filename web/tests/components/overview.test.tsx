import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { HealthStrip } from "@/components/overview/HealthStrip";
import { FirstRunChecklist } from "@/components/overview/FirstRunChecklist";
import { KpiCard } from "@/components/overview/KpiCard";
import { LiveFeed } from "@/components/overview/LiveFeed";
import { TopList } from "@/components/overview/TopList";

const event = {
  id: 1,
  timestamp: "2026-11-19T10:00:00+00:00",
  event_type: "failed_login",
  severity: "high",
  description: "failure",
};

describe("Overview components", () => {
  it("renders a KPI with a delta and a link", () => {
    render(
      <KpiCard
        label="Events (24 h)"
        value={12}
        delta="+2 (+20%)"
        href="/events?preset=24h"
      />,
    );
    expect(screen.getByText("+2 (+20%)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /events/i })).toHaveAttribute(
      "href",
      "/events?preset=24h",
    );
  });

  it("offers a retry on a KPI error", async () => {
    const onRetry = vi.fn();
    render(
      <KpiCard label="Events (24 h)" value={0} href="/events" error="Load failed" onRetry={onRetry} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows a first-run checklist when there are no events", () => {
    render(<FirstRunChecklist />);
    expect(screen.getByText(/run the engine/i)).toBeInTheDocument();
    expect(screen.getByText(/check collector warnings/i)).toBeInTheDocument();
  });

  it("pauses and resumes the live feed with an aria-live status", async () => {
    const onTogglePause = vi.fn();
    render(
      <LiveFeed
        events={[event]}
        status="live"
        paused={false}
        onTogglePause={onTogglePause}
        now="2026-11-19T10:05:00+00:00"
      />,
    );
    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(screen.getByRole("list")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /pause/i }));
    expect(onTogglePause).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["reconnecting", "Reconnecting…"],
    ["polling", "Polling"],
  ])("shows the %s connection status", (status, label) => {
    render(
      <LiveFeed
        events={[]}
        status={status as "reconnecting" | "polling"}
        paused={false}
        onTogglePause={vi.fn()}
        now="2026-11-19T10:05:00+00:00"
      />,
    );
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("shows collector warnings and links to health", () => {
    render(
      <HealthStrip
        health={{ status: "ok" }}
        collectors={[{ name: "auth.log", status: "warning", warnings: ["permission denied"] }]}
        baselines={{ mature: 6, total: 24 }}
        notificationsEnabled={false}
      />,
    );
    expect(screen.getByText(/permission denied/i)).toBeInTheDocument();
    expect(screen.getByText(/learning: 6\/24 h/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /health/i })).toHaveAttribute("href", "/health");
  });

  it("links top values to filtered events", () => {
    render(
      <TopList
        title="Top source IPs"
        field="source_ip"
        items={[{ value: "203.0.113.45", total: 7 }]}
      />,
    );
    expect(screen.getByRole("link", { name: /203.0.113.45/ })).toHaveAttribute(
      "href",
      "/events?source_ip=203.0.113.45",
    );
  });
});
