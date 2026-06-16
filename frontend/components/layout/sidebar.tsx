"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type ScreenPermission } from "@/lib/api";
import { MusicPlayer } from "./MusicPlayer";

const NAV_ITEMS = [
  { href: "/dashboard",         screen: "dashboard",      label: "Dashboard",    icon: "ti-layout-dashboard" },
  { href: "/clients",           screen: "clients",        label: "Clients",      icon: "ti-building" },
  { href: "/projects",          screen: "projects",       label: "Projects",     icon: "ti-folder" },
  { href: "/requirements",      screen: "requirements",   label: "Requirements", icon: "ti-file-description" },
  { href: "/prds",              screen: "prds",           label: "PRDs",         icon: "ti-book" },
  { href: "/srs",               screen: "srs",            label: "SRS",          icon: "ti-file-text" },
  { href: "/architecture",      screen: "architecture",   label: "Architecture", icon: "ti-sitemap" },
  { href: "/tasks",             screen: "tasks",          label: "Kanban",       icon: "ti-columns" },
  { href: "/traceability",      screen: "traceability",   label: "Traceability", icon: "ti-git-commit" },
  { href: "/knowledge",         screen: "knowledge_base", label: "Knowledge",    icon: "ti-brain" },
  { href: "/decisions",         screen: "decisions",      label: "Decisions",    icon: "ti-scale" },
  { href: "/admin/users",       screen: "admin_users",    label: "Users",        icon: "ti-users" },
  { href: "/admin/permissions", screen: "admin_users",    label: "Permissions",  icon: "ti-shield-check" },
  { href: "/admin/ai-config",   screen: "ai_config",      label: "AI config",    icon: "ti-robot" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [screens,   setScreens]   = useState<ScreenPermission[]>([]);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    api.getScreens().then(setScreens).catch(() => setScreens([]));
  }, []);

  // Read persisted state after mount (avoid SSR mismatch)
  useEffect(() => {
    try { setCollapsed(localStorage.getItem("sb-collapsed") === "1"); } catch { /* ignore */ }
  }, []);

  // Persist on every toggle
  useEffect(() => {
    try { localStorage.setItem("sb-collapsed", collapsed ? "1" : "0"); } catch { /* ignore */ }
  }, [collapsed]);

  const allowed = new Set(screens.map((s) => s.screen_key));

  // Width is owned entirely by inline style — never depends on Tailwind width classes
  const W = collapsed ? "56px" : "224px";

  return (
    <aside
      style={{ width: W, minWidth: W, transition: "width 0.2s ease, min-width 0.2s ease" }}
      // flex-shrink-0 prevents the flex row from squeezing the sidebar
      // NO overflow-hidden — that was clipping the icons to nothing
      className="relative flex h-screen flex-shrink-0 flex-col border-r border-gray-800 bg-gray-950"
    >
      {/* ── Header ────────────────────────────────────────────────────── */}
      {collapsed ? (
        // Collapsed: only the expand button, full-width + centred
        <div className="flex flex-col items-center gap-1 border-b border-gray-800 py-3">
          {/* Mini brand mark */}
          <div className="flex h-7 w-7 items-center justify-center rounded bg-indigo-600 text-xs font-bold text-white select-none">
            P
          </div>
          {/* Expand button — text fallback so it renders even without icon font */}
          <button
            onClick={() => setCollapsed(false)}
            title="Expand sidebar"
            className="mt-1 flex h-7 w-7 items-center justify-center rounded border border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-500 hover:bg-gray-700 hover:text-white transition-colors"
          >
            <i className="ti ti-chevrons-right text-sm" aria-hidden />
            {/* Text fallback in case icon font not loaded */}
            <span className="sr-only">Expand</span>
          </button>
        </div>
      ) : (
        // Expanded: brand + collapse button
        <div className="flex items-center justify-between border-b border-gray-800 px-4 py-5">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-white">PM Studio</p>
            <p className="text-xs text-gray-500">AI project management</p>
          </div>
          <button
            onClick={() => setCollapsed(true)}
            title="Collapse sidebar"
            className="ml-2 flex h-7 w-7 shrink-0 items-center justify-center rounded border border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-500 hover:bg-gray-700 hover:text-white transition-colors"
          >
            <i className="ti ti-chevrons-left text-sm" aria-hidden />
          </button>
        </div>
      )}

      {/* ── Nav ───────────────────────────────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto p-2">
        {NAV_ITEMS.filter(
          (item) => screens.length === 0 || allowed.has(item.screen),
        ).map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              title={item.label}          // always set — tooltip in both modes
              className={[
                "mb-0.5 flex items-center rounded-md py-2.5 text-sm transition-colors",
                collapsed ? "justify-center px-1" : "gap-3 px-3",
                active
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:bg-gray-900 hover:text-white",
              ].join(" ")}
            >
              <i className={`ti ${item.icon} shrink-0 text-[17px]`} aria-hidden />
              {/* Label: hidden when collapsed via width + opacity, no overflow-hidden on aside */}
              {!collapsed && (
                <span className="truncate">{item.label}</span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* ── Music player ──────────────────────────────────────────────── */}
      <MusicPlayer collapsed={collapsed} />
    </aside>
  );
}
