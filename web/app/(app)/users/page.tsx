import { RequireAdmin } from "@/components/ui/RequireAdmin";
import { UsersRoute } from "@/components/users/UsersRoute";

export default function UsersPageRoute() {
  return (
    <RequireAdmin>
      <UsersRoute />
    </RequireAdmin>
  );
}
