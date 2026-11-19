"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Skeleton } from "@/components/ui/primitives";
import { useMe } from "@/lib/auth";

/** Display-only guard; every admin endpoint also enforces RBAC server-side. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const me = useMe();
  const router = useRouter();

  useEffect(() => {
    if (me.username && me.role !== "admin") router.replace("/?error=forbidden");
  }, [me.role, me.username, router]);

  // The auth query is still loading; do not redirect on the anonymous default.
  if (!me.username) return <Skeleton rows={3} />;
  if (me.role === "admin") return <>{children}</>;
  return <Skeleton rows={3} />;
}
