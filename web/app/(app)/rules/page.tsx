import Link from "next/link";

import { ApiTable } from "@/components/data-table/ApiTable";
import { RequireRole } from "@/lib/auth";

export default function RulesPage() {
  return (
    <div className="space-y-3">
      <RequireRole requiredRole="admin">
        <Link className="inline-block rounded bg-slate-900 px-3 py-2 text-sm text-white" href="/rules/new">
          New rule
        </Link>
      </RequireRole>
      <ApiTable<Record<string, unknown>>
        path="/api/rules"
        columns={["id", "name", "kind", "enabled", "description"]}
        title="Rules"
      />
    </div>
  );
}
