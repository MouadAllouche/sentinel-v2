import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useLiveUpdates } from "@/lib/sse";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  close = vi.fn();
}

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient();
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useLiveUpdates", () => {
  afterEach(() => {
    FakeEventSource.instances = [];
    vi.useRealTimers();
  });

  it("subscribes to the stream and invalidates queries on messages", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const withClient = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useLiveUpdates(), { wrapper: withClient });
    await waitFor(() => expect(FakeEventSource.instances[0]).toBeDefined());
    expect(FakeEventSource.instances[0]?.url).toBe("/api/stream");
    act(() => {
      FakeEventSource.instances[0]?.onmessage?.(
        { data: JSON.stringify({ type: "incident.created", id: 1 }) } as MessageEvent,
      );
    });
    await waitFor(() => expect(result.current.status).toBe("live"));
    expect(invalidate).toHaveBeenCalled();
  });

  it("reports reconnecting when the stream fails", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { result } = renderHook(() => useLiveUpdates(), { wrapper });
    await waitFor(() => expect(FakeEventSource.instances[0]).toBeDefined());
    const timeoutSpy = vi.spyOn(globalThis, "setTimeout");
    act(() => FakeEventSource.instances[0]?.onerror?.());
    await waitFor(() => expect(result.current.status).toBe("reconnecting"));
    expect(timeoutSpy).toHaveBeenCalledWith(expect.any(Function), 1000);
    timeoutSpy.mockRestore();
  });

  it("does not open a stream while paused", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { result } = renderHook(() => useLiveUpdates({ paused: true }), { wrapper });
    await waitFor(() => expect(result.current.status).toBe("paused"));
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("forwards the entity id from the polling fallback", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onMessage = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ items: [{ id: 99, ref_id: 7, type: "incident.status_changed" }] }),
          { status: 200 },
        ),
      ),
    );
    renderHook(() => useLiveUpdates({ onMessage }), { wrapper });
    await waitFor(() => expect(FakeEventSource.instances[0]).toBeDefined());
    act(() => {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        FakeEventSource.instances[0]?.onerror?.();
      }
    });
    await waitFor(() => expect(onMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: "incident.status_changed", id: 7 }),
    ));
  });

  it("falls back to polling after three stream failures", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useLiveUpdates(), { wrapper });
    await waitFor(() => expect(FakeEventSource.instances[0]).toBeDefined());
    act(() => {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        FakeEventSource.instances[0]?.onerror?.();
      }
    });
    await waitFor(() => expect(result.current.status).toBe("polling"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("/api/changes?since=");
  });
});
