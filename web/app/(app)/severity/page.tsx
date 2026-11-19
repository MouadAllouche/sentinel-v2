import { ApiTable } from "@/components/data-table/ApiTable";

export default function SeverityPage() {
  return (
    <div className="space-y-4">
      <ApiTable<Record<string, unknown>>
        path="/api/severity/defaults"
        columns={["key", "severity", "points"]}
        title="Severity defaults"
      />
      <ApiTable<Record<string, unknown>>
        path="/api/severity/overrides"
        columns={["scope", "subject", "severity", "points", "priority"]}
        title="Severity overrides"
      />
    </div>
  );
}
