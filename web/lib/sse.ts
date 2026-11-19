"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

export type StreamStatus = "connecting" | "live" | "reconnecting" | "polling" | "paused";

export interface StreamMessage {
  type: string;
  id?: number | string;
  at?: string;
}

const MAX_BACKOFF_MS = 30_000;
const POLL_INTERVAL_MS = 10_000;

/**
 * Subscribe to /api/stream, invalidate queries on change events, reconnect with
 * backoff, pause when the tab is hidden, and fall back to polling if streaming
 * cannot be established (for example through a buffering proxy).
 */
export function useLiveUpdates(
  options: { paused?: boolean; onMessage?: (message: StreamMessage) => void } = {},
): { status: StreamStatus } {
  const paused = options.paused ?? false;
  const onMessage = options.onMessage;
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [retry, setRetry] = useState(0);
  const failures = useRef(0);
  const source = useRef<EventSource | null>(null);
  const timers = useRef<Array<ReturnType<typeof setTimeout>>>([]);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastChange = useRef(0);

  const invalidate = useCallback(
    (_message: StreamMessage) => {
      // Change events are ids only; refetching active queries is the safe
      // default and keeps this hook independent of individual page filters.
      void queryClient.invalidateQueries();
    },
    [queryClient],
  );

  const stopPolling = useCallback(() => {
    if (pollTimer.current !== null) clearInterval(pollTimer.current);
    pollTimer.current = null;
  }, []);

  const startPolling = useCallback(() => {
    setStatus("polling");
    const poll = async () => {
      if (document.visibilityState === "hidden") return;
      try {
        const response = await fetch(`/api/changes?since=${lastChange.current}`, {
          credentials: "include",
        });
        if (response.ok) {
          const body = (await response.json()) as {
            items?: Array<{ id: number; ref_id?: number; type?: string }>;
          };
          for (const item of body.items ?? []) {
            lastChange.current = Math.max(lastChange.current, item.id);
            const message = { type: item.type ?? "change", id: item.ref_id ?? item.id };
            invalidate(message);
            onMessage?.(message);
          }
        }
      } catch {
        // Keep the degraded status visible instead of claiming a live stream.
      }
    };
    void poll();
    if (pollTimer.current === null) {
      pollTimer.current = setInterval(() => void poll(), POLL_INTERVAL_MS);
      timers.current.push(pollTimer.current);
    }
  }, [invalidate, onMessage]);

  const connect = useCallback(() => {
    stopPolling();
    if (document.visibilityState === "hidden") {
      setStatus("paused");
      return;
    }
    if (typeof EventSource === "undefined") {
      startPolling();
      return;
    }
    const es = new EventSource("/api/stream");
    source.current = es;
    es.onmessage = (event: MessageEvent<string>) => {
      failures.current = 0;
      setStatus("live");
      // The SSE frame id is the change-row id; the data id is the entity id.
      const frameId = Number((event as MessageEvent<string> & { lastEventId?: string }).lastEventId);
      if (Number.isFinite(frameId) && frameId > 0) {
        lastChange.current = Math.max(lastChange.current, frameId);
      }
      try {
        const message = JSON.parse(event.data) as StreamMessage;
        invalidate(message);
        onMessage?.(message);
      } catch {
        // Ignore malformed frames; the next valid one invalidates again.
      }
    };
    es.onerror = () => {
      es.close();
      failures.current += 1;
      if (failures.current >= 3) {
        startPolling();
        return;
      }
      setStatus("reconnecting");
      setRetry((current) => current + 1);
    };
  }, [invalidate, onMessage, startPolling, stopPolling]);

  useEffect(() => {
    if (paused) {
      source.current?.close();
      source.current = null;
      stopPolling();
      queueMicrotask(() => setStatus("paused"));
      return;
    }
    let active = true;
    queueMicrotask(() => {
      if (active) connect();
    });
    const onVisibility = () => {
      if (document.visibilityState === "hidden" || paused) {
        source.current?.close();
        setStatus("paused");
      } else {
        failures.current = 0;
        connect();
      }
    };
    const onUnauthorized = () => {
      queryClient.clear();
      window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("sentinel:unauthorized", onUnauthorized);
    return () => {
      active = false;
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("sentinel:unauthorized", onUnauthorized);
      source.current?.close();
      source.current = null;
      stopPolling();
      for (const timer of timers.current) clearTimeout(timer);
      timers.current = [];
    };
  }, [connect, paused, queryClient, stopPolling]);

  useEffect(() => {
    if (retry === 0 || paused) return;
    const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** (failures.current - 1));
    const timer = setTimeout(() => {
      if (document.visibilityState === "visible") connect();
    }, delay);
    timers.current.push(timer);
    return () => clearTimeout(timer);
  }, [retry, connect, paused]);

  return { status };
}
