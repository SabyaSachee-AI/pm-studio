"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type ScreenPermission } from "@/lib/api";

const NAV_ITEMS = [
  { href: "/dashboard",       screen: "dashboard",    label: "Dashboard",    icon: "ti-layout-dashboard" },
  { href: "/clients",         screen: "clients",      label: "Clients",      icon: "ti-building" },
  { href: "/projects",        screen: "projects",     label: "Projects",     icon: "ti-folder" },
  { href: "/requirements",    screen: "requirements", label: "Requirements", icon: "ti-file-description" },
  { href: "/prds",            screen: "prds",         label: "PRDs",         icon: "ti-book" },
  { href: "/srs",             screen: "srs",          label: "SRS",          icon: "ti-file-text" },
  { href: "/architecture",    screen: "architecture", label: "Architecture", icon: "ti-sitemap" },
  { href: "/tasks",           screen: "tasks",        label: "Kanban",       icon: "ti-columns" },
  { href: "/knowledge",       screen: "knowledge_base",label: "Knowledge",   icon: "ti-brain" },
  { href: "/decisions",       screen: "decisions",    label: "Decisions",    icon: "ti-scale" },
  { href: "/admin/users",     screen: "admin_users",  label: "Users",        icon: "ti-users" },
  { href: "/admin/ai-config", screen: "admin_users",  label: "AI config",    icon: "ti-robot" },
];

export function Sidebar() {
  const pathname  = usePathname();
  const [screens,   setScreens]   = useState<ScreenPermission[]>([]);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    api.getScreens().then(setScreens).catch(() => setScreens([]));
  }, []);

  const allowed = new Set(screens.map((s) => s.screen_key));

  return (
    <aside
      className={`sticky top-0 flex h-screen flex-col border-r border-gray-800 bg-gray-950 transition-all duration-200 ${
        collapsed ? "w-14" : "w-56"
      }`}
    >
      {/* Brand + collapse toggle */}
      {collapsed ? (
        /* Collapsed header — only the expand button, centered */
        <div className="flex flex-col items-center gap-2 border-b border-gray-800 px-2 py-3">
          <span className="flex h-7 w-7 items-center justify-center rounded bg-indigo-600 text-xs font-bold text-white">
            P
          </span>
          <button
            onClick={() => setCollapsed(false)}
            title="Expand sidebar"
            className="rounded p-1.5 text-gray-500 hover:bg-gray-800 hover:text-gray-200 transition-colors"
          >
            <i className="ti ti-chevrons-right text-base" aria-hidden />
          </button>
        </div>
      ) : (
        /* Expanded header — brand + collapse button */
        <div className="flex items-center justify-between border-b border-gray-800 px-4 py-5">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-white">PM Studio</p>
            <p className="text-xs text-gray-500">AI project management</p>
          </div>
          <button
            onClick={() => setCollapsed(true)}
            title="Collapse sidebar"
            className="ml-2 shrink-0 rounded p-1.5 text-gray-500 hover:bg-gray-800 hover:text-gray-200 transition-colors"
          >
            <i className="ti ti-chevrons-left text-base" aria-hidden />
          </button>
        </div>
      )}

      {/* Nav items */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {NAV_ITEMS.filter(
          (item) => screens.length === 0 || allowed.has(item.screen),
        ).map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={`flex items-center gap-3 rounded-md py-2 text-sm transition-colors ${
                collapsed ? "justify-center px-0" : "px-3"
              } ${
                active
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:bg-gray-900 hover:text-white"
              }`}
            >
              <i className={`ti ${item.icon} text-base shrink-0`} aria-hidden />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
