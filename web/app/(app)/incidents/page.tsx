import { ApiTable } from "@/components/data-table/ApiTable";

export default function IncidentsPage() {
  return (
    <ApiTable<Record<string, unknown>>
      path="/api/incidents"
      columns={["id", "status", "severity", "score", "created_at", "assignee"]}
      title="Incidents"
    />
  );
}
