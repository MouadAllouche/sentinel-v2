export function StatusHistory({
  entries,
  audit = [],
}: {
  entries: Array<{
    id: number;
    from_status: string;
    to_status: string;
    actor: string;
    reason?: string | null;
    at: string;
  }>;
  audit?: Array<{ id: number; actor: string; action: string; ts: string }>;
}) {
  return (
    <div className="space-y-3">
      <ul className="space-y-2 text-sm" aria-label="Status history">
        {entries.length === 0 ? <li className="text-slate-500">No status changes yet.</li> : null}
        {entries.map((entry) => (
          <li key={entry.id} className="rounded border border-slate-200 p-2 dark:border-slate-700">
            <p>{entry.from_status} → {entry.to_status}</p>
            <p className="text-xs text-slate-500">{entry.actor} · {entry.at}</p>
            {entry.reason ? <p className="mt-1">{entry.reason}</p> : null}
          </li>
        ))}
      </ul>
      {audit.length ? (
        <ul className="space-y-1 text-sm" aria-label="Related audit entries">
          {audit.map((item) => (
            <li key={item.id} className="text-slate-600 dark:text-slate-300">
              {item.ts} · {item.actor} · {item.action}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
