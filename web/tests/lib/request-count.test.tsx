import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { beforeAll, afterAll, afterEach, describe, expect, it, vi } from "vitest";

import { Overview } from "@/components/overview/Overview";
import { AuthContext } from "@/lib/auth";
import { fixture } from "../fixtures";

const NOW = "2026-11-19T12:00:00+00:00";
const counts: Record<string, number> = {};

function countHandler(path: string, payload: unknown) {
  return http.get(`*/${path}`, ({ request }) => {
    const url = new URL(request.url);
    const key = `${url.pathname}${url.search}`;
    counts[key] = (counts[key] ?? 0) + 1;
    return HttpResponse.json(payload as Record<string, unknown>);
  });
}

const server = setupServer(
  countHandler("api/incidents", fixture("incidents")),
  countHandler("api/events", fixture("events")),
  countHandler("api/rules", fixture("rules")),
  countHandler("api/rules/findings", fixture("findings")),
  countHandler("api/baselines", fixture("baselines")),
  countHandler("api/collectors", fixture("collectors")),
  countHandler("api/notifications/channels", fixture("channels")),
  countHandler("api/risk/thresholds", fixture("thresholds")),
  countHandler("api/system/info", fixture("systemInfo")),
  countHandler("api/events/stats", fixture("stats")),
  countHandler("api/events/top", fixture("top")),
  countHandler("api/changes", fixture("changes")),
  countHandler("api/health", fixture("health")),
);

beforeAll(() => {
  Object.keys(counts).forEach((key) => delete counts[key]);
  server.listen();
  class FakeEventSource {
    onmessage: unknown = null;
    onerror: unknown = null;
    close() {}
  }
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  server.close();
  vi.unstubAllGlobals();
});

describe("Overview request loop", () => {
  it("requests each endpoint once on mount", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <AuthContext.Provider value={{ username: "fixture-admin", role: "admin" }}>
          <Overview now={NOW} />
        </AuthContext.Provider>
      </QueryClientProvider>,
    );
    await new Promise((resolve) => setTimeout(resolve, 400));
    for (const [path, count] of Object.entries(counts)) {
      expect(count, `${path} was requested ${count} times`).toBe(1);
    }
  });
});
