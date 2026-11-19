"use client";

import { EVENT_SOURCES, EVENT_TYPE_GROUPS } from "@/lib/events";
import { type EventFilters, isValidCidr, rangeForPreset } from "@/lib/filters";
import { Button } from "@/components/ui/primitives";

const SEVERITIES = ["low", "medium", "high", "critical"];

export function FilterBar({
  filters,
  onChange,
}: {
  filters: EventFilters;
  onChange: (filters: EventFilters) => void;
}) {
  const update = (changes: Partial<EventFilters>) => onChange({ ...filters, ...changes });
  const toggle = (key: "event_type" | "severity" | "source", value: string) => {
    const current = filters[key];
    update({
      [key]: current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    } as Partial<EventFilters>);
  };
  const cidrInvalid = filters.source_cidr.length > 0 && !isValidCidr(filters.source_cidr);

  return (
    <section aria-label="Event filters" className="space-y-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex-1 min-w-48 text-sm">
          Search events
          <input
            id="event-search"
            aria-label="Search events"
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={filters.search}
            onChange={(event) => update({ search: event.target.value })}
            placeholder="Free-text search"
          />
        </label>
        <label className="text-sm">
          Time range
          <select
            aria-label="Time range"
            className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={filters.preset}
            onChange={(event) => {
              const preset = event.target.value;
              if (preset === "custom") {
                update({ preset });
                return;
              }
              update({ preset, ...rangeForPreset(preset, new Date().toISOString()) });
            }}
          >
            <option value="15m">15 m</option>
            <option value="1h">1 h</option>
            <option value="24h">24 h</option>
            <option value="7d">7 d</option>
            <option value="30d">30 d</option>
            <option value="custom">custom</option>
          </select>
        </label>
        <label className="text-sm">
          Source IP / CIDR
          <input
            aria-label="Source CIDR"
            className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={filters.source_cidr || filters.source_ip}
            onChange={(event) =>
              update(
                event.target.value.includes("/")
                  ? { source_cidr: event.target.value, source_ip: "" }
                  : { source_ip: event.target.value, source_cidr: "" },
              )
            }
            placeholder="203.0.113.0/24"
          />
        </label>
        {cidrInvalid ? (
          <p role="alert" className="w-full text-sm text-red-700 dark:text-red-300">
            Enter a valid CIDR network (for example 203.0.113.0/24).
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-4 text-sm">
        <fieldset>
          <legend className="font-medium">Severity</legend>
          <div className="flex flex-wrap gap-2">
            {SEVERITIES.map((severity) => (
              <label key={severity} className="inline-flex items-center gap-1">
                <input
                  type="checkbox"
                  aria-label={`Severity ${severity}`}
                  checked={filters.severity.includes(severity)}
                  onChange={() => toggle("severity", severity)}
                />
                {severity}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend className="font-medium">Event type</legend>
          <div className="flex flex-wrap gap-3">
            {Object.entries(EVENT_TYPE_GROUPS).map(([group, types]) => (
              <div key={group}>
                <p className="text-xs text-slate-500">{group}</p>
                {types.map((type) => (
                  <label key={type} className="mr-2 inline-flex items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      aria-label={`Event type ${type}`}
                      checked={filters.event_type.includes(type)}
                      onChange={() => toggle("event_type", type)}
                    />
                    {type}
                  </label>
                ))}
              </div>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend className="font-medium">Source</legend>
          <div className="flex flex-wrap gap-2">
            {EVENT_SOURCES.map((source) => (
              <label key={source} className="inline-flex items-center gap-1 text-xs">
                <input
                  type="checkbox"
                  aria-label={`Source ${source}`}
                  checked={filters.source.includes(source)}
                  onChange={() => toggle("source", source)}
                />
                {source}
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-sm">
        <label className="inline-flex items-center gap-1">
          Since
          <input
            aria-label={filters.timezone === "utc" ? "Since (UTC)" : "Since (local)"}
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={filters.since}
            onChange={(event) => update({ since: event.target.value, preset: "custom" })}
            placeholder="2026-11-19T00:00:00+00:00"
          />
        </label>
        <label className="inline-flex items-center gap-1">
          Until
          <input
            aria-label={filters.timezone === "utc" ? "Until (UTC)" : "Until (local)"}
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={filters.until}
            onChange={(event) => update({ until: event.target.value, preset: "custom" })}
            placeholder="2026-11-20T00:00:00+00:00"
          />
        </label>
        <Button
          aria-label="Toggle UTC/local time"
          onClick={() => {
            const timezone = filters.timezone === "utc" ? "local" : "utc";
            const convert = (value: string) => {
              if (!value) return "";
              const date = new Date(value);
              return Number.isNaN(date.getTime())
                ? value
                : timezone === "utc"
                  ? date.toISOString().replace(/\.\d{3}Z$/, "+00:00")
                  : date.toLocaleString("sv-SE");
            };
            update({ timezone, since: convert(filters.since), until: convert(filters.until) });
          }}
        >
          {filters.timezone === "utc" ? "UTC" : "Local"}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-sm">
        <label className="inline-flex items-center gap-1">
          <input
            type="checkbox"
            aria-label="Include allowlisted"
            checked={filters.allowlisted === true}
            onChange={(event) => update({ allowlisted: event.target.checked })}
          />
          Include allowlisted
        </label>
        {filters.allowlisted ? (
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
            allowlisted included
          </span>
        ) : null}
        <label className="inline-flex items-center gap-1">
          <input
            type="checkbox"
            aria-label="Only in incidents"
            checked={filters.in_incident === true}
            onChange={(event) => update({ in_incident: event.target.checked ? true : null })}
          />
          Only in incidents
        </label>
        <label className="inline-flex items-center gap-1">
          Process
          <input
            aria-label="Process filter"
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={filters.process_name}
            onChange={(event) => update({ process_name: event.target.value })}
          />
        </label>
        <label className="inline-flex items-center gap-1">
          Username
          <input
            aria-label="Username filter"
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={filters.username}
            onChange={(event) => update({ username: event.target.value })}
          />
        </label>
        <Button
          onClick={() => update({ event_type: [], severity: [], source: [], search: "", source_ip: "", source_cidr: "", allowlisted: null })}
        >
          Clear filters
        </Button>
      </div>
    </section>
  );
}
