"use client";

import {
  Activity,
  ShieldAlert,
  ListFilter,
  ScrollText,
  SlidersHorizontal,
  Waypoints,
  BellRing,
  Settings,
  Users,
  History,
  HeartPulse,
  LayoutDashboard,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { useMe } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/events", label: "Events", icon: ScrollText },
  { href: "/incidents", label: "Incidents", icon: ShieldAlert },
  { href: "/rules", label: "Rules", icon: ListFilter },
  { href: "/severity", label: "Severity", icon: SlidersHorizontal },
  { href: "/allowlist", label: "Allowlist", icon: ShieldCheckIcon },
  { href: "/behavior", label: "Behavior", icon: Activity },
  { href: "/drift", label: "Drift", icon: Waypoints },
  { href: "/notifications", label: "Notifications", icon: BellRing },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/users", label: "Users", icon: Users },
  { href: "/audit", label: "Audit", icon: History },
  { href: "/health", label: "Health", icon: HeartPulse },
] as const;

function ShieldCheckIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3Z" stroke="currentColor" strokeWidth="1.7" />
      <path d="m9 12 2 2 4-4" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

const ADMIN_PATHS = new Set(["/notifications", "/settings", "/users", "/audit"]);

export function Sidebar() {
  const pathname = usePathname();
  const me = useMe();
  const [collapsed, setCollapsed] = useState(false);
  const visible = NAV.filter(
    (item) => !(me.username && me.role !== "admin" && ADMIN_PATHS.has(item.href)),
  );

  return (
    <aside className={cn("shrink-0 border-r border-slate-200 dark:border-slate-700", collapsed ? "w-16" : "w-56")}>
      <div className="flex items-center justify-between p-3">
        {!collapsed ? <span className="font-semibold">Sentinel</span> : null}
        <button
          type="button"
          className="rounded p-1 text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
          aria-expanded={!collapsed}
          onClick={() => setCollapsed((value) => !value)}
        >
          {collapsed ? "»" : "«"}
          <span className="sr-only">{collapsed ? "Expand sidebar" : "Collapse sidebar"}</span>
        </button>
      </div>
      <nav aria-label="Main" className="flex flex-col gap-0.5 px-2">
        {visible.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              title={label}
              className={cn(
                "flex items-center gap-2 rounded px-2 py-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-800",
                active && "bg-slate-200 font-medium dark:bg-slate-700",
                collapsed && "justify-center",
              )}
            >
              <Icon size={18} aria-hidden="true" />
              {!collapsed ? <span>{label}</span> : null}
            </Link>
          );
        })}
      </nav>
      <p className="mt-4 px-3 text-xs text-slate-500">Read-only monitoring</p>
    </aside>
  );
}
