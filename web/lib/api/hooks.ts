"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "../query-keys";
import { client } from "./client";
import type { paths } from "./schema";

/** Minimal shapes used by the shell; the generated schema defines the wire contract. */
export interface ListPage<T> {
  items: T[];
  next_cursor?: string | null;
  total?: number;
}

export interface EventRecord {
  id: number;
  timestamp: string;
  source: string;
  event_type: string;
  severity: string;
  description: string;
  source_ip?: string | null;
  username?: string | null;
}

export interface IncidentRecord {
  id: number;
  status: string;
  severity: string;
  score?: number;
  title?: string;
  created_at?: string;
  assignee?: string | null;
  mitre?: string[];
  event_ids?: number[];
  first_seen?: string;
  last_seen?: string;
}

export interface RuleRecord {
  id: string;
  name: string;
  enabled: boolean;
  kind: string;
  description?: string;
}

export interface Health {
  status: string;
  [key: string]: unknown;
}

const emptyPage = <T,>(): ListPage<T> => ({ items: [], next_cursor: null });

/** Generic list reader for secondary pages; the generated schema types every path. */
export function useApiList<T>(
  path: keyof paths,
  params: Record<string, unknown> = {},
  enabled = true,
) {
  return useQuery({
    queryKey: ["api", path, params],
    queryFn: async (): Promise<ListPage<T>> => {
      const { data } = await client.GET(path as never, {
        params: { query: params as never },
      } as never);
      const value = data as unknown;
      if (Array.isArray(value)) return { items: value as T[], next_cursor: null };
      if (value && typeof value === "object" && "items" in value) {
        return value as ListPage<T>;
      }
      if (value && typeof value === "object") {
        return {
          items: Object.entries(value).map(([key, item]) => ({ key, ...(item as object) })) as T[],
          next_cursor: null,
        };
      }
      return emptyPage<T>();
    },
    staleTime: 15_000,
    enabled,
  });
}

export function useEvents(
  filters: Record<string, unknown> = {},
  options: { refetchInterval?: number } = {},
) {
  return useQuery({
    queryKey: queryKeys.events(filters),
    queryFn: async (): Promise<ListPage<EventRecord>> => {
      const { data } = await client.GET("/api/events", {
        params: { query: filters as never },
      });
      return (data as ListPage<EventRecord> | undefined) ?? emptyPage<EventRecord>();
    },
    staleTime: 15_000,
    refetchInterval: options.refetchInterval,
  });
}

export function useEvent(id: number) {
  return useQuery({
    queryKey: queryKeys.event(id),
    queryFn: async () => {
      const { data } = await client.GET("/api/events/{event_id}", {
        params: { path: { event_id: id } },
      });
      return data as EventRecord | undefined;
    },
    enabled: Number.isFinite(id) && id > 0,
    staleTime: 30_000,
  });
}

export function useIncidents(filters: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: queryKeys.incidents(filters),
    queryFn: async (): Promise<IncidentRecord[]> => {
      const { data } = await client.GET("/api/incidents", {
        params: { query: filters as never },
      });
      return (data as IncidentRecord[] | undefined) ?? [];
    },
    staleTime: 15_000,
  });
}

export function useIncident(id: number) {
  return useQuery({
    queryKey: queryKeys.incident(id),
    queryFn: async () => {
      const { data } = await client.GET("/api/incidents/{identifier}", {
        params: { path: { identifier: id } },
      });
      return data as IncidentRecord | undefined;
    },
    enabled: Number.isFinite(id) && id > 0,
  });
}

export function useIncidentTimeline(id: number) {
  return useQuery({
    queryKey: queryKeys.timeline(id),
    queryFn: async (): Promise<Array<{ timestamp: string; kind: string; summary: string; fact?: boolean }>> => {
      const { data } = await client.GET("/api/incidents/{identifier}/timeline", {
        params: { path: { identifier: id } },
      });
      return (data as Array<{ timestamp: string; kind: string; summary: string; fact?: boolean }> | undefined) ?? [];
    },
    enabled: Number.isFinite(id) && id > 0,
  });
}

export function useIncidentExplanation(id: number) {
  return useQuery({
    queryKey: queryKeys.explanation(id),
    queryFn: async (): Promise<Record<string, unknown>> => {
      const { data } = await client.GET("/api/incidents/{identifier}/explanation", {
        params: { path: { identifier: id } },
      });
      return (data as Record<string, unknown> | undefined) ?? {};
    },
    enabled: Number.isFinite(id) && id > 0,
  });
}

export function useRules() {
  return useQuery({
    queryKey: queryKeys.rules,
    queryFn: async (): Promise<RuleRecord[]> => {
      const { data } = await client.GET("/api/rules");
      return (data as RuleRecord[] | undefined) ?? [];
    },
    staleTime: 30_000,
  });
}

export function useRule(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.rule(id ?? "new"),
    queryFn: async (): Promise<Record<string, unknown> | undefined> => {
      if (!id) return undefined;
      const { data } = await client.GET("/api/rules/{identifier}", {
        params: { path: { identifier: id } },
      });
      return data as Record<string, unknown> | undefined;
    },
    enabled: Boolean(id),
  });
}

export function useRiskThresholds() {
  return useQuery({
    queryKey: queryKeys.riskThresholds,
    queryFn: async (): Promise<{ low: number; medium: number; high: number }> => {
      const { data } = await client.GET("/api/risk/thresholds");
      const value = (data ?? {}) as { low?: number; medium?: number; high?: number };
      return {
        low: value.low ?? 25,
        medium: value.medium ?? 50,
        high: value.high ?? 75,
      };
    },
    staleTime: 5 * 60 * 1000,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: async (): Promise<Health> => {
      const { data } = await client.GET("/api/health");
      return (data as Health | undefined) ?? { status: "unknown" };
    },
    staleTime: 30_000,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (values: { username: string; password: string }) => {
      const { data } = await client.POST("/api/auth/login", { body: values });
      return data as { username: string; role: "admin" | "viewer" };
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.me });
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await client.POST("/api/auth/logout", {});
    },
    onSuccess: () => {
      queryClient.clear();
    },
  });
}

export function useToggleRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, enabled }: { id: string; enabled: boolean }) => {
      const path = enabled ? "/api/rules/{identifier}/enable" : "/api/rules/{identifier}/disable";
      await client.POST(path, { params: { path: { identifier: id } } });
      return { id, enabled };
    },
    onMutate: async ({ id, enabled }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.rules });
      const previous = queryClient.getQueryData<RuleRecord[]>(queryKeys.rules);
      queryClient.setQueryData<RuleRecord[]>(queryKeys.rules, (rules) =>
        rules?.map((rule) => (rule.id === id ? { ...rule, enabled } : rule)),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(queryKeys.rules, context.previous);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.rules });
    },
  });
}

export interface StatBucket {
  bucket: string;
  severity: string;
  total: number;
}

export function useEventStats(params: {
  bucket: "hour" | "day";
  group_by?: "severity";
  since?: string;
  until?: string;
}) {
  return useQuery({
    queryKey: queryKeys.eventStats(params as Record<string, unknown>),
    queryFn: async (): Promise<StatBucket[]> => {
      const { data } = await client.GET("/api/events/stats", {
        params: { query: params as never },
      });
      if (data && "buckets" in data) {
        return (data as unknown as { buckets: StatBucket[] }).buckets;
      }
      return [];
    },
    staleTime: 15_000,
  });
}

export function useTopValues(field: string, limit = 5) {
  return useQuery({
    queryKey: queryKeys.topValues(field),
    queryFn: async (): Promise<Array<{ value: string; total: number }>> => {
      const { data } = await client.GET("/api/events/top", {
        params: { query: { field, limit } },
      });
      return (data as Array<{ value: string; total: number }> | undefined) ?? [];
    },
    staleTime: 30_000,
  });
}

export function useFindings() {
  return useQuery({
    queryKey: queryKeys.findings,
    queryFn: async (): Promise<Array<Record<string, unknown>>> => {
      const { data } = await client.GET("/api/rules/findings");
      return (data as Array<Record<string, unknown>> | undefined) ?? [];
    },
    staleTime: 30_000,
  });
}

export function useSavedFilters() {
  return useQuery({
    queryKey: queryKeys.savedFilters,
    queryFn: async (): Promise<Array<{ id: number; name: string; page: string; query: Record<string, unknown> }>> => {
      const { data } = await client.GET("/api/filters/saved");
      return (data as Array<{ id: number; name: string; page: string; query: Record<string, unknown> }> | undefined) ?? [];
    },
  });
}

export function useCreateSavedFilter() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { name: string; page: string; query: Record<string, unknown> }) => {
      await client.POST("/api/filters/saved", { body: payload });
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.savedFilters }),
  });
}

export function useDeleteSavedFilter() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (identifier: number) => {
      await client.DELETE("/api/filters/saved/{identifier}", {
        params: { path: { identifier } },
      });
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.savedFilters }),
  });
}

export function useAddAllowlistEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      kind: string;
      value: string;
      scope: string;
      reason: string;
    }) => {
      await client.POST("/api/allowlist", { body: payload });
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.allowlist }),
  });
}

export function useCollectors() {
  return useQuery({
    queryKey: queryKeys.collectors,
    queryFn: async (): Promise<Array<Record<string, unknown>>> => {
      const { data } = await client.GET("/api/collectors");
      return (data as Array<Record<string, unknown>> | undefined) ?? [];
    },
    staleTime: 30_000,
  });
}

export function useCycles() {
  return useQuery({
    queryKey: queryKeys.cycles,
    queryFn: async (): Promise<Array<Record<string, unknown>>> => {
      const { data } = await client.GET("/api/cycles");
      return (data as Array<Record<string, unknown>> | undefined) ?? [];
    },
    staleTime: 30_000,
  });
}

export function useBaselines() {
  return useQuery({
    queryKey: queryKeys.baselines,
    queryFn: async (): Promise<Array<Record<string, unknown>>> => {
      const { data } = await client.GET("/api/baselines");
      return (data as Array<Record<string, unknown>> | undefined) ?? [];
    },
    staleTime: 60_000,
  });
}

export function useEngineRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await client.POST("/api/engine/run", {});
    },
    onSuccess: () => {
      void queryClient.invalidateQueries();
    },
  });
}
