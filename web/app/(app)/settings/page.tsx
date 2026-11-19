import { ApiTable } from "@/components/data-table/ApiTable";

export default function SettingsPage() {
  return (
    <div className="space-y-4">
      <ApiTable<Record<string, unknown>>
        path="/api/settings/retention"
        columns={["key", "value"]}
        title="Retention policy"
      />
      <ApiTable<Record<string, unknown>>
        path="/api/risk/decay"
        columns={["key", "value"]}
        title="Risk decay"
      />
    </div>
  );
}
