export function ExplanationPanel({
  explanation,
}: {
  explanation: {
    grouping?: { strong?: string[]; weak?: string[] };
    rules?: Array<{ rule_id?: string; tier_label?: string }>;
    anchors?: Array<{ event_id: number; timestamp: string; event_type: string }>;
    caveats?: string[];
  };
}) {
  const strong = explanation.grouping?.strong ?? [];
  const weak = explanation.grouping?.weak ?? [];
  return (
    <div className="space-y-3">
      <section>
        <h2 className="font-semibold">Strong links</h2>
        {strong.length ? (
          <ul className="list-disc pl-5 text-sm">
            {strong.map((reason, index) => <li key={index}>{reason}</li>)}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">No strong links recorded.</p>
        )}
      </section>
      <section>
        <h2 className="font-semibold">Weak links (time proximity only)</h2>
        {weak.length ? (
          <ul className="list-disc pl-5 text-sm">
            {weak.map((reason, index) => <li key={index}>Weak: {reason}</li>)}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">No weak links recorded.</p>
        )}
      </section>
      {explanation.anchors?.length ? (
        <section>
          <h2 className="font-semibold">Anchor events</h2>
          <ul className="list-disc pl-5 text-sm">
            {explanation.anchors.map((anchor) => (
              <li key={anchor.event_id}>
                {anchor.timestamp} · {anchor.event_type} · event #{anchor.event_id}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {explanation.rules?.length ? (
        <section>
          <h2 className="font-semibold">Rule findings</h2>
          <ul className="list-disc pl-5 text-sm">
            {explanation.rules.map((rule, index) => (
              <li key={index}>{rule.rule_id ?? "unknown"} · {rule.tier_label ?? "?"}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <section aria-label="Caveats" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-700 dark:bg-amber-950">
        {(explanation.caveats ?? []).map((caveat, index) => <p key={index}>{caveat}</p>)}
      </section>
    </div>
  );
}
