import { ApiTable } from "@/components/data-table/ApiTable";

export default function AuditPage() {
  return (
    <ApiTable<Record<string, unknown>>
      path="/api/audit"
      columns={["ts", "actor", "action", "target_type", "target_id", "ip"]}
      title="Audit log"
    />
  );
}
