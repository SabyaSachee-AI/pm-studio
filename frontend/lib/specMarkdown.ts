/** Build Markdown from task developer specs (single spec + full-project summary). */

export interface SpecMdTask {
  title: string;
  seq?: number | null;
  priority?: string;
  module_name?: string | null;
  linked_fr?: string | null;
  effort_hours?: number | null;
}

function str(c: Record<string, unknown>, k: string): string {
  const v = c[k];
  return typeof v === "string" ? v : "";
}
function strList(c: Record<string, unknown>, k: string): string[] {
  const v = c[k];
  return Array.isArray(v) ? v.map(String) : [];
}

function taskHeading(task: SpecMdTask): string {
  const seq = task.seq != null ? `Task #${String(task.seq).padStart(3, "0")} — ` : "";
  return `${seq}${task.title}`;
}

function metaLine(task: SpecMdTask): string {
  const parts: string[] = [];
  if (task.priority) parts.push(`**Priority:** ${task.priority}`);
  if (task.module_name) parts.push(`**Module:** ${task.module_name}`);
  if (task.linked_fr) parts.push(`**FR:** ${task.linked_fr}`);
  if (task.effort_hours != null) parts.push(`**Effort:** ${task.effort_hours}h`);
  return parts.join(" · ");
}

/** Markdown body for a single spec (heading level configurable for embedding). */
export function buildSpecMarkdown(
  task: SpecMdTask,
  content: Record<string, unknown>,
  level = 1,
): string {
  const h = "#".repeat(level);
  const sub = "#".repeat(level + 1);
  const out: string[] = [];

  out.push(`${h} ${taskHeading(task)}`);
  const meta = metaLine(task);
  if (meta) out.push(meta);
  out.push("");

  const scope = str(content, "task_scope");
  if (scope) {
    out.push(`${sub} What to build`, "", scope, "");
  }

  const filesCreate = strList(content, "files_to_create");
  const filesModify = strList(content, "files_to_modify");
  if (filesCreate.length || filesModify.length) {
    out.push(`${sub} Files`, "");
    if (filesCreate.length) {
      out.push("**Create:**", "");
      filesCreate.forEach((f) => out.push(`- \`${f}\``));
      out.push("");
    }
    if (filesModify.length) {
      out.push("**Modify:**", "");
      filesModify.forEach((f) => out.push(`- \`${f}\``));
      out.push("");
    }
  }

  const db = content.database as { tables?: Array<{ name?: string; relevant_columns?: Array<{ name?: string; type?: string }> }> } | undefined;
  const tables = Array.isArray(db?.tables) ? db!.tables! : [];
  if (tables.length) {
    out.push(`${sub} Database`, "", "| Table | Relevant columns |", "| --- | --- |");
    tables.forEach((t) => {
      const cols = (t.relevant_columns ?? []).map((c) => `${c.name ?? ""}: ${c.type ?? ""}`).join(", ") || "-";
      out.push(`| \`${t.name ?? "-"}\` | ${cols} |`);
    });
    out.push("");
  }

  const eps = content.api_endpoints as Array<{ method?: string; path?: string; request_body?: string; response_schema?: string; status_code?: string }> | undefined;
  const endpoints = Array.isArray(eps) ? eps : [];
  if (endpoints.length) {
    out.push(`${sub} API endpoints`, "", "| Method | Path | Request / Response |", "| --- | --- | --- |");
    endpoints.forEach((e) => {
      const rr = [
        e.request_body ? `Req: ${e.request_body}` : "",
        e.response_schema ? `Res: ${e.response_schema}${e.status_code ? ` (${e.status_code})` : ""}` : "",
      ].filter(Boolean).join("<br>") || "-";
      out.push(`| ${(e.method ?? "").toUpperCase()} | \`${e.path ?? ""}\` | ${rr} |`);
    });
    out.push("");
  }

  const route = str(content, "frontend_route");
  const component = str(content, "frontend_component");
  if (route || component) {
    out.push(`${sub} Frontend`, "");
    if (route) out.push(`- **Route:** \`${route}\``);
    if (component) out.push(`- **Component:** \`${component}\``);
    out.push("");
  }

  const criteria = strList(content, "acceptance_criteria");
  if (criteria.length) {
    out.push(`${sub} Acceptance criteria`, "");
    criteria.forEach((c) => out.push(`- [ ] ${c}`));
    out.push("");
  }

  const notes = str(content, "technical_notes");
  if (notes) {
    out.push(`${sub} Technical notes`, "", notes, "");
  }

  const summary = str(content, "cursor_prompt");
  if (summary) {
    out.push(`${sub} Implementation summary`, "", "```", summary, "```", "");
  }

  return out.join("\n");
}

export interface AllSpecsItem {
  task: SpecMdTask;
  content: Record<string, unknown>;
}

/** One Markdown document combining every generated spec, ordered by task serial. */
export function buildAllSpecsMarkdown(projectName: string, items: AllSpecsItem[]): string {
  const ordered = [...items].sort((a, b) => (a.task.seq ?? 9e9) - (b.task.seq ?? 9e9));
  const out: string[] = [];

  out.push(`# ${projectName} — Developer Specifications`, "");
  out.push(`_Generated ${new Date().toISOString().slice(0, 10)} · ${ordered.length} task spec${ordered.length === 1 ? "" : "s"}_`, "");

  // Table of contents
  out.push("## Contents", "");
  ordered.forEach((it) => {
    out.push(`- ${taskHeading(it.task)}`);
  });
  out.push("", "---", "");

  ordered.forEach((it, i) => {
    out.push(buildSpecMarkdown(it.task, it.content, 2));
    if (i < ordered.length - 1) out.push("", "---", "");
  });

  return out.join("\n");
}

/** Trigger a browser download of text content. */
export function downloadTextFile(filename: string, text: string, mime = "text/markdown"): void {
  const blob = new Blob([text], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function slugFilename(value: string): string {
  return value.replace(/[^\w.-]+/g, "-").replace(/-+/g, "-").slice(0, 60) || "spec";
}
