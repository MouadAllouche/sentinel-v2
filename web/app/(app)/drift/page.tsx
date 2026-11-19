import { ApiTable } from "@/components/data-table/ApiTable";

export default function DriftPage() {
  return (
    <ApiTable<Record<string, unknown>>
      path="/api/drift/status"
      columns={["id", "path", "enabled", "metadata_only", "baseline_status"]}
      title="Monitored paths and drift status"
    />
  );
}
