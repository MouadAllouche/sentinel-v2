import { ApiTable } from "@/components/data-table/ApiTable";

export default function AllowlistPage() {
  return (
    <ApiTable<Record<string, unknown>>
      path="/api/allowlist"
      columns={["id", "scope", "subject", "reason", "created_at"]}
      title="Allowlist"
    />
  );
}
