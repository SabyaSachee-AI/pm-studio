"use client";

import { MermaidDiagram } from "@/components/ui/MermaidDiagram";
import {
  buildAuthFlowDiagram,
  buildComponentTreeDiagram,
  buildErDiagram,
  buildRbacDiagram,
  buildRoutingDiagram,
  buildSystemOverviewDiagram,
} from "@/lib/architectureDiagrams";

// ---------------------------------------------------------------------------
// Diagram panel — tries programmatic first, falls back to AI-stored string
// ---------------------------------------------------------------------------

function DiagramPanel({
  title,
  generated,
  stored,
  id,
}: {
  title: string;
  generated?: string;
  stored?: string;
  id: string;
}) {
  const chart = generated?.trim() ? generated : (stored ?? "");
  if (!chart) return null;
  return (
    <div className="print:break-inside-avoid">
      <h4 className="mb-2 text-sm font-medium text-gray-300">{title}</h4>
      <MermaidDiagram chart={chart} id={id} />
    </div>
  );
}

function StoredDiagrams({
  diagrams,
  exclude,
  prefix,
}: {
  diagrams?: Record<string, string>;
  exclude?: string[];
  prefix: string;
}) {
  if (!diagrams) return null;
  const entries = Object.entries(diagrams).filter(
    ([name]) => !exclude?.includes(name),
  );
  if (!entries.length) return null;
  return (
    <>
      {entries.map(([name, chart]) => (
        <div key={name} className="print:break-inside-avoid">
          <h4 className="mb-2 text-sm font-medium text-gray-300">
            {name.replace(/_/g, " ")}
          </h4>
          <MermaidDiagram chart={chart} id={`${prefix}-${name}`} />
        </div>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Method badge
// ---------------------------------------------------------------------------

function methodBadgeClass(method: string): string {
  const m = method.toUpperCase();
  if (m === "POST") return "bg-green-800 text-green-100";
  if (m === "GET") return "bg-blue-800 text-blue-100";
  if (m === "PATCH" || m === "PUT") return "bg-amber-800 text-amber-100";
  if (m === "DELETE") return "bg-red-800 text-red-100";
  return "bg-gray-700 text-gray-200";
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ArchitectureDocView({
  docKey,
  doc,
}: {
  docKey: string;
  doc: Record<string, unknown> | null;
}) {
  if (!doc) {
    return <p className="text-gray-500">Document not generated yet.</p>;
  }

  const diagrams = doc.diagrams as Record<string, string> | undefined;

  // ── System architecture ──────────────────────────────────────────────────
  if (docKey === "doc_system_arch") {
    const stack = (doc.tech_stack as Record<string, Record<string, string>>) ?? {};
    const components = (doc.components as Array<Record<string, unknown>>) ?? [];
    const systemOverview = buildSystemOverviewDiagram(components);
    return (
      <div className="space-y-6 text-sm text-gray-300">
        <p>{String(doc.overview ?? "")}</p>
        {doc.architecture_pattern ? (
          <p><strong>Pattern:</strong> {String(doc.architecture_pattern)}</p>
        ) : null}
        {Object.keys(stack).length > 0 ? (
          <section>
            <h3 className="font-medium text-white">Tech stack</h3>
            <table className="mt-2 w-full text-xs">
              <thead>
                <tr className="border-b border-gray-700 text-left text-gray-500">
                  <th className="py-1">Layer</th><th>Name</th><th>Version</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(stack).map(([layer, item]) => (
                  <tr key={layer} className="border-b border-gray-800">
                    <td className="py-2 capitalize">{layer.replace(/_/g, " ")}</td>
                    <td>{item?.name ?? ""}</td>
                    <td>{item?.version ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ) : null}
        {components.length > 0 ? (
          <section>
            <h3 className="font-medium text-white">Components</h3>
            <ul className="mt-2 space-y-2">
              {components.map((c, i) => (
                <li key={i} className="rounded border border-gray-800 p-3">
                  <strong>{String(c.name)}</strong> ({String(c.type)})
                  <p className="mt-1 text-gray-400">{String(c.responsibility ?? "")}</p>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        <div className="space-y-4">
          <DiagramPanel title="System overview" generated={systemOverview} stored={diagrams?.system_overview} id="sys-system_overview" />
          <StoredDiagrams diagrams={diagrams} exclude={["system_overview"]} prefix="sys" />
        </div>
      </div>
    );
  }

  // ── Database ─────────────────────────────────────────────────────────────
  if (docKey === "doc_database") {
    const tables = (doc.tables as Array<Record<string, unknown>>) ?? [];
    const relationships = (doc.relationships as Array<Record<string, string>>) ?? [];
    const erd = buildErDiagram(tables, relationships);
    return (
      <div className="space-y-6 text-sm text-gray-300">
        <p>{String(doc.overview ?? "")}</p>
        {tables.map((tbl, i) => {
          const columns = (tbl.columns as Array<Record<string, unknown>>) ?? [];
          const indexes = (tbl.indexes as Array<Record<string, unknown>>) ?? [];
          return (
            <section key={i} className="rounded border border-gray-800 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-medium text-white">{String(tbl.name)}</h3>
                {tbl.linked_srs_entity ? (
                  <span className="rounded bg-blue-950/60 px-2 py-0.5 text-xs text-blue-300">
                    {String(tbl.linked_srs_entity)}
                  </span>
                ) : null}
                {tbl.mvp_scope ? (
                  <span className={`rounded px-2 py-0.5 text-xs ${String(tbl.mvp_scope) === "v1" ? "bg-green-950/60 text-green-300" : "bg-gray-800 text-gray-400"}`}>
                    {String(tbl.mvp_scope)}
                  </span>
                ) : null}
              </div>
              {tbl.purpose ? <p className="mt-1 text-xs text-gray-500">{String(tbl.purpose)}</p> : null}
              {columns.length > 0 ? (
                <table className="mt-3 w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-700 text-left text-gray-500">
                      <th className="py-1 pr-3">Column</th>
                      <th className="pr-3">Type</th>
                      <th className="pr-3">Nullable</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {columns.map((col, ci) => (
                      <tr key={ci} className="border-b border-gray-800/60">
                        <td className="py-1 pr-3 font-mono text-gray-200">
                          {col.pk ? <span className="mr-1 text-yellow-400">🔑</span> : null}
                          {String(col.name ?? "")}
                        </td>
                        <td className="pr-3 font-mono text-blue-300">{String(col.type ?? "")}</td>
                        <td className="pr-3 text-gray-500">{col.nullable === false ? "NOT NULL" : "null"}</td>
                        <td className="text-gray-500">{String(col.default ?? "")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}
              {indexes.length > 0 ? (
                <p className="mt-2 text-xs text-gray-500">
                  <strong>Indexes:</strong> {indexes.map((ix) => String(ix.columns ?? ix.name ?? ix)).join(", ")}
                </p>
              ) : null}
              {tbl.constraints && (tbl.constraints as string[]).length > 0 ? (
                <p className="mt-1 text-xs text-gray-500">
                  <strong>Constraints:</strong> {(tbl.constraints as string[]).join(" · ")}
                </p>
              ) : null}
            </section>
          );
        })}
        <div className="space-y-4">
          <DiagramPanel title="Entity relationship diagram" generated={erd} stored={diagrams?.erd} id="db-erd" />
          <StoredDiagrams diagrams={diagrams} exclude={["erd"]} prefix="db" />
        </div>
      </div>
    );
  }

  // ── API ──────────────────────────────────────────────────────────────────
  if (docKey === "doc_api") {
    const endpoints = (doc.endpoints as Array<Record<string, unknown>>) ?? [];
    const authFlow = buildAuthFlowDiagram();
    return (
      <div className="space-y-6 text-sm text-gray-300">
        <p>{String(doc.overview ?? "")}</p>
        <div className="space-y-3">
          {endpoints.map((ep, i) => (
            <div key={i} className="rounded border border-gray-800 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-xs font-mono ${methodBadgeClass(String(ep.method))}`}>
                  {String(ep.method)}
                </span>
                <code className="text-xs">{String(ep.full_path ?? ep.path)}</code>
                {ep.linked_fr ? (
                  <span className="rounded bg-gray-800 px-1.5 py-0.5 text-xs text-gray-400">{String(ep.linked_fr)}</span>
                ) : null}
                {ep.mvp_scope ? (
                  <span className={`rounded px-1.5 py-0.5 text-xs ${String(ep.mvp_scope) === "v1" ? "text-green-400" : "text-gray-500"}`}>
                    {String(ep.mvp_scope)}
                  </span>
                ) : null}
              </div>
              <p className="mt-2 text-gray-400">{String(ep.description ?? "")}</p>
            </div>
          ))}
        </div>
        <div className="space-y-4">
          <DiagramPanel title="Auth flow" generated={authFlow} stored={diagrams?.auth_flow} id="api-auth_flow" />
          <StoredDiagrams diagrams={diagrams} exclude={["auth_flow"]} prefix="api" />
        </div>
      </div>
    );
  }

  // ── Frontend ─────────────────────────────────────────────────────────────
  if (docKey === "doc_frontend") {
    const pages = (doc.pages as Array<Record<string, unknown>>) ?? [];
    const routing = buildRoutingDiagram(pages);
    const componentTree = buildComponentTreeDiagram(pages);
    return (
      <div className="space-y-6 text-sm text-gray-300">
        <p>{String(doc.overview ?? "")}</p>
        <ul className="space-y-2">
          {pages.map((p, i) => (
            <li key={i} className="rounded border border-gray-800 p-3">
              <code className="text-blue-300">{String(p.path)}</code>
              <span className="ml-2 text-gray-400">{String(p.description ?? "")}</span>
              {(p.api_calls as string[] | undefined)?.length ? (
                <p className="mt-1 text-xs text-gray-600">
                  API: {(p.api_calls as string[]).slice(0, 4).join(", ")}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
        <div className="space-y-4">
          <DiagramPanel title="Routing" generated={routing} id="fe-routing" />
          <DiagramPanel title="Component tree" generated={componentTree} id="fe-component_tree" />
          <StoredDiagrams diagrams={diagrams} exclude={["routing", "component_tree"]} prefix="fe" />
        </div>
      </div>
    );
  }

  // ── Security ─────────────────────────────────────────────────────────────
  if (docKey === "doc_security") {
    const rbac = (doc.rbac as Record<string, unknown>) ?? {};
    const roles = (rbac.roles as Array<string | Record<string, unknown>>) ?? [];
    const matrix = rbac.permission_matrix as Record<string, string[]> | Array<Record<string, string>> | undefined;
    const rbacDiagram = buildRbacDiagram(roles);
    const authFlow = buildAuthFlowDiagram();
    return (
      <div className="space-y-6 text-sm text-gray-300">
        <p>{String(doc.overview ?? "")}</p>
        {roles.length > 0 ? (
          <section>
            <h3 className="font-medium text-white">Roles</h3>
            <ul className="mt-2 space-y-1">
              {roles.map((r, i) => {
                const name = typeof r === "string" ? r : String((r as Record<string, unknown>).name ?? "");
                const desc = typeof r === "object" ? String((r as Record<string, unknown>).description ?? "") : "";
                return (
                  <li key={i} className="flex gap-2 text-xs">
                    <span className="rounded bg-gray-800 px-2 py-0.5 font-mono text-blue-300">{name}</span>
                    {desc ? <span className="text-gray-500">{desc}</span> : null}
                  </li>
                );
              })}
            </ul>
          </section>
        ) : null}
        {matrix ? (
          <section>
            <h3 className="font-medium text-white">Permission matrix</h3>
            {Array.isArray(matrix) ? (
              <table className="mt-2 w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-700 text-left text-gray-500">
                    <th className="py-1">Resource</th>
                    {Object.keys(matrix[0] ?? {}).filter((k) => k !== "resource").map((k) => (
                      <th key={k} className="capitalize">{k.replace(/_/g, " ")}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {matrix.map((row, i) => (
                    <tr key={i} className="border-b border-gray-800">
                      {Object.values(row).map((v, j) => (
                        <td key={j} className="py-1 pr-3">{String(v)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <table className="mt-2 w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-700 text-left text-gray-500">
                    <th className="py-1">Role</th><th>Permissions</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(matrix).map(([role, perms]) => (
                    <tr key={role} className="border-b border-gray-800">
                      <td className="py-1 pr-3 font-mono text-blue-300">{role}</td>
                      <td className="text-gray-400">{Array.isArray(perms) ? perms.join(", ") : String(perms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        ) : null}
        <div className="space-y-4">
          <DiagramPanel title="Auth flow" generated={authFlow} id="sec-auth_flow" />
          <DiagramPanel title="RBAC flow" generated={rbacDiagram} id="sec-rbac_flow" />
          <StoredDiagrams diagrams={diagrams} exclude={["auth_flow", "rbac_flow"]} prefix="sec" />
        </div>
      </div>
    );
  }

  // ── UI/UX ────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6 text-sm text-gray-300">
      <p>{String(doc.overview ?? "")}</p>
      {(doc.ux_rules as string[] | undefined)?.length ? (
        <section>
          <h3 className="font-medium text-white">UX rules</h3>
          <ul className="mt-2 list-inside list-disc space-y-1 text-gray-400">
            {(doc.ux_rules as string[]).map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </section>
      ) : null}
      <div className="space-y-4">
        <StoredDiagrams diagrams={diagrams} prefix="ux" />
      </div>
    </div>
  );
}
