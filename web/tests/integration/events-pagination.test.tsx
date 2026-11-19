import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { useState } from "react";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { useApiList } from "@/lib/api/hooks";

const firstPage = [
  { id: 1, description: "one" },
  { id: 2, description: "two" },
];
const secondPage = [
  { id: 3, description: "three" },
  { id: 4, description: "four" },
];

const server = setupServer(
  http.get("*/api/events", ({ request }) => {
    const cursor = new URL(request.url).searchParams.get("cursor");
    return HttpResponse.json({
      items: cursor ? secondPage : firstPage,
      next_cursor: cursor ? null : "cursor-2",
    });
  }),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function PagedEvents() {
  const [cursor, setCursor] = useState<string | null>(null);
  const query = useApiList<{ id: number; description: string }>(
    "/api/events",
    cursor ? { cursor } : {},
  );
  return (
    <div>
      <div data-testid="ids">
        {(query.data?.items ?? []).map((item) => (
          <span key={item.id}>{item.id}</span>
        ))}
      </div>
      <button type="button" onClick={() => setCursor(query.data?.next_cursor ?? null)}>
        Next
      </button>
    </div>
  );
}

describe("events pagination (MSW)", () => {
  it("has no duplicates or gaps across cursor pages", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PagedEvents />
      </QueryClientProvider>,
    );
    const ids = screen.getByTestId("ids");
    await screen.findByText("1");
    expect(ids.textContent).toBe("12");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("3");
    expect(ids.textContent).toBe("34");
    const unique = new Set(
      Array.from(ids.querySelectorAll("span")).map((span) => span.textContent),
    );
    expect(unique.size).toBe(2);
  });
});
