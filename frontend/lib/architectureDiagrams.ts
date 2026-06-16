/**
 * Programmatic Mermaid diagram builders generated from structured architecture
 * data (never from AI free-text). Shared between the on-screen doc view and the
 * PDF export so both render identical, reliable diagrams.
 */

/** Sanitise a value for use as a Mermaid node ID (alphanumeric + underscore only) */
export function nodeId(raw: string): string {
  return raw.replace(/[^a-zA-Z0-9]/g, "_").replace(/^_+|_+$/g, "").slice(0, 30) || "node";
}

/** Sanitise a value for use as a Mermaid label (quote it, escape inner quotes) */
export function nodeLabel(raw: string): string {
  return `"${String(raw).replace(/"/g, "'").replace(/[<>{}|]/g, " ").slice(0, 60)}"`;
}

/** Build a routing flowchart from pages array */
export function buildRoutingDiagram(pages: Array<Record<string, unknown>>): string {
  if (!pages.length) return "";
  const lines = ["flowchart TD", `  Root["/ App"]`];
  const seen = new Set<string>();
  for (const p of pages.slice(0, 18)) {
    const path = String(p.path ?? "");
    if (!path) continue;
    const id = nodeId(path);
    if (seen.has(id)) continue;
    seen.add(id);
    const prot = p.protected !== false ? " 🔒" : "";
    lines.push(`  ${id}[${nodeLabel(path + prot)}]`);
    const parts = path.split("/").filter(Boolean);
    if (parts.length <= 1) {
      lines.push(`  Root --> ${id}`);
    } else {
      const parentPath = "/" + parts.slice(0, -1).join("/");
      const parentId = nodeId(parentPath);
      if (seen.has(parentId)) {
        lines.push(`  ${parentId} --> ${id}`);
      } else {
        lines.push(`  Root --> ${id}`);
      }
    }
  }
  return lines.join("\n");
}

/** Build a component tree flowchart from pages */
export function buildComponentTreeDiagram(pages: Array<Record<string, unknown>>): string {
  if (!pages.length) return "";
  const lines = ["flowchart LR"];
  lines.push(`  App["Next.js 14 App"]`);
  const seen = new Set<string>();
  for (const p of pages.slice(0, 12)) {
    const path = String(p.path ?? "");
    if (!path) continue;
    const id = nodeId(path);
    if (seen.has(id)) continue;
    seen.add(id);
    const pageName = path.split("/").filter(Boolean).pop() ?? path;
    lines.push(`  ${id}[${nodeLabel(pageName + " page")}]`);
    lines.push(`  App --> ${id}`);
    const comps = (p.components as string[] | undefined) ?? [];
    for (const c of comps.slice(0, 4)) {
      const cid = nodeId(id + "_" + c);
      lines.push(`  ${cid}[${nodeLabel(c)}]`);
      lines.push(`  ${id} --> ${cid}`);
    }
  }
  return lines.join("\n");
}

/** Build ERD from tables and relationships */
export function buildErDiagram(
  tables: Array<Record<string, unknown>>,
  relationships: Array<Record<string, string>>,
): string {
  if (!tables.length) return "";
  const lines = ["erDiagram"];
  for (const tbl of tables.slice(0, 14)) {
    const name = String(tbl.name ?? "").toUpperCase().replace(/[^A-Z0-9_]/g, "_");
    if (!name) continue;
    const cols = (tbl.columns as Array<Record<string, unknown>>) ?? [];
    if (cols.length) {
      lines.push(`  ${name} {`);
      for (const col of cols.slice(0, 6)) {
        const type = String(col.type ?? "TEXT").replace(/[^A-Z0-9_]/gi, "_").toUpperCase().slice(0, 20) || "TEXT";
        const colName = String(col.name ?? "").replace(/[^a-z0-9_]/gi, "_").slice(0, 30) || "id";
        const pk = col.pk ? " PK" : "";
        lines.push(`    ${type} ${colName}${pk}`);
      }
      lines.push(`  }`);
    } else {
      lines.push(`  ${name} {`);
      lines.push(`    UUID id PK`);
      lines.push(`  }`);
    }
  }
  const tableNames = new Set(
    tables.slice(0, 14).map((t) => String(t.name ?? "").toUpperCase().replace(/[^A-Z0-9_]/g, "_")),
  );
  const addedRels = new Set<string>();
  for (const rel of (relationships ?? []).slice(0, 20)) {
    const from = String(rel.from ?? rel.table1 ?? "").toUpperCase().replace(/[^A-Z0-9_]/g, "_");
    const to = String(rel.to ?? rel.table2 ?? "").toUpperCase().replace(/[^A-Z0-9_]/g, "_");
    const label = String(rel.type ?? rel.relationship ?? rel.label ?? "has").replace(/"/g, "").slice(0, 20) || "relates";
    if (!from || !to || !tableNames.has(from) || !tableNames.has(to)) continue;
    const key = `${from}|${to}`;
    if (addedRels.has(key)) continue;
    addedRels.add(key);
    lines.push(`  ${from} ||--o{ ${to} : "${label}"`);
  }
  if (!addedRels.size) {
    const tableList = tables.slice(0, 14);
    for (const tbl of tableList) {
      const tName = String(tbl.name ?? "").toUpperCase().replace(/[^A-Z0-9_]/g, "_");
      const cols = (tbl.columns as Array<Record<string, unknown>>) ?? [];
      for (const col of cols) {
        const cName = String(col.name ?? "");
        if (cName.endsWith("_id") && !col.pk) {
          const refTable = cName.slice(0, -3).toUpperCase().replace(/[^A-Z0-9_]/g, "_") + "S";
          if (tableNames.has(refTable)) {
            const key = `${refTable}|${tName}`;
            if (!addedRels.has(key)) {
              addedRels.add(key);
              lines.push(`  ${refTable} ||--o{ ${tName} : "has"`);
            }
          }
        }
      }
    }
  }
  return lines.join("\n");
}

/** Build system overview flowchart from components */
export function buildSystemOverviewDiagram(components: Array<Record<string, unknown>>): string {
  if (!components.length) return "";
  const lines = ["flowchart TD"];
  const ids: string[] = [];
  for (const c of components.slice(0, 10)) {
    const name = String(c.name ?? "");
    const type = String(c.type ?? "");
    const id = nodeId(name);
    ids.push(id);
    const label = nodeLabel(name + (type ? ` (${type})` : ""));
    if (type.toLowerCase().includes("database") || type.toLowerCase().includes("db")) {
      lines.push(`  ${id}[(${label})]`);
    } else if (type.toLowerCase().includes("queue") || type.toLowerCase().includes("cache")) {
      lines.push(`  ${id}[/${label}/]`);
    } else {
      lines.push(`  ${id}[${label}]`);
    }
  }
  for (const c of components.slice(0, 10)) {
    const fromId = nodeId(String(c.name ?? ""));
    const comms = (c.communicates_with as string[]) ?? [];
    for (const target of comms.slice(0, 4)) {
      const toId = nodeId(target);
      if (ids.includes(toId)) {
        lines.push(`  ${fromId} --> ${toId}`);
      }
    }
  }
  return lines.join("\n");
}

/** Build API auth sequence diagram programmatically */
export function buildAuthFlowDiagram(): string {
  return `sequenceDiagram
  participant C as "Client"
  participant API as "FastAPI"
  participant DB as "PostgreSQL"
  C ->> API: POST /api/v1/auth/login
  API ->> DB: validate credentials
  DB -->> API: user record
  API -->> C: Set-Cookie JWT HttpOnly
  C ->> API: GET /api/v1/auth/me (cookie)
  API -->> C: user profile`;
}

/** Build security RBAC flowchart from roles */
export function buildRbacDiagram(roles: Array<string | Record<string, unknown>>): string {
  if (!roles.length) return "";
  const lines = ["flowchart LR", `  Request["API Request"]`];
  lines.push(`  JWT["JWT Verify"]`);
  lines.push(`  Request --> JWT`);
  for (const r of roles.slice(0, 6)) {
    const roleName = typeof r === "string" ? r : String(r.name ?? "role");
    const id = nodeId(roleName);
    lines.push(`  ${id}[${nodeLabel(roleName)}]`);
    lines.push(`  JWT --> ${id}`);
  }
  return lines.join("\n");
}

/**
 * Build the full set of diagrams for a given document, keyed by diagram name.
 * Programmatic builders take priority; AI-stored diagrams fill remaining slots.
 * This is the single source of truth used by both the screen view and the PDF.
 */
export function buildDiagramsForDoc(
  docKey: string,
  doc: Record<string, unknown> | null | undefined,
): Record<string, string> {
  if (!doc) return {};
  const stored = (doc.diagrams as Record<string, string> | undefined) ?? {};
  const out: Record<string, string> = {};

  if (docKey === "doc_system_arch") {
    const components = (doc.components as Array<Record<string, unknown>>) ?? [];
    const sys = buildSystemOverviewDiagram(components);
    if (sys) out.system_overview = sys;
  } else if (docKey === "doc_database") {
    const tables = (doc.tables as Array<Record<string, unknown>>) ?? [];
    const relationships = (doc.relationships as Array<Record<string, string>>) ?? [];
    const erd = buildErDiagram(tables, relationships);
    if (erd) out.erd = erd;
  } else if (docKey === "doc_api") {
    out.auth_flow = buildAuthFlowDiagram();
  } else if (docKey === "doc_frontend") {
    const pages = (doc.pages as Array<Record<string, unknown>>) ?? [];
    const routing = buildRoutingDiagram(pages);
    const tree = buildComponentTreeDiagram(pages);
    if (routing) out.routing = routing;
    if (tree) out.component_tree = tree;
  } else if (docKey === "doc_security") {
    const rbac = (doc.rbac as Record<string, unknown>) ?? {};
    const roles = (rbac.roles as Array<string | Record<string, unknown>>) ?? [];
    out.auth_flow = buildAuthFlowDiagram();
    const rbacDiagram = buildRbacDiagram(roles);
    if (rbacDiagram) out.rbac = rbacDiagram;
  }

  // Fill in any AI-stored diagrams that we didn't generate programmatically
  for (const [name, chart] of Object.entries(stored)) {
    if (!out[name] && chart?.trim()) {
      out[name] = chart;
    }
  }
  return out;
}
