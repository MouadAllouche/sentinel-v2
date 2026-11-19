"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ChangePasswordDialog } from "@/components/forms/ChangePasswordDialog";
import { Button, Input } from "@/components/ui/primitives";
import { useMe } from "@/lib/auth";
import { useLogout } from "@/lib/api/hooks";
import { useLiveUpdates } from "@/lib/sse";
import { useTheme } from "./ThemeProvider";

const STATUS_LABEL: Record<string, string> = {
  connecting: "Connecting to live feed",
  live: "Live updates active",
  reconnecting: "Reconnecting to live feed",
  polling: "Live feed unavailable, polling",
  paused: "Live updates paused (tab hidden)",
};

export function Topbar() {
  const router = useRouter();
  const me = useMe();
  const { theme, toggle } = useTheme();
  const { status } = useLiveUpdates();
  const logout = useLogout();
  const [search, setSearch] = useState("");
  const [changingPassword, setChangingPassword] = useState(false);

  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-2 dark:border-slate-700">
      <form
        role="search"
        className="flex flex-1 items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          router.push(`/events?q=${encodeURIComponent(search)}`);
        }}
      >
        <Input
          aria-label="Global search"
          placeholder="Search IP or username"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </form>
      <span role="status" aria-live="polite" className="text-xs text-slate-600 dark:text-slate-300">
        <span aria-hidden="true">{status === "live" ? "●" : "○"}</span> {STATUS_LABEL[status] ?? status}
      </span>
      <Button aria-label="Theme" aria-pressed={theme === "dark"} onClick={toggle}>
        {theme === "dark" ? "Light" : "Dark"}
      </Button>
      <span className="text-sm">Signed in as {me.username || "…"}</span>
      <Button onClick={() => setChangingPassword(true)}>Change password</Button>
      {changingPassword ? <ChangePasswordDialog onClose={() => setChangingPassword(false)} /> : null}
      <Button
        onClick={() => {
          void logout.mutateAsync().finally(() => router.push("/login"));
        }}
      >
        Sign out
      </Button>
    </header>
  );
}
