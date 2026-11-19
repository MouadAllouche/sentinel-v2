import Link from "next/link";

import { Card } from "@/components/ui/primitives";

export function FirstRunChecklist() {
  return (
    <Card>
      <h2 className="text-lg font-semibold">Sentinel has not collected any events yet</h2>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm">
        <li>
          Run the engine once with <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">python cli.py engine</code>.
        </li>
        <li>Check collector warnings on the Health page and fix permission problems.</li>
        <li>
          <Link className="text-blue-700 underline" href="/health">
            Open Health
          </Link>{" "}
          and confirm the database is writable.
        </li>
      </ol>
      <p className="mt-3 text-xs text-slate-500">
        Charts and KPIs appear as soon as the first events are stored.
      </p>
    </Card>
  );
}
