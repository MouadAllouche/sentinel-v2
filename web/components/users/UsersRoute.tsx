"use client";

import { ErrorState, Skeleton } from "@/components/ui/primitives";
import { UsersPage, type UserRow } from "@/components/users/UsersPage";
import { useToast } from "@/components/ui/Toaster";
import { client } from "@/lib/api/client";
import { useApiList } from "@/lib/api/hooks";
import { useMe } from "@/lib/auth";

export function UsersRoute() {
  const me = useMe();
  const { show } = useToast();
  const users = useApiList<UserRow>("/api/users");
  if (users.isLoading) return <Skeleton rows={4} />;
  if (users.isError) return <ErrorState message="Could not load users." />;
  return (
    <UsersPage
      users={users.data?.items ?? []}
      role={me.role}
      onCreate={(username, password, role) => {
        void client
          .POST("/api/users", { body: { username, password, role } })
          .then(() => void users.refetch())
          .catch(() => show("Could not create the user"));
      }}
      onChangeRole={(identifier, role) => {
        void client
          .PATCH("/api/users/{identifier}", {
            params: { path: { identifier } },
            body: { role },
          })
          .then(() => void users.refetch())
          .catch(() => show("Could not change the role"));
      }}
      onDisable={(identifier, disabled) => {
        void client
          .PATCH("/api/users/{identifier}", {
            params: { path: { identifier } },
            body: { disabled },
          })
          .then(() => void users.refetch())
          .catch(() => show("Could not change the user"));
      }}
      onResetPassword={(identifier) => {
        const password = window.prompt("New temporary password (at least 12 characters)");
        if (!password) return;
        void client
          .POST("/api/users/{identifier}/password-reset", {
            params: { path: { identifier } },
            body: { password },
          })
          .then(() => show("Password reset", "success"))
          .catch(() => show("Could not reset the password"));
      }}
      onRevokeSessions={(identifier) => {
        void client
          .POST("/api/users/{identifier}/sessions/revoke", {
            params: { path: { identifier } },
          })
          .then(() => show("Sessions revoked", "success"))
          .catch(() => show("Could not revoke sessions"));
      }}
    />
  );
}
