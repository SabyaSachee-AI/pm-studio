"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api, type Project } from "@/lib/api";

type Item = {
  label: string;
  hint: string;
  icon: string;
  href: string;
};

const SCREENS: Item[] = [
  { label: "Dashboard", hint: "Screen", icon: "ti-layout-dashboard", href: "/dashboard" },
  { label: "Clients", hint: "Screen", icon: "ti-users-group", href: "/clients" },
  { label: "Projects", hint: "Screen", icon: "ti-folder", href: "/projects" },
  { label: "Requirements", hint: "Screen", icon: "ti-file-text", href: "/requirements" },
  { label: "PRDs", hint: "Screen", icon: "ti-file-description", href: "/prds" },
  { label: "SRS", hint: "Screen", icon: "ti-file-code", href: "/srs" },
  { label: "Architecture", hint: "Screen", icon: "ti-topology-star-3", href: "/architecture" },
  { label: "Kanban", hint: "Screen", icon: "ti-layout-kanban", href: "/tasks" },
  { label: "Build", hint: "Screen", icon: "ti-code", href: "/build" },
  { label: "Traceability", hint: "Screen", icon: "ti-route", href: "/traceability" },
  { label: "Knowledge", hint: "Screen", icon: "ti-book", href: "/knowledge" },
  { label: "Decisions", hint: "Screen", icon: "ti-scale", href: "/decisions" },
  { label: "AI config", hint: "Admin", icon: "ti-settings-bolt", href: "/admin/ai-config" },
];

/** Ctrl/Cmd+K quick navigation — screens + project search, zero clicks. */
export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const [projects, setProjects] = useState<Project[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // Global shortcut: Ctrl/Cmd+K opens, Escape closes.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Load projects once per open (cheap list; lets users jump by name).
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setSelected(0);
    void api.listProjects().then(setProjects).catch(() => setProjects([]));
    const t = setTimeout(() => inputRef.current?.focus(), 30);
    return () => clearTimeout(t);
  }, [open]);

  const items = useMemo<Item[]>(() => {
    const projectItems: Item[] = projects.map((p) => ({
      label: p.name,
      hint: "Project",
      icon: "ti-folder-filled",
      href: `/projects/${p.id}`,
    }));
    const all = [...SCREENS, ...projectItems];
    const q = query.trim().toLowerCase();
    if (!q) return all.slice(0, 12);
    return all
      .filter((it) => it.label.toLowerCase().includes(q))
      .slice(0, 12);
  }, [projects, query]);

  const go = useCallback(
    (item: Item | undefined) => {
      if (!item) return;
      setOpen(false);
      router.push(item.href);
    },
    [router],
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-[15vh]"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-xl border border-gray-700 bg-gray-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-gray-800 px-4">
          <i className="ti ti-search text-gray-500" aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelected(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setSelected((s) => Math.min(s + 1, items.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setSelected((s) => Math.max(s - 1, 0));
              } else if (e.key === "Enter") {
                e.preventDefault();
                go(items[selected]);
              }
            }}
            placeholder="Jump to a screen or project…"
            className="w-full bg-transparent py-3 text-sm text-gray-200 outline-none placeholder:text-gray-600"
          />
          <kbd className="rounded border border-gray-700 px-1.5 py-0.5 text-[10px] text-gray-500">Esc</kbd>
        </div>
        <ul className="max-h-80 overflow-y-auto py-1">
          {items.map((it, i) => (
            <li key={`${it.href}-${it.label}`}>
              <button
                className={`flex w-full items-center gap-3 px-4 py-2 text-left text-sm ${
                  i === selected ? "bg-blue-600/20 text-blue-200" : "text-gray-300 hover:bg-gray-800"
                }`}
                onMouseEnter={() => setSelected(i)}
                onClick={() => go(it)}
              >
                <i className={`ti ${it.icon} text-gray-500`} aria-hidden />
                <span className="flex-1 truncate">{it.label}</span>
                <span className="text-[10px] uppercase tracking-wide text-gray-600">{it.hint}</span>
              </button>
            </li>
          ))}
          {items.length === 0 && (
            <li className="px-4 py-6 text-center text-sm text-gray-600">No matches.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
