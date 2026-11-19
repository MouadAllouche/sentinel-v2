"use client";

import { createContext, useContext, type ReactNode } from "react";

export type Role = "admin" | "viewer";

export interface Me {
  username: string;
  role: Role;
}

const defaultMe: Me = { username: "", role: "viewer" };

export const AuthContext = createContext<Me>(defaultMe);

/** Returns the current user. The API remains the authority for every action. */
export function useMe(): Me {
  return useContext(AuthContext);
}

/**
 * Restrict a control to a role. This is display-only; the API enforces RBAC.
 * `roleOfUser` allows isolated tests and previews to supply the role explicitly.
 */
export function RequireRole({
  requiredRole,
  roleOfUser,
  children,
}: {
  requiredRole: Role;
  roleOfUser?: Role;
  children: ReactNode;
}) {
  const me = useMe();
  const effective = roleOfUser ?? me.role;
  if (effective !== requiredRole) return null;
  return <>{children}</>;
}

/** Only a same-origin absolute path (with optional query/hash) is accepted. */
export function validateNextPath(value: string | null | undefined): string {
  if (!value || typeof value !== "string") return "/";
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return "/";
  if (/[\r\n]/.test(value)) return "/";
  if (typeof window === "undefined") return value.includes("://") ? "/" : value;
  try {
    const url = new URL(value, window.location.origin);
    if (url.origin !== window.location.origin) return "/";
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return "/";
  }
}
