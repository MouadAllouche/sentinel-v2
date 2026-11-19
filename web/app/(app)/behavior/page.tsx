import { ApiTable } from "@/components/data-table/ApiTable";

export default function BehaviorPage() {
  return (
    <div className="space-y-4">
      <ApiTable<Record<string, unknown>>
        path="/api/anomalies"
        columns={["id", "timestamp", "event_type", "severity", "description"]}
        title="Anomalies"
      />
      <ApiTable<Record<string, unknown>>
        path="/api/baselines"
        columns={["metric", "subject", "status", "sample_count"]}
        title="Baselines"
      />
    </div>
  );
}
