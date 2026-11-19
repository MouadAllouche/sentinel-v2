import { AuditRoute } from "@/components/audit/AuditRoute";
import { RequireAdmin } from "@/components/ui/RequireAdmin";

export default function AuditPageRoute() {
  return (
    <RequireAdmin>
      <AuditRoute />
    </RequireAdmin>
  );
}
