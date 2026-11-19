import { NotificationsRoute } from "@/components/notifications/NotificationsRoute";
import { RequireAdmin } from "@/components/ui/RequireAdmin";

export default function NotificationsPage() {
  return (
    <RequireAdmin>
      <NotificationsRoute />
    </RequireAdmin>
  );
}
