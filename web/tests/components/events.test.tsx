import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render as rtlRender, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { EventFilters } from "@/lib/filters";
import { EventDrawer } from "@/components/events/EventDrawer";
import { EventExport } from "@/components/events/EventExport";
import { EventTable } from "@/components/events/EventTable";
import { FilterBar } from "@/components/events/FilterBar";
import { NewEventsBanner } from "@/components/events/NewEventsBanner";
import { SavedFilters } from "@/components/events/SavedFilters";
import { emptyFilters } from "@/lib/filters";

function render(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const event = {
  id: 42,
  timestamp: "2026-11-19T10:00:00+00:00",
  event_type: "failed_login",
  severity: "high",
  severity_source: "override:17",
  description: "failed password for root",
  source: "auth.log",
  username: "root",
  source_ip: "203.0.113.45",
  process_name: "sshd",
  score: 12,
  enrichment: { ip_scope: "external", flags: ["repeat"] },
};

describe("Events explorer components", () => {
  it("syncs filter changes and rejects invalid CIDR input", async () => {
    const onChange = vi.fn();
    function Stateful() {
      const [filters, setFilters] = useState<EventFilters>(emptyFilters);
      return (
        <FilterBar
          filters={filters}
          onChange={(next) => {
            setFilters(next);
            onChange(next);
          }}
        />
      );
    }
    render(<Stateful />);
    await userEvent.type(screen.getByLabelText("Search events"), "root");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ search: "root" }));
    await userEvent.type(screen.getByLabelText("Source CIDR"), "999.0.0.0/33");
    expect(screen.getByText(/enter a valid cidr/i)).toBeInTheDocument();
  });

  it("applies a saved filter", async () => {
    const onApply = vi.fn();
    render(
      <SavedFilters
        saved={[{ id: 1, name: "SSH failures", page: "events", query: { source_ip: "203.0.113.45" } }]}
        onApply={onApply}
        onSave={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /apply ssh failures/i }));
    expect(onApply).toHaveBeenCalledWith({ source_ip: "203.0.113.45" });
  });

  it.each([
    ["default", "default severity"],
    ["override:17", "override 17"],
    ["rule:ssh-bruteforce", "rule ssh-bruteforce"],
  ])("explains the %s severity source in the drawer", (source, explanation) => {
    render(
      <EventDrawer
        event={{ ...event, severity_source: source }}
        onClose={vi.fn()}
        findings={[{ rule_id: "ssh-bruteforce", tier_label: "Low" }]}
        incidents={[{ id: 7 }]}
      />,
    );
    expect(screen.getByTestId("severity-source")).toHaveTextContent(explanation);
    expect(screen.getByRole("link", { name: /severity/i })).toHaveAttribute("href", "/severity");
    expect(screen.getByRole("button", { name: /show raw data/i })).toBeInTheDocument();
    expect(screen.getAllByText(/ssh-bruteforce/i).length).toBeGreaterThan(0);
  });

  it("hides admin actions for viewers", () => {
    render(<EventDrawer event={event} onClose={vi.fn()} roleOfUser="viewer" />);
    expect(screen.queryByRole("button", { name: /add allowlist/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /create rule/i })).toBeNull();
  });

  it("requires a reason before confirming an allowlist entry", async () => {
    render(<EventDrawer event={event} onClose={vi.fn()} roleOfUser="admin" />);
    await userEvent.click(screen.getByRole("button", { name: /add allowlist/i }));
    const confirm = screen.getByRole("button", { name: "Confirm" });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/reason/i), "known scanner");
    expect(confirm).toBeEnabled();
  });

  it("exports exactly the current filter semantics", async () => {
    let href = "";
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        href = this.href;
      });
    render(<EventExport filters={emptyFilters} />);
    await userEvent.click(screen.getByRole("button", { name: /export csv/i }));
    expect(href).not.toContain("allowlisted=true");

    render(
      <EventExport
        filters={{ ...emptyFilters, allowlisted: false, in_incident: true }}
      />,
    );
    await userEvent.click(screen.getAllByRole("button", { name: /export csv/i })[1]!);
    expect(href).toContain("allowlisted=false");
    expect(href).toContain("in_incident=true");
    click.mockRestore();
  });

  it("shows the new-events banner", async () => {
    const onLoad = vi.fn();
    render(<NewEventsBanner count={5} onLoad={onLoad} />);
    await userEvent.click(screen.getByRole("button", { name: /5 new events/i }));
    expect(onLoad).toHaveBeenCalledTimes(1);
  });

  it("supports keyboard search, selection and drawer opening", async () => {
    const onSelect = vi.fn();
    render(
      <>
        <FilterBar filters={emptyFilters} onChange={vi.fn()} />
        <EventTable
          events={[event, { ...event, id: 43 }]}
          onSelect={onSelect}
          selectedId={null}
          filters={emptyFilters}
          onFiltersChange={vi.fn()}
        />
      </>,
    );
    await userEvent.keyboard("/");
    expect(screen.getByLabelText("Search events")).toHaveFocus();
    await userEvent.click(screen.getByRole("table"));
    await userEvent.keyboard("j{Enter}");
    expect(onSelect).toHaveBeenCalledWith(event);
    await userEvent.keyboard("{Escape}");
  });
});
