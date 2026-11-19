"use client";

export interface PreviewResult {
  total_findings: number;
  noise_per_day: number;
  by_severity?: Record<string, number>;
  groups?: Array<{ value: string; total: number }>;
  samples?: unknown[];
}

export function PreviewPanel({
  result,
  loading,
  onRangeChange,
}: {
  result: PreviewResult | null;
  loading: boolean;
  onRangeChange: (preset: string) => void;
}) {
  const tooMuch = (result?.total_findings ?? 0) > 1000;
  return (
    <aside aria-label="Preview and backtest" className="space-y-2 rounded border border-slate-200 p-3 dark:border-slate-700">
      <h2 className="font-semibold">Preview &amp; backtest</h2>
      <p className="text-xs text-slate-500">Simulation on historical data. Nothing is saved.</p>
      <label className="text-sm">
        Range
        <select
          aria-label="Preview range"
          className="ml-2 rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
          onChange={(event) => onRangeChange(event.target.value)}
        >
          <option value="7d">last 7 days</option>
          <option value="24h">last 24 hours</option>
          <option value="30d">last 30 days</option>
        </select>
      </label>
      {loading ? <p role="status">Simulating…</p> : null}
      {!loading && !result ? <p className="text-sm">No data in this range.</p> : null}
      {!loading && tooMuch ? (
        <p className="text-sm text-amber-800 dark:text-amber-200">Too much data — narrow the range.</p>
      ) : null}
      {!loading && result && !tooMuch ? (
        <div className="text-sm">
          <p>Findings: <strong>{result.total_findings}</strong></p>
          <p aria-live="polite">≈ {result.noise_per_day} findings/day</p>
          <table className="mt-2 w-full text-left">
            <caption className="sr-only">Findings by severity</caption>
            <tbody>
              {Object.entries(result.by_severity ?? {}).map(([severity, total]) => (
                <tr key={severity}>
                  <th scope="row">{severity}</th>
                  <td>{total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </aside>
  );
}
