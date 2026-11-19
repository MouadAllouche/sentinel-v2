import type { ScoreReason, ScoreSummary } from "@/lib/incident/helpers";

export function ScoreReasonsTable({
  reasons,
  summary,
}: {
  reasons: ScoreReason[];
  summary: ScoreSummary | null;
}) {
  const running = reasons.reduce((total, reason) => total + reason.points, 0);
  return (
    <div className="space-y-2">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Stored score reasons</caption>
        <thead>
          <tr>
            <th scope="col">Rule</th>
            <th scope="col">Tier</th>
            <th scope="col">Points</th>
            <th scope="col">Severity</th>
            <th scope="col">Explanation</th>
          </tr>
        </thead>
        <tbody>
          {reasons.map((reason, index) => (
            <tr key={`${reason.rule_id ?? index}-${index}`} className="border-b border-slate-100 dark:border-slate-800">
              <td>{reason.rule_id ?? reason.rule_name ?? reason.kind ?? "—"}</td>
              <td>{reason.tier_label ?? "—"}</td>
              <td className="tabular-nums">{reason.points}</td>
              <td>{reason.severity ?? "—"}</td>
              <td>{reason.explanation ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-sm">
        Running total: <strong className="tabular-nums">{running}</strong>
        {summary?.capped ? " (capped at 100)" : ""}
      </p>
      {summary?.severity_basis ? (
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Severity set by {summary.severity_basis}.
        </p>
      ) : null}
    </div>
  );
}
