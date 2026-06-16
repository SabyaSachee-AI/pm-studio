"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type PermissionCell, type PermissionMatrix } from "@/lib/api";

// ─── constants ────────────────────────────────────────────────────────────────

const SCREEN_META: Record<string, { label: string; icon: string }> = {
  dashboard:    { label: "Dashboard",    icon: "ti-layout-dashboard" },
  clients:      { label: "Clients",      icon: "ti-building" },
  projects:     { label: "Projects",     icon: "ti-folder" },
  requirements: { label: "Requirements", icon: "ti-file-upload" },
  prds:         { label: "PRDs",         icon: "ti-book" },
  srs:          { label: "SRS",          icon: "ti-file-text" },
  architecture: { label: "Architecture", icon: "ti-sitemap" },
  tasks:        { label: "Kanban tasks",   icon: "ti-columns" },
  traceability: { label: "Traceability",  icon: "ti-git-commit" },
  knowledge_base:{ label: "Knowledge base",icon: "ti-brain" },
  decisions:    { label: "Decisions",     icon: "ti-scale" },
  admin_users:  { label: "Admin — users", icon: "ti-users" },
  ai_config:    { label: "AI config",     icon: "ti-robot" },
};

const ROLE_META: Record<string, { label: string; color: string }> = {
  project_manager:  { label: "Project manager",   color: "text-blue-400" },
  business_analyst: { label: "Business analyst",  color: "text-violet-400" },
  architect:        { label: "Architect",          color: "text-cyan-400" },
  code_creator:     { label: "Developer",          color: "text-amber-400" },
  qa_engineer:      { label: "QA engineer",        color: "text-emerald-400" },
  client:           { label: "Client",             color: "text-pink-400" },
  viewer:           { label: "Viewer",             color: "text-gray-400" },
};

// ─── cell toggle component ────────────────────────────────────────────────────

function PermToggle({
  active,
  label,
  color,
  disabled,
  saving,
  onClick,
}: {
  active: boolean;
  label: string;
  color: string;
  disabled: boolean;
  saving: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || saving}
      title={disabled ? "Admin roles always have full access" : `Toggle ${label}`}
      className={[
        "relative flex h-7 w-7 items-center justify-center rounded text-[10px] font-bold uppercase tracking-wide transition-all",
        saving ? "animate-pulse" : "",
        disabled
          ? "cursor-default border border-gray-700/30 bg-gray-800/20 text-gray-700"
          : active
            ? `border ${color} bg-opacity-20 text-white shadow-sm`
            : "border border-gray-700/50 bg-gray-800/40 text-gray-600 hover:border-gray-600 hover:text-gray-400",
      ].join(" ")}
    >
      {saving ? <i className="ti ti-loader-2 animate-spin text-xs" aria-hidden /> : label[0]}
    </button>
  );
}

// ─── page ─────────────────────────────────────────────────────────────────────

type SavingKey = `${string}:${string}:${"view" | "edit"}`;

export default function PermissionsPage() {
  const [matrix, setMatrix]   = useState<PermissionMatrix | null>(null);
  const [saving, setSaving]   = useState<Set<SavingKey>>(new Set());
  const [toast, setToast]     = useState<{ msg: string; ok: boolean } | null>(null);
  const [filter, setFilter]   = useState<string>("all");

  const load = useCallback(async () => {
    const m = await api.getPermissionMatrix();
    setMatrix(m);
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Build lookup: role:screen → {can_view, can_edit}
  const lookup = useMemo(() => {
    const map = new Map<string, PermissionCell>();
    matrix?.permissions.forEach((p) => map.set(`${p.role}:${p.screen_key}`, p));
    return map;
  }, [matrix]);

  function showToast(msg: string, ok = true) {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 2500);
  }

  async function toggle(
    role: string,
    screen: string,
    field: "can_view" | "can_edit",
  ) {
    const key = `${role}:${screen}` as const;
    const current = lookup.get(key) ?? { role, screen_key: screen, can_view: false, can_edit: false };

    let nextView = current.can_view;
    let nextEdit = current.can_edit;

    if (field === "can_edit") {
      nextEdit = !nextEdit;
      if (nextEdit) nextView = true;         // edit implies view
    } else {
      nextView = !nextView;
      if (!nextView) nextEdit = false;       // removing view also removes edit
    }

    // Optimistic update
    setMatrix((prev) => {
      if (!prev) return prev;
      const updated = prev.permissions.map((p) =>
        p.role === role && p.screen_key === screen
          ? { ...p, can_view: nextView, can_edit: nextEdit }
          : p,
      );
      // Add new cell if it didn't exist
      if (!updated.find((p) => p.role === role && p.screen_key === screen)) {
        updated.push({ role, screen_key: screen, can_view: nextView, can_edit: nextEdit });
      }
      return { ...prev, permissions: updated };
    });

    const savingKey = `${role}:${screen}:${field}` as SavingKey;
    setSaving((s) => new Set(s).add(savingKey));
    try {
      await api.updatePermission(role, screen, nextView, nextEdit);
      showToast(`${ROLE_META[role]?.label ?? role} — ${SCREEN_META[screen]?.label ?? screen} updated`);
    } catch {
      showToast("Save failed — reverting", false);
      void load();
    } finally {
      setSaving((s) => { const n = new Set(s); n.delete(savingKey); return n; });
    }
  }

  // Role filter
  const visibleRoles = useMemo(() => {
    if (!matrix) return [];
    return filter === "all" ? matrix.roles : [filter];
  }, [matrix, filter]);

  if (!matrix) {
    return (
      <div className="flex h-64 items-center justify-center text-gray-500">
        <i className="ti ti-loader-2 animate-spin mr-2" /> Loading permissions…
      </div>
    );
  }

  return (
    <div className="space-y-5 pb-10">

      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm shadow-xl transition-all ${
          toast.ok
            ? "border-emerald-700/60 bg-emerald-950/80 text-emerald-300"
            : "border-red-700/60 bg-red-950/80 text-red-300"
        }`}>
          <i className={`ti ${toast.ok ? "ti-check" : "ti-x"} text-base`} aria-hidden />
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-gray-600">Admin</p>
          <h1 className="text-2xl font-bold text-white">Screen permissions</h1>
          <p className="mt-0.5 text-sm text-gray-500">
            Control which screens each role can view or edit. Changes save instantly.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-600">Filter role:</span>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="rounded-md border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-white"
          >
            <option value="all">All roles</option>
            {matrix.roles.map((r) => (
              <option key={r} value={r}>{ROLE_META[r]?.label ?? r}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-gray-800 bg-gray-900/40 px-4 py-3 text-xs text-gray-500">
        <span className="flex items-center gap-1.5">
          <span className="flex h-5 w-5 items-center justify-center rounded border border-blue-500 bg-blue-500/20 text-[9px] font-bold text-white">V</span>
          View — can open & read the screen
        </span>
        <span className="flex items-center gap-1.5">
          <span className="flex h-5 w-5 items-center justify-center rounded border border-amber-500 bg-amber-500/20 text-[9px] font-bold text-white">E</span>
          Edit — can create / modify content
        </span>
        <span className="flex items-center gap-1.5">
          <span className="flex h-5 w-5 items-center justify-center rounded border border-gray-700/30 bg-gray-800/20 text-[9px] font-bold text-gray-700">V</span>
          Off — no access
        </span>
        <span className="ml-auto flex items-center gap-1.5 text-emerald-600">
          <i className="ti ti-shield-check text-sm" aria-hidden />
          Admin roles (owner, admin) always have full access and cannot be changed
        </span>
      </div>

      {/* Matrix table */}
      <div className="overflow-x-auto rounded-xl border border-gray-800">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-gray-800 bg-gray-900/80">
              <th className="sticky left-0 z-10 bg-gray-900 px-4 py-3 text-left text-xs font-semibold uppercase tracking-widest text-gray-500 w-44">
                Screen
              </th>
              {/* Admin role indicator columns */}
              {matrix.admin_roles.map((role) => (
                <th key={role} className="px-2 py-3 text-center">
                  <div className="flex flex-col items-center gap-1">
                    <span className="rounded-full border border-emerald-800/40 bg-emerald-950/30 px-2 py-0.5 text-[10px] font-medium text-emerald-500 whitespace-nowrap">
                      {role === "studio_owner" ? "Owner" : "Admin"}
                    </span>
                    <i className="ti ti-shield-check text-xs text-emerald-700" aria-hidden />
                  </div>
                </th>
              ))}
              {/* Editable role columns */}
              {visibleRoles.map((role) => {
                const meta = ROLE_META[role];
                return (
                  <th key={role} className="px-3 py-3 text-center min-w-[88px]">
                    <div className="flex flex-col items-center gap-0.5">
                      <span className={`text-[11px] font-semibold whitespace-nowrap ${meta?.color ?? "text-gray-400"}`}>
                        {meta?.label ?? role}
                      </span>
                      <span className="text-[9px] text-gray-700">V / E</span>
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {matrix.screens.map((screen, si) => {
              const meta = SCREEN_META[screen];
              return (
                <tr
                  key={screen}
                  className={`border-b border-gray-800/60 last:border-0 ${si % 2 === 0 ? "bg-gray-900/20" : "bg-transparent"} hover:bg-gray-900/50 transition-colors`}
                >
                  {/* Screen label (sticky) */}
                  <td className={`sticky left-0 z-10 px-4 py-3 ${si % 2 === 0 ? "bg-gray-900/80" : "bg-gray-950/90"}`}>
                    <div className="flex items-center gap-2">
                      <i className={`ti ${meta?.icon ?? "ti-square"} text-sm text-gray-500`} aria-hidden />
                      <span className="font-medium text-gray-200 whitespace-nowrap">{meta?.label ?? screen}</span>
                    </div>
                  </td>

                  {/* Admin role cells — always full, locked */}
                  {matrix.admin_roles.map((role) => (
                    <td key={role} className="px-2 py-3 text-center">
                      <div className="flex items-center justify-center gap-1">
                        <span title="Full view access — always on" className="flex h-7 w-7 items-center justify-center rounded border border-blue-800/30 bg-blue-950/20 text-[10px] font-bold text-blue-700">V</span>
                        <span title="Full edit access — always on" className="flex h-7 w-7 items-center justify-center rounded border border-amber-800/30 bg-amber-950/20 text-[10px] font-bold text-amber-700">E</span>
                      </div>
                    </td>
                  ))}

                  {/* Editable role cells */}
                  {visibleRoles.map((role) => {
                    const cell = lookup.get(`${role}:${screen}`) ?? {
                      role, screen_key: screen, can_view: false, can_edit: false,
                    };
                    const viewKey = `${role}:${screen}:view` as SavingKey;
                    const editKey = `${role}:${screen}:edit` as SavingKey;
                    return (
                      <td key={role} className="px-3 py-3 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <PermToggle
                            active={cell.can_view}
                            label="View"
                            color="border-blue-500 bg-blue-500/15"
                            disabled={false}
                            saving={saving.has(viewKey)}
                            onClick={() => void toggle(role, screen, "can_view")}
                          />
                          <PermToggle
                            active={cell.can_edit}
                            label="Edit"
                            color="border-amber-500 bg-amber-500/15"
                            disabled={false}
                            saving={saving.has(editKey)}
                            onClick={() => void toggle(role, screen, "can_edit")}
                          />
                        </div>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Role summary cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {matrix.roles.map((role) => {
          const meta = ROLE_META[role];
          const rolePerms = matrix.permissions.filter((p) => p.role === role);
          const viewCount = rolePerms.filter((p) => p.can_view).length;
          const editCount = rolePerms.filter((p) => p.can_edit).length;
          const total = matrix.screens.length;
          return (
            <div
              key={role}
              className={`cursor-pointer rounded-xl border p-4 transition-all ${
                filter === role
                  ? "border-indigo-600/60 bg-indigo-950/20"
                  : "border-gray-800 bg-gray-900/40 hover:border-gray-700"
              }`}
              onClick={() => setFilter(filter === role ? "all" : role)}
            >
              <p className={`text-sm font-semibold ${meta?.color ?? "text-gray-400"}`}>
                {meta?.label ?? role}
              </p>
              <div className="mt-2 flex gap-3">
                <div>
                  <p className="text-lg font-bold text-blue-400 tabular-nums">{viewCount}</p>
                  <p className="text-[10px] text-gray-600">can view</p>
                </div>
                <div>
                  <p className="text-lg font-bold text-amber-400 tabular-nums">{editCount}</p>
                  <p className="text-[10px] text-gray-600">can edit</p>
                </div>
                <div className="ml-auto">
                  <p className="text-lg font-bold text-gray-600 tabular-nums">{total}</p>
                  <p className="text-[10px] text-gray-700">total</p>
                </div>
              </div>
              {/* Mini progress bar */}
              <div className="mt-2 h-1 w-full rounded-full bg-gray-800 overflow-hidden">
                <div
                  className="h-1 rounded-full bg-blue-500/60 transition-all duration-500"
                  style={{ width: `${total > 0 ? (viewCount / total) * 100 : 0}%` }}
                />
              </div>
              <p className="mt-1 text-[9px] text-gray-700">
                Click to {filter === role ? "show all" : "filter matrix"}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
