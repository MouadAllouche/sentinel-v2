import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DataTable } from "@/components/data-table/DataTable";

const rows = [
  { id: 1, description: "first event" },
  { id: 2, description: "second event" },
];

describe("DataTable", () => {
  beforeEach(() => window.history.replaceState(null, "", "/"));

  it("renders rows and a semantic table", () => {
    render(<DataTable rows={rows} columns={["id", "description"]} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("first event")).toBeInTheDocument();
  });

  it("shows an empty state with no rows", () => {
    render(<DataTable rows={[]} columns={["id", "description"]} />);
    expect(screen.getByText(/no events/i)).toBeInTheDocument();
  });

  it("supports cursor pagination", async () => {
    const onPage = vi.fn();
    const onPrevious = vi.fn();
    render(
      <DataTable
        rows={rows}
        columns={["id", "description"]}
        cursor="5"
        nextCursor="10"
        onPage={onPage}
        onPrevious={onPrevious}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onPage).toHaveBeenCalledWith("10");
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(onPrevious).toHaveBeenCalledTimes(1);
  });

  it("syncs filters to the URL", async () => {
    render(<DataTable rows={rows} columns={["id", "description"]} />);
    await userEvent.type(screen.getByLabelText(/filter/i), "second");
    await waitFor(() => expect(window.location.search).toContain("q=second"));
    expect(screen.getByText("second event")).toBeInTheDocument();
    expect(screen.queryByText("first event")).toBeNull();
  });
});
