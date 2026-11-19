import { ApiTable } from "@/components/data-table/ApiTable";

export default function NotificationsPage() {
  return (
    <div className="space-y-4">
      <ApiTable<Record<string, unknown>>
        path="/api/notifications/channels"
        columns={["id", "name", "kind", "enabled", "min_severity"]}
        title="Notification channels"
      />
      <ApiTable<Record<string, unknown>>
        path="/api/notifications/log"
        columns={["id", "ts", "channel", "severity", "status"]}
        title="Notification log"
      />
    </div>
  );
}
