import { formatInTimeZone } from "date-fns-tz";

export function formatUtc(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  return formatInTimeZone(date, "UTC", "yyyy-MM-dd HH:mm:ss 'UTC'");
}

export function formatRelative(from: string, to: string): string {
  const delta = Math.max(
    0,
    Math.round((new Date(to).getTime() - new Date(from).getTime()) / 1000),
  );
  if (delta < 60) return `${delta}s`;
  const minutes = Math.floor(delta / 60);
  const seconds = delta % 60;
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

export function formatScore(score: number): string {
  return String(Math.min(100, Math.max(0, Math.round(score))));
}
