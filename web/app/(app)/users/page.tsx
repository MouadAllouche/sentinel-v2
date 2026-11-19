import { ApiTable } from "@/components/data-table/ApiTable";

export default function UsersPage() {
  return (
    <ApiTable<Record<string, unknown>>
      path="/api/users"
      columns={["id", "username", "role", "disabled", "created_at"]}
      title="Users"
    />
  );
}
