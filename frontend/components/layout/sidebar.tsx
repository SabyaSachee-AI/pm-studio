"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type ScreenPermission } from "@/lib/api";

const NAV_ITEMS = [
  { href: "/dashboard", screen: "dashboard", label: "Dashboard" },
  { href: "/clients", screen: "clients", label: "Clients" },
  { href: "/projects", screen: "projects", label: "Projects" },
  { href: "/requirements", screen: "requirements", label: "Requirements" },
  { href: "/prds", screen: "prds", label: "PRDs" },
  { href: "/srs", screen: "srs", label: "SRS" },
  { href: "/architecture", screen: "architecture", label: "Architecture" },
  { href: "/tasks", screen: "tasks", label: "Kanban" },
  { href: "/knowledge", screen: "knowledge_base", label: "Knowledge" },
  { href: "/decisions", screen: "decisions", label: "Decisions" },
  { href: "/admin/users", screen: "admin_users", label: "Users" },
  { href: "/admin/ai-config", screen: "admin_users", label: "AI config" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [screens, setScreens] = useState<ScreenPermission[]>([]);

  useEffect(() => {
    api.getScreens().then(setScreens).catch(() => setScreens([]));
  }, []);

  const allowed = new Set(screens.map((s) => s.screen_key));

  return (
    <aside className="flex h-full w-56 flex-col border-r border-gray-800 bg-gray-950">
      <div className="border-b border-gray-800 px-4 py-5">
        <p className="text-sm font-semibold text-white">PM Studio</p>
        <p className="text-xs text-gray-500">AI project management</p>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {NAV_ITEMS.filter(
          (item) => screens.length === 0 || allowed.has(item.screen),
        ).map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`block rounded-md px-3 py-2 text-sm ${
                active
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:bg-gray-900 hover:text-white"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
