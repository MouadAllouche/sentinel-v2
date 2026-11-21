import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import type { ReactNode } from "react";
import { beforeAll, afterAll, afterEach, describe, expect, it, vi } from "vitest";

import { Overview } from "@/components/overview/Overview";
import { IncidentListRoute } from "@/components/incidents/IncidentListRoute";
import { IncidentDetail } from "@/components/incidents/IncidentDetail";
import { AuthContext } from "@/lib/auth";
import { fixture } from "../fixtures";

const NOW = "2026-11-19T12:00:00+00:00";

const server = setupServer(
  http.get("*/api/incidents", () => HttpResponse.json(fixture("incidents"))),
  http.get("*/api/events", () => HttpResponse.json(fixture("events"))),
  http.get("*/api/rules", () => HttpResponse.json(fixture("rules"))),
  http.get("*/api/rules/findings", () => HttpResponse.json(fixture("findings"))),
  http.get("*/api/baselines", () => HttpResponse.json(fixture("baselines"))),
  http.get("*/api/drift/status", () => HttpResponse.json(fixture("drift"))),
  http.get("*/api/health", () => HttpResponse.json(fixture("health"))),
  http.get("*/api/collectors", () => HttpResponse.json(fixture("collectors"))),
  http.get("*/api/notifications/channels", () => HttpResponse.json(fixture("channels"))),
  http.get("*/api/risk/thresholds", () => HttpResponse.json(fixture("thresholds"))),
  http.get("*/api/system/info", () => HttpResponse.json(fixture("systemInfo"))),
  http.get("*/api/events/stats", () => HttpResponse.json(fixture("stats"))),
  http.get("*/api/events/top", () => HttpResponse.json(fixture("top"))),
  http.get("*/api/changes", () => HttpResponse.json(fixture("changes"))),
  http.get("*/api/incidents/1", () => HttpResponse.json(fixture("incident"))),
  http.get("*/api/incidents/1/timeline", () => HttpResponse.json(fixture("timeline"))),
  http.get("*/api/incidents/1/explanation", () => HttpResponse.json(fixture("explanation"))),
  http.get("*/api/incidents/1/graph", () => HttpResponse.json(fixture("graph"))),
  http.get("*/api/incidents/1/notes", () => HttpResponse.json(fixture("notes"))),
  http.get("*/api/incidents/1/history", () => HttpResponse.json(fixture("history"))),
);

beforeAll(() => {
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

function wrapper(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <AuthContext.Provider value={{ username: "fixture-admin", role: "admin" }}>
        {ui}
      </AuthContext.Provider>
    </QueryClientProvider>
  );
}

describe("components rendered with real API fixtures", () => {
  it("renders Overview with real incidents (MITRE objects) without crashing", async () => {
    render(wrapper(<Overview now={NOW} />));
    await waitFor(() => expect(screen.getByText(/highest-risk open incidents/i)).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText(/T1110/i).length).toBeGreaterThan(0));
    expect(screen.getAllByRole("link", { name: /T1110/i }).length).toBeGreaterThan(0);
  });

  it("renders the incident list with real fixtures", async () => {
    render(wrapper(<IncidentListRoute />));
    await waitFor(() => expect(screen.getByRole("table", { name: /incidents matching/i })).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText(/T1110/i).length).toBeGreaterThan(0));
  });

  it("renders incident detail with real fixtures", async () => {
    render(wrapper(<IncidentDetail id={1} />));
    await waitFor(() => expect(screen.getAllByText(/not proof of a single actor/i).length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByRole("list", { name: /incident timeline/i })).toBeInTheDocument());
  });
});
