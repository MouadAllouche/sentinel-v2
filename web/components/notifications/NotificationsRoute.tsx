"use client";

import { ChannelEditor, type ChannelValue } from "@/components/notifications/ChannelEditor";
import { Button, Card, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toaster";
import { client } from "@/lib/api/client";
import { useApiList, useSystemInfo } from "@/lib/api/hooks";
import { useMe } from "@/lib/auth";

export function NotificationsRoute() {
  const me = useMe();
  const { show } = useToast();
  const channels = useApiList<ChannelValue & { id: number }>("/api/notifications/channels");
  const log = useApiList<Record<string, unknown>>("/api/notifications/log");
  const info = useSystemInfo();
  const envVars = info.data?.env_vars ?? {};
  const globallyEnabled = Boolean(info.data?.notifications_enabled);

  if (channels.isLoading) return <Skeleton rows={4} />;
  if (channels.isError) return <ErrorState message="Could not load notification channels." />;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Notifications</h1>
      <p role="status" className="rounded border border-slate-300 p-3 text-sm dark:border-slate-600">
        Notifications are {globallyEnabled ? "ON" : "OFF"} globally in settings.toml (read-only).
      </p>
      {me.role !== "admin" ? <p className="text-sm text-slate-500">View only</p> : null}
      <div className="grid gap-3 lg:grid-cols-2">
        {(channels.data?.items ?? []).map((channel) => (
          <Card key={channel.id}>
            <h2 className="font-semibold">{channel.name}</h2>
            <ChannelEditor
              value={channel}
              envVars={envVars}
              readOnly={me.role !== "admin"}
              onSave={(value) => {
                void client
                  .PUT("/api/notifications/channels/{identifier}", {
                    params: { path: { identifier: channel.id } },
                    body: value as unknown as Record<string, unknown>,
                  })
                  .then(() => {
                    show("Channel saved", "success");
                    void channels.refetch();
                  })
                  .catch(() => show("Could not save the channel"));
              }}
            />
            <Button
              className="mt-2"
              disabled={me.role !== "admin"}
              onClick={() => {
                void client
                  .POST("/api/notifications/channels/{identifier}/test", {
                    params: { path: { identifier: channel.id } },
                  })
                  .then(({ data }) => {
                    const result = data as { ok?: boolean } | undefined;
                    if (result?.ok === false) show("Test message was not delivered");
                    else show("Test message sent", "success");
                    void log.refetch();
                  })
                  .catch(() => show("Test message failed"));
              }}
            >
              Send test
            </Button>
          </Card>
        ))}
      </div>
      <Card>
        <h2 className="font-semibold">Notification log</h2>
        <table className="mt-2 w-full text-left text-sm">
          <caption className="sr-only">Notification attempts</caption>
          <thead><tr><th scope="col">Time</th><th scope="col">Channel</th><th scope="col">Incident</th><th scope="col">Status</th><th scope="col">Detail</th></tr></thead>
          <tbody>
            {(log.data?.items ?? []).map((item, index) => (
              <tr key={index} className="border-b border-slate-100 dark:border-slate-800">
                <td>{String(item.sent_at ?? "—")}</td><td>{String(item.channel_id ?? "—")}</td>
                <td>{String(item.incident_id ?? "—")}</td><td>{String(item.status ?? "—")}</td>
                <td>{String(item.detail ?? "—")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
