import { ApiTable } from "@/components/data-table/ApiTable";

export default function EventsPage() {
  return (
    <ApiTable<Record<string, unknown>>
      path="/api/events"
      columns={["id", "timestamp", "event_type", "severity", "source_ip", "description"]}
      title="Events"
    />
  );
}
