"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2, X } from "lucide-react";
import { AiStatusBar, aiJobStatusBarProps } from "@/components/ui/AiStatusBar";
import { ArchModelSelector } from "@/components/ui/ArchModelSelector";
import { Button } from "@/components/ui/button";
import { api, type ModelChoice } from "@/lib/api";
import { useAiJob } from "@/lib/hooks/useAiJob";

type DocKey =
  | "doc_system_arch"
  | "doc_database"
  | "doc_api"
  | "doc_frontend"
  | "doc_security"
  | "doc_uiux";

interface ArchitectureEditSheetProps {
  open: boolean;
  docKey: DocKey;
  title: string;
  architectureId: string;
  initialContent: Record<string, unknown>;
  consistencyIssues?: string[];
  onClose: () => void;
  onSaved: (content: Record<string, unknown>) => void;
}

// ---------------------------------------------------------------------------
// Tiny helpers
// ---------------------------------------------------------------------------

function inp(extra = "") {
  return `w-full rounded border border-gray-700 bg-gray-950 px-2.5 py-1.5 text-sm text-gray-100 focus:border-blue-600 focus:outline-none ${extra}`;
}

function ta(rows = 3, extra = "") {
  return `${inp(extra)} resize-none`;
}

function Label({ children }: { children: React.ReactNode }) {
  return <span className="mb-1 block text-xs font-medium text-gray-400">{children}</span>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <Label>{label}</Label>
      {children}
    </label>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 text-sm font-semibold text-white">{children}</h3>;
}

function Card({ children, onRemove }: { children: React.ReactNode; onRemove?: () => void }) {
  return (
    <div className="relative rounded-lg border border-gray-800 bg-gray-900/60 p-3">
      {onRemove ? (
        <button
          type="button"
          onClick={onRemove}
          className="absolute right-2 top-2 rounded p-0.5 text-gray-500 hover:bg-red-950/40 hover:text-red-400"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      ) : null}
      <div className="space-y-2 pr-6">{children}</div>
    </div>
  );
}

function AddButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-1.5 rounded border border-dashed border-gray-700 px-3 py-1.5 text-xs text-gray-400 hover:border-blue-700 hover:text-blue-400"
    >
      <Plus className="h-3.5 w-3.5" />
      {label}
    </button>
  );
}

function CollapsibleCard({
  title,
  subtitle,
  badge,
  onRemove,
  children,
}: {
  title: string;
  subtitle?: string;
  badge?: string;
  onRemove?: () => void;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/60">
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex flex-1 items-center gap-2 text-left"
        >
          {open ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-gray-500" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-gray-500" />
          )}
          <span className="text-sm font-medium text-gray-200">{title}</span>
          {badge ? (
            <span className="rounded bg-gray-800 px-1.5 py-0.5 text-xs text-gray-400">{badge}</span>
          ) : null}
          {subtitle ? (
            <span className="truncate text-xs text-gray-500">{subtitle}</span>
          ) : null}
        </button>
        {onRemove ? (
          <button
            type="button"
            onClick={onRemove}
            className="rounded p-0.5 text-gray-600 hover:bg-red-950/40 hover:text-red-400"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </div>
      {open ? <div className="border-t border-gray-800 p-3 space-y-3">{children}</div> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Per-doc editors
// ---------------------------------------------------------------------------

// ── System Architecture ──────────────────────────────────────────────────────

type Component = { name: string; type: string; responsibility: string; communicates_with: string[] };
type TechStackEntry = { layer: string; name: string; version: string; reason: string };

function SystemArchEditor({
  draft,
  setDraft,
}: {
  draft: Record<string, unknown>;
  setDraft: (d: Record<string, unknown>) => void;
}) {
  const components = ((draft.components as Component[]) ?? []) as Component[];
  const techStack = draft.tech_stack as Record<string, Record<string, string>> ?? {};
  const stackEntries: TechStackEntry[] = Object.entries(techStack).map(([layer, v]) => ({
    layer,
    name: v?.name ?? "",
    version: v?.version ?? "",
    reason: v?.reason ?? "",
  }));

  function setComponents(next: Component[]) {
    setDraft({ ...draft, components: next });
  }

  function setStack(entries: TechStackEntry[]) {
    const obj: Record<string, Record<string, string>> = {};
    for (const e of entries) {
      if (e.layer.trim()) obj[e.layer.trim()] = { name: e.name, version: e.version, reason: e.reason };
    }
    setDraft({ ...draft, tech_stack: obj });
  }

  function updateComp(i: number, key: keyof Component, val: string) {
    const next = [...components];
    if (key === "communicates_with") {
      next[i] = { ...next[i], communicates_with: val.split(",").map((s) => s.trim()).filter(Boolean) };
    } else {
      next[i] = { ...next[i], [key]: val };
    }
    setComponents(next);
  }

  return (
    <div className="space-y-5">
      <Field label="Overview">
        <textarea
          rows={3}
          className={ta(3)}
          value={String(draft.overview ?? "")}
          onChange={(e) => setDraft({ ...draft, overview: e.target.value })}
        />
      </Field>
      <Field label="Architecture pattern">
        <input className={inp()} value={String(draft.architecture_pattern ?? "")}
          onChange={(e) => setDraft({ ...draft, architecture_pattern: e.target.value })} />
      </Field>

      <div>
        <SectionTitle>Tech stack</SectionTitle>
        <div className="space-y-2">
          {stackEntries.map((entry, i) => (
            <Card key={i} onRemove={() => {
              const next = [...stackEntries];
              next.splice(i, 1);
              setStack(next);
            }}>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Layer"><input className={inp()} value={entry.layer}
                  onChange={(e) => { const next = [...stackEntries]; next[i] = { ...entry, layer: e.target.value }; setStack(next); }} /></Field>
                <Field label="Name"><input className={inp()} value={entry.name}
                  onChange={(e) => { const next = [...stackEntries]; next[i] = { ...entry, name: e.target.value }; setStack(next); }} /></Field>
                <Field label="Version"><input className={inp()} value={entry.version}
                  onChange={(e) => { const next = [...stackEntries]; next[i] = { ...entry, version: e.target.value }; setStack(next); }} /></Field>
                <Field label="Reason"><input className={inp()} value={entry.reason}
                  onChange={(e) => { const next = [...stackEntries]; next[i] = { ...entry, reason: e.target.value }; setStack(next); }} /></Field>
              </div>
            </Card>
          ))}
          <AddButton label="Add tech stack item" onClick={() => setStack([...stackEntries, { layer: "", name: "", version: "", reason: "" }])} />
        </div>
      </div>

      <div>
        <SectionTitle>Components</SectionTitle>
        <div className="space-y-2">
          {components.map((c, i) => (
            <CollapsibleCard
              key={i}
              title={c.name || `Component ${i + 1}`}
              subtitle={c.type}
              onRemove={() => setComponents(components.filter((_, j) => j !== i))}
            >
              <Field label="Name"><input className={inp()} value={c.name} onChange={(e) => updateComp(i, "name", e.target.value)} /></Field>
              <Field label="Type"><input className={inp()} value={c.type} onChange={(e) => updateComp(i, "type", e.target.value)} /></Field>
              <Field label="Responsibility">
                <textarea rows={2} className={ta(2)} value={c.responsibility}
                  onChange={(e) => updateComp(i, "responsibility", e.target.value)} />
              </Field>
              <Field label="Communicates with (comma-separated)">
                <input className={inp()} value={(c.communicates_with ?? []).join(", ")}
                  onChange={(e) => updateComp(i, "communicates_with", e.target.value)} />
              </Field>
            </CollapsibleCard>
          ))}
          <AddButton label="Add component" onClick={() => setComponents([...components, { name: "", type: "", responsibility: "", communicates_with: [] }])} />
        </div>
      </div>

      <Field label="Data flow (one step per line)">
        <textarea rows={4} className={ta(4)} value={((draft.data_flow as string[]) ?? []).join("\n")}
          onChange={(e) => setDraft({ ...draft, data_flow: e.target.value.split("\n").filter(Boolean) })} />
      </Field>
    </div>
  );
}

// ── Database ──────────────────────────────────────────────────────────────────

type DbCol = { name: string; type: string; pk: boolean; nullable: boolean; default: string };
type DbTable = { name: string; purpose: string; linked_srs_entity: string; columns: DbCol[]; constraints: string[] };

function DatabaseEditor({
  draft,
  setDraft,
}: {
  draft: Record<string, unknown>;
  setDraft: (d: Record<string, unknown>) => void;
}) {
  const tables = ((draft.tables as DbTable[]) ?? []) as DbTable[];

  function setTables(next: DbTable[]) { setDraft({ ...draft, tables: next }); }

  function updateTable(i: number, patch: Partial<DbTable>) {
    const next = [...tables];
    next[i] = { ...next[i], ...patch };
    setTables(next);
  }

  function updateCol(ti: number, ci: number, patch: Partial<DbCol>) {
    const cols = [...(tables[ti].columns ?? [])];
    cols[ci] = { ...cols[ci], ...patch };
    updateTable(ti, { columns: cols });
  }

  return (
    <div className="space-y-5">
      <Field label="Overview">
        <textarea rows={3} className={ta(3)} value={String(draft.overview ?? "")}
          onChange={(e) => setDraft({ ...draft, overview: e.target.value })} />
      </Field>

      <div>
        <SectionTitle>Tables</SectionTitle>
        <div className="space-y-2">
          {tables.map((tbl, ti) => (
            <CollapsibleCard
              key={ti}
              title={tbl.name || `Table ${ti + 1}`}
              subtitle={tbl.purpose}
              badge={tbl.linked_srs_entity}
              onRemove={() => setTables(tables.filter((_, j) => j !== ti))}
            >
              <div className="grid grid-cols-2 gap-2">
                <Field label="Table name"><input className={inp()} value={tbl.name}
                  onChange={(e) => updateTable(ti, { name: e.target.value })} /></Field>
                <Field label="SRS entity link"><input className={inp()} value={tbl.linked_srs_entity ?? ""}
                  onChange={(e) => updateTable(ti, { linked_srs_entity: e.target.value })} /></Field>
              </div>
              <Field label="Purpose">
                <textarea rows={2} className={ta(2)} value={tbl.purpose ?? ""}
                  onChange={(e) => updateTable(ti, { purpose: e.target.value })} />
              </Field>

              <div>
                <Label>Columns</Label>
                <div className="space-y-1.5">
                  {(tbl.columns ?? []).map((col, ci) => (
                    <div key={ci} className="grid grid-cols-[1fr_1fr_auto_auto_auto] gap-1.5 items-center rounded border border-gray-800 bg-gray-950 px-2 py-1.5">
                      <input className={inp("text-xs font-mono")} placeholder="column_name" value={col.name}
                        onChange={(e) => updateCol(ti, ci, { name: e.target.value })} />
                      <input className={inp("text-xs font-mono")} placeholder="TEXT / UUID / INT" value={col.type}
                        onChange={(e) => updateCol(ti, ci, { type: e.target.value })} />
                      <label className="flex items-center gap-1 text-xs text-gray-400 whitespace-nowrap">
                        <input type="checkbox" checked={!!col.pk}
                          onChange={(e) => updateCol(ti, ci, { pk: e.target.checked })} />
                        PK
                      </label>
                      <label className="flex items-center gap-1 text-xs text-gray-400 whitespace-nowrap">
                        <input type="checkbox" checked={col.nullable !== false}
                          onChange={(e) => updateCol(ti, ci, { nullable: e.target.checked })} />
                        null
                      </label>
                      <button type="button" onClick={() => {
                        const cols = (tbl.columns ?? []).filter((_, j) => j !== ci);
                        updateTable(ti, { columns: cols });
                      }} className="text-gray-600 hover:text-red-400">
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                  <AddButton label="Add column" onClick={() => {
                    const cols = [...(tbl.columns ?? []), { name: "", type: "TEXT", pk: false, nullable: true, default: "" }];
                    updateTable(ti, { columns: cols });
                  }} />
                </div>
              </div>

              <Field label="Constraints (one per line)">
                <textarea rows={2} className={ta(2, "text-xs font-mono")}
                  value={(tbl.constraints ?? []).join("\n")}
                  onChange={(e) => updateTable(ti, { constraints: e.target.value.split("\n").filter(Boolean) })} />
              </Field>
            </CollapsibleCard>
          ))}
          <AddButton label="Add table" onClick={() => setTables([...tables, { name: "", purpose: "", linked_srs_entity: "", columns: [], constraints: [] }])} />
        </div>
      </div>
    </div>
  );
}

// ── API ───────────────────────────────────────────────────────────────────────

type Endpoint = { method: string; path: string; full_path: string; description: string; linked_fr: string; mvp_scope: string; auth_required: boolean };

const HTTP_METHODS = ["GET", "POST", "PATCH", "PUT", "DELETE"];

function ApiEditor({
  draft,
  setDraft,
}: {
  draft: Record<string, unknown>;
  setDraft: (d: Record<string, unknown>) => void;
}) {
  const endpoints = ((draft.endpoints as Endpoint[]) ?? []) as Endpoint[];

  function setEndpoints(next: Endpoint[]) { setDraft({ ...draft, endpoints: next }); }

  function updateEp(i: number, patch: Partial<Endpoint>) {
    const next = [...endpoints];
    next[i] = { ...next[i], ...patch };
    setEndpoints(next);
  }

  return (
    <div className="space-y-5">
      <Field label="Overview">
        <textarea rows={3} className={ta(3)} value={String(draft.overview ?? "")}
          onChange={(e) => setDraft({ ...draft, overview: e.target.value })} />
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Base URL"><input className={inp()} value={String(draft.base_url ?? "/api/v1")}
          onChange={(e) => setDraft({ ...draft, base_url: e.target.value })} /></Field>
        <Field label="Auth"><input className={inp()} value={String(draft.auth ?? "")}
          onChange={(e) => setDraft({ ...draft, auth: e.target.value })} /></Field>
      </div>

      <div>
        <SectionTitle>Endpoints ({endpoints.length})</SectionTitle>
        <div className="space-y-2">
          {endpoints.map((ep, i) => (
            <CollapsibleCard
              key={i}
              title={`${ep.method || "?"} ${ep.full_path || ep.path || "..."}`}
              subtitle={ep.description}
              badge={ep.linked_fr}
              onRemove={() => setEndpoints(endpoints.filter((_, j) => j !== i))}
            >
              <div className="grid grid-cols-[120px_1fr] gap-2">
                <Field label="Method">
                  <select className={inp()} value={ep.method} onChange={(e) => updateEp(i, { method: e.target.value })}>
                    {HTTP_METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                </Field>
                <Field label="Path"><input className={inp("font-mono text-xs")} value={ep.full_path || ep.path}
                  onChange={(e) => updateEp(i, { full_path: e.target.value, path: e.target.value })} /></Field>
              </div>
              <Field label="Description">
                <textarea rows={2} className={ta(2)} value={ep.description ?? ""}
                  onChange={(e) => updateEp(i, { description: e.target.value })} />
              </Field>
              <div className="grid grid-cols-3 gap-2">
                <Field label="Linked FR"><input className={inp("text-xs")} value={ep.linked_fr ?? ""}
                  onChange={(e) => updateEp(i, { linked_fr: e.target.value })} /></Field>
                <Field label="MVP scope">
                  <select className={inp()} value={ep.mvp_scope ?? "v1"} onChange={(e) => updateEp(i, { mvp_scope: e.target.value })}>
                    <option value="v1">v1</option>
                    <option value="v2">v2</option>
                    <option value="later">later</option>
                  </select>
                </Field>
                <Field label="Auth required">
                  <select className={inp()} value={ep.auth_required === false ? "no" : "yes"}
                    onChange={(e) => updateEp(i, { auth_required: e.target.value === "yes" })}>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </Field>
              </div>
            </CollapsibleCard>
          ))}
          <AddButton label="Add endpoint" onClick={() => setEndpoints([...endpoints, { method: "GET", path: "/", full_path: "/api/v1/", description: "", linked_fr: "", mvp_scope: "v1", auth_required: true }])} />
        </div>
      </div>
    </div>
  );
}

// ── Frontend ─────────────────────────────────────────────────────────────────

type FePage = { path: string; description: string; protected: boolean; components: string[]; api_calls: string[] };

function FrontendEditor({
  draft,
  setDraft,
}: {
  draft: Record<string, unknown>;
  setDraft: (d: Record<string, unknown>) => void;
}) {
  const pages = ((draft.pages as FePage[]) ?? []) as FePage[];

  function setPages(next: FePage[]) { setDraft({ ...draft, pages: next }); }

  function updatePage(i: number, patch: Partial<FePage>) {
    const next = [...pages];
    next[i] = { ...next[i], ...patch };
    setPages(next);
  }

  return (
    <div className="space-y-5">
      <Field label="Overview">
        <textarea rows={3} className={ta(3)} value={String(draft.overview ?? "")}
          onChange={(e) => setDraft({ ...draft, overview: e.target.value })} />
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Framework"><input className={inp()} value={String(draft.framework ?? "")}
          onChange={(e) => setDraft({ ...draft, framework: e.target.value })} /></Field>
        <Field label="Styling"><input className={inp()} value={String(draft.styling ?? "")}
          onChange={(e) => setDraft({ ...draft, styling: e.target.value })} /></Field>
      </div>

      <div>
        <SectionTitle>Pages ({pages.length})</SectionTitle>
        <div className="space-y-2">
          {pages.map((p, i) => (
            <CollapsibleCard
              key={i}
              title={p.path || `Page ${i + 1}`}
              subtitle={p.description}
              badge={p.protected === false ? "public" : "protected"}
              onRemove={() => setPages(pages.filter((_, j) => j !== i))}
            >
              <div className="grid grid-cols-2 gap-2">
                <Field label="Route path"><input className={inp("font-mono text-xs")} value={p.path}
                  onChange={(e) => updatePage(i, { path: e.target.value })} /></Field>
                <Field label="Access">
                  <select className={inp()} value={p.protected === false ? "public" : "protected"}
                    onChange={(e) => updatePage(i, { protected: e.target.value === "protected" })}>
                    <option value="protected">Protected (auth)</option>
                    <option value="public">Public</option>
                  </select>
                </Field>
              </div>
              <Field label="Description">
                <textarea rows={2} className={ta(2)} value={p.description ?? ""}
                  onChange={(e) => updatePage(i, { description: e.target.value })} />
              </Field>
              <Field label="Components (comma-separated)">
                <input className={inp("text-xs")} value={(p.components ?? []).join(", ")}
                  onChange={(e) => updatePage(i, { components: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
              </Field>
              <Field label="API calls (comma-separated)">
                <input className={inp("text-xs font-mono")} value={(p.api_calls ?? []).join(", ")}
                  onChange={(e) => updatePage(i, { api_calls: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
              </Field>
            </CollapsibleCard>
          ))}
          <AddButton label="Add page" onClick={() => setPages([...pages, { path: "/", description: "", protected: true, components: [], api_calls: [] }])} />
        </div>
      </div>
    </div>
  );
}

// ── Security ──────────────────────────────────────────────────────────────────

type Role = { name: string; description: string };

function SecurityEditor({
  draft,
  setDraft,
}: {
  draft: Record<string, unknown>;
  setDraft: (d: Record<string, unknown>) => void;
}) {
  const rbac = (draft.rbac as Record<string, unknown>) ?? {};
  const rawRoles = (rbac.roles as Array<string | Record<string, unknown>>) ?? [];
  const roles: Role[] = rawRoles.map((r) =>
    typeof r === "string" ? { name: r, description: "" } : { name: String(r.name ?? ""), description: String(r.description ?? "") }
  );

  function setRoles(next: Role[]) {
    setDraft({ ...draft, rbac: { ...rbac, roles: next } });
  }

  return (
    <div className="space-y-5">
      <Field label="Overview">
        <textarea rows={3} className={ta(3)} value={String(draft.overview ?? "")}
          onChange={(e) => setDraft({ ...draft, overview: e.target.value })} />
      </Field>

      <div>
        <SectionTitle>Roles</SectionTitle>
        <div className="space-y-2">
          {roles.map((r, i) => (
            <Card key={i} onRemove={() => setRoles(roles.filter((_, j) => j !== i))}>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Role name"><input className={inp("font-mono text-xs")} value={r.name}
                  onChange={(e) => { const next = [...roles]; next[i] = { ...r, name: e.target.value }; setRoles(next); }} /></Field>
                <Field label="Description"><input className={inp()} value={r.description}
                  onChange={(e) => { const next = [...roles]; next[i] = { ...r, description: e.target.value }; setRoles(next); }} /></Field>
              </div>
            </Card>
          ))}
          <AddButton label="Add role" onClick={() => setRoles([...roles, { name: "", description: "" }])} />
        </div>
      </div>

      <Field label="OWASP checklist (JSON — advanced)">
        <textarea rows={5} className={ta(5, "font-mono text-xs")}
          value={JSON.stringify(draft.owasp_checklist ?? [], null, 2)}
          onChange={(e) => {
            try { setDraft({ ...draft, owasp_checklist: JSON.parse(e.target.value) }); } catch { /* keep typing */ }
          }} />
      </Field>
    </div>
  );
}

// ── UI/UX ─────────────────────────────────────────────────────────────────────

function UiUxEditor({
  draft,
  setDraft,
}: {
  draft: Record<string, unknown>;
  setDraft: (d: Record<string, unknown>) => void;
}) {
  const uxRules = (draft.ux_rules as string[]) ?? [];

  return (
    <div className="space-y-5">
      <Field label="Overview">
        <textarea rows={3} className={ta(3)} value={String(draft.overview ?? "")}
          onChange={(e) => setDraft({ ...draft, overview: e.target.value })} />
      </Field>

      <div>
        <SectionTitle>UX rules</SectionTitle>
        <div className="space-y-1.5">
          {uxRules.map((rule, i) => (
            <div key={i} className="flex gap-2">
              <input className={inp("flex-1")} value={rule}
                onChange={(e) => {
                  const next = [...uxRules];
                  next[i] = e.target.value;
                  setDraft({ ...draft, ux_rules: next });
                }} />
              <button type="button" onClick={() => setDraft({ ...draft, ux_rules: uxRules.filter((_, j) => j !== i) })}
                className="rounded p-1.5 text-gray-600 hover:bg-red-950/40 hover:text-red-400">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
          <AddButton label="Add UX rule" onClick={() => setDraft({ ...draft, ux_rules: [...uxRules, ""] })} />
        </div>
      </div>

      <Field label="Design system (JSON — colors, typography, spacing)">
        <textarea rows={6} className={ta(6, "font-mono text-xs")}
          value={JSON.stringify(draft.design_system ?? {}, null, 2)}
          onChange={(e) => {
            try { setDraft({ ...draft, design_system: JSON.parse(e.target.value) }); } catch { /* keep typing */ }
          }} />
      </Field>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main sheet
// ---------------------------------------------------------------------------

function DocEditor({
  docKey,
  draft,
  setDraft,
}: {
  docKey: DocKey;
  draft: Record<string, unknown>;
  setDraft: (d: Record<string, unknown>) => void;
}) {
  if (docKey === "doc_system_arch") return <SystemArchEditor draft={draft} setDraft={setDraft} />;
  if (docKey === "doc_database") return <DatabaseEditor draft={draft} setDraft={setDraft} />;
  if (docKey === "doc_api") return <ApiEditor draft={draft} setDraft={setDraft} />;
  if (docKey === "doc_frontend") return <FrontendEditor draft={draft} setDraft={setDraft} />;
  if (docKey === "doc_security") return <SecurityEditor draft={draft} setDraft={setDraft} />;
  return <UiUxEditor draft={draft} setDraft={setDraft} />;
}

export function ArchitectureEditSheet({
  open,
  docKey,
  title,
  architectureId,
  initialContent,
  consistencyIssues,
  onClose,
  onSaved,
}: ArchitectureEditSheetProps) {
  const [draft, setDraft] = useState<Record<string, unknown>>(initialContent);
  const [aiInstruction, setAiInstruction] = useState("");
  const [aiModel, setAiModel] = useState<ModelChoice | null>(null);
  const [error, setError] = useState("");
  const aiJob = useAiJob();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      setDraft(structuredClone(initialContent));
      if (consistencyIssues?.length) {
        setAiInstruction(
          "Fix the following consistency issues:\n" +
          consistencyIssues.map((i) => `- ${i}`).join("\n"),
        );
      } else {
        setAiInstruction("");
      }
      setError("");
    }
  }, [open, initialContent, consistencyIssues]);

  if (!open) return null;

  async function handleApplyAi() {
    if (!aiInstruction.trim()) return;
    aiJob.startManual("Applying AI edits");
    setError("");
    try {
      const result = await api.aiEditArchitectureDoc(
        architectureId, docKey, draft, aiInstruction, aiModel,
      );
      setDraft(result.corrected_content);
      aiJob.completeManual();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "AI edit failed";
      setError(msg);
      aiJob.failManual(msg);
    }
  }

  async function handleSave() {
    setError("");
    try {
      await api.updateArchitectureDoc(architectureId, docKey, draft);
      onSaved(draft);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  return (
    <>
      <button
        type="button"
        aria-label="Close edit panel"
        className="fixed inset-0 z-40 bg-black/50"
        onClick={onClose}
      />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col border-l border-gray-800 bg-gray-950 shadow-2xl">
        {/* Header */}
        <header className="flex shrink-0 items-center justify-between border-b border-gray-800 px-4 py-3">
          <div>
            <p className="text-xs text-gray-500">Edit document</p>
            <h2 className="text-lg font-semibold text-white">{title}</h2>
          </div>
          <button
            type="button"
            className="rounded-md p-2 text-gray-400 hover:bg-gray-900 hover:text-white"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        {/* Scrollable body */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4">
          <DocEditor docKey={docKey} draft={draft} setDraft={setDraft} />

          {/* AI instruction */}
          <div className="mt-6 rounded-lg border border-gray-800 bg-gray-900/40 p-4">
            <p className="mb-2 text-xs font-semibold text-gray-400">Ask AI to edit this document</p>
            <textarea
              rows={4}
              className={ta(4)}
              placeholder="Describe what to change — e.g. Add Redis caching component, link it to API and Database"
              value={aiInstruction}
              onChange={(e) => setAiInstruction(e.target.value)}
              disabled={aiJob.isRunning}
            />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <ArchModelSelector value={aiModel} onChange={setAiModel} compact />
              <Button size="sm" disabled={aiJob.isRunning || !aiInstruction.trim()}
                onClick={() => void handleApplyAi()}>
                Apply with AI
              </Button>
            </div>
            {aiJob.isVisible ? (
              <div className="mt-3">
                <AiStatusBar {...aiJobStatusBarProps(aiJob)} operationName={aiJob.operationName} processingMessage={aiJob.processingMessage} />
              </div>
            ) : null}
          </div>

          {error ? <p className="mt-3 text-sm text-red-400">{error}</p> : null}
        </div>

        {/* Footer */}
        <footer className="flex shrink-0 items-center justify-between gap-2 border-t border-gray-800 px-4 py-3">
          <Button variant="outline" disabled={aiJob.isRunning} onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={aiJob.isRunning} onClick={() => void handleSave()}>
            Save changes
          </Button>
        </footer>
      </aside>
    </>
  );
}
