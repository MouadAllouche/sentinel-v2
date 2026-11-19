import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IncidentList } from "@/components/incidents/IncidentList";
import type { IncidentFilters } from "@/lib/incident/filters";

const incidents = Array.from({ length: 12 }, (_, index) => ({
  id: index + 1,
  title: `Incident ${index + 1}`,
  severity: index % 3 === 0 ? "critical" : "high",
  status: "open",
  risk_score: 100 - index,
  primary_ip: "203.0.113.45",
  primary_username: "root",
  first_seen: "2026-11-19T10:00:00+00:00",
  last_seen: "2026-11-19T10:10:00+00:00",
  event_ids: [1, 2],
  mitre: ["T1110"],
  assignee: null,
}));

const filters: IncidentFilters = {
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

describe("IncidentList", () => {
  beforeEach(() => window.history.replaceState(null, "", "/incidents"));

  it("syncs filters and sort to the URL", async () => {
    const onChange = vi.fn();
    render(
      <IncidentList
        incidents={incidents}
        filters={filters}
        onFiltersChange={onChange}
        onBulkStatus={vi.fn()}
        currentRole="admin"
      />,
    );
    await userEvent.click(screen.getByLabelText("Severity critical"));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ severity: ["critical"] }));
    await userEvent.selectOptions(screen.getByLabelText("Sort"), "recent");
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ sort: "recent" }));
  });

  it(
    "requires a reason and typed confirmation for bulk status changes of more than 10",
    async () => {
    const onBulkStatus = vi.fn();
    render(
      <IncidentList
        incidents={incidents}
        filters={filters}
        onFiltersChange={vi.fn()}
        onBulkStatus={onBulkStatus}
        currentRole="admin"
      />,
    );
    const checkboxes = screen.getAllByLabelText(/select incident/i);
    for (const checkbox of checkboxes) await userEvent.click(checkbox);
    await userEvent.click(screen.getByRole("button", { name: /change status/i }));
    await userEvent.selectOptions(screen.getByLabelText("Bulk target status"), "resolved");
    const confirm = screen.getByRole("button", { name: /confirm/i });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/reason/i), "reviewed and closed");
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/type confirm/i), "confirm");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    await waitFor(() =>
      expect(onBulkStatus).toHaveBeenCalledWith(
        incidents.map((incident) => incident.id),
        "resolved",
        "reviewed and closed",
      ),
    );
    },
    20_000,
  );

  it("highlights incidents changed by the live feed", () => {
    render(
      <IncidentList
        incidents={incidents.slice(0, 2)}
        filters={filters}
        onFiltersChange={vi.fn()}
        onBulkStatus={vi.fn()}
        currentRole="viewer"
        highlightedIds={new Set([2])}
      />,
    );
    expect(screen.getByRole("row", { name: /incident 2/i })).toHaveAttribute("data-highlighted", "true");
  });

  it("hides bulk actions for viewers", () => {
    render(
      <IncidentList
        incidents={incidents}
        filters={filters}
        onFiltersChange={vi.fn()}
        onBulkStatus={vi.fn()}
        currentRole="viewer"
      />,
    );
    expect(screen.queryByRole("button", { name: /change status/i })).toBeNull();
  });
});
