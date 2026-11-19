"use client";

import { useState } from "react";

import { Button, Card, Input, Label } from "@/components/ui/primitives";
import { passwordStrength } from "@/lib/admin/helpers";
import type { Role } from "@/lib/auth";

export interface UserRow {
  id: number;
  username: string;
  role: string;
  disabled?: boolean;
  locked_until?: string | null;
  last_login?: string | null;
  failed_logins?: number;
}

export function UsersPage({
  users,
  role,
  onCreate,
  onChangeRole,
  onDisable,
  onResetPassword,
  onRevokeSessions,
}: {
  users: UserRow[];
  role: Role;
  onCreate: (username: string, password: string, userRole: string) => void;
  onChangeRole: (id: number, next: string) => void;
  onDisable: (id: number, disabled: boolean) => void;
  onResetPassword: (id: number, password: string) => void;
  onRevokeSessions: (id: number) => void;
}) {
  const [creating, setCreating] = useState(false);
  const [username, setUsername] = useState("");
  const [userRole, setUserRole] = useState("viewer");
  const [oneTime, setOneTime] = useState<string | null>(null);
  const admin = role === "admin";
  const activeAdmins = users.filter((item) => item.role === "admin" && !item.disabled);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold">Users</h1>
        <Button disabled={!admin} onClick={() => setCreating(true)}>Create user</Button>
      </div>
      {oneTime ? (
        <p role="status" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-700 dark:bg-amber-950">
          Temporary password: <code>{oneTime}</code> — shown once. The user must change it on first login.
        </p>
      ) : null}
      {creating ? (
        <Card>
          <Label htmlFor="new-username">Username</Label>
          <Input id="new-username" aria-label="New username" value={username} onChange={(event) => setUsername(event.target.value)} />
          <Label htmlFor="new-role">Role</Label>
          <select
            id="new-role"
            aria-label="New role"
            className="w-full rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800"
            value={userRole}
            onChange={(event) => setUserRole(event.target.value)}
          >
            <option value="viewer">viewer</option><option value="admin">admin</option>
          </select>
          <Button
            className="mt-2"
            disabled={username.length < 3}
            onClick={() => {
              const bytes = new Uint8Array(18);
              crypto.getRandomValues(bytes);
              const password = Array.from(bytes, (byte) => String.fromCharCode(33 + (byte % 90))).join("");
              setOneTime(password);
              onCreate(username, password, userRole);
              setCreating(false);
              setUsername("");
            }}
          >
            Create
          </Button>
          <p className="mt-2 text-xs text-slate-500">Passwords must be at least 12 characters.</p>
        </Card>
      ) : null}
      <Card>
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Users</caption>
          <thead>
            <tr><th scope="col">Username</th><th scope="col">Role</th><th scope="col">Last login</th><th scope="col">Locked until</th><th scope="col">Disable</th><th scope="col">Actions</th></tr>
          </thead>
          <tbody>
            {users.map((user) => {
              const lastAdmin = user.role === "admin" && !user.disabled && activeAdmins.length === 1;
              return (
                <tr key={user.id} className="border-b border-slate-100 dark:border-slate-800">
                  <td>{user.username}</td>
                  <td>
                    <select
                      aria-label={`Role for ${user.username}`}
                      disabled={!admin || lastAdmin}
                      value={user.role}
                      onChange={(event) => onChangeRole(user.id, event.target.value)}
                    >
                      <option value="viewer">viewer</option><option value="admin">admin</option>
                    </select>
                  </td>
                  <td>{user.last_login ?? "—"}</td>
                  <td>{user.locked_until ?? "—"}</td>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Disable ${user.username}`}
                      checked={Boolean(user.disabled)}
                      disabled={!admin || lastAdmin}
                      onChange={(event) => onDisable(user.id, event.target.checked)}
                    />
                  </td>
                  <td className="flex gap-1">
                    <Button disabled={!admin} onClick={() => onResetPassword(user.id, "")}>Reset password</Button>
                    <Button disabled={!admin} onClick={() => onRevokeSessions(user.id)}>Revoke sessions</Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
      <p className="text-xs text-slate-500">Password strength: {passwordStrength("")} — choose at least 12 characters.</p>
    </div>
  );
}
