import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";

// A4 portrait with comfortable print margins (mm)
const PAGE_W = 210;
const PAGE_H = 297;
const MARGIN = { top: 20, right: 18, bottom: 20, left: 18 };
const CONTENT_W = PAGE_W - MARGIN.left - MARGIN.right;
const ACCENT: [number, number, number] = [79, 70, 229]; // indigo
const HEADING: [number, number, number] = [30, 41, 59];
const MUTED: [number, number, number] = [100, 116, 139];

export interface SpecPdfTask {
  title: string;
  seq?: number | null;
  priority?: string;
  module_name?: string | null;
  linked_fr?: string | null;
  effort_hours?: number | null;
}

export interface SpecPdfOptions {
  task: SpecPdfTask;
  content: Record<string, unknown>;
  projectName: string;
}

function str(c: Record<string, unknown>, k: string): string {
  const v = c[k];
  return typeof v === "string" ? v : "";
}
function strList(c: Record<string, unknown>, k: string): string[] {
  const v = c[k];
  return Array.isArray(v) ? v.map(String) : [];
}

function slug(value: string): string {
  return value.replace(/[^\w.-]+/g, "-").replace(/-+/g, "-").slice(0, 60) || "task";
}

export function buildSpecPdf({ task, content, projectName }: SpecPdfOptions): void {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  let y = MARGIN.top;

  const ensureSpace = (needed: number) => {
    if (y + needed > PAGE_H - MARGIN.bottom) {
      doc.addPage();
      y = MARGIN.top;
    }
  };

  // ── Header band ──────────────────────────────────────────────────────────
  doc.setFillColor(...ACCENT);
  doc.rect(0, 0, PAGE_W, 4, "F");

  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  doc.text(projectName.toUpperCase(), MARGIN.left, y);
  doc.text("DEVELOPER SPECIFICATION", PAGE_W - MARGIN.right, y, { align: "right" });
  y += 7;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(16);
  doc.setTextColor(...HEADING);
  const titlePrefix = task.seq != null ? `Task #${String(task.seq).padStart(3, "0")} — ` : "";
  const titleLines = doc.splitTextToSize(titlePrefix + task.title, CONTENT_W);
  doc.text(titleLines, MARGIN.left, y);
  y += titleLines.length * 6.5 + 1;

  // Meta chips line
  const meta: string[] = [];
  if (task.priority) meta.push(`Priority: ${task.priority}`);
  if (task.module_name) meta.push(`Module: ${task.module_name}`);
  if (task.linked_fr) meta.push(`FR: ${task.linked_fr}`);
  if (task.effort_hours != null) meta.push(`Effort: ${task.effort_hours}h`);
  if (meta.length) {
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9);
    doc.setTextColor(...MUTED);
    doc.text(meta.join("     |     "), MARGIN.left, y);
    y += 5;
  }
  doc.setDrawColor(226, 232, 240);
  doc.line(MARGIN.left, y, PAGE_W - MARGIN.right, y);
  y += 7;

  // ── Section helpers ──────────────────────────────────────────────────────
  const sectionTitle = (label: string) => {
    ensureSpace(12);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(11);
    doc.setTextColor(...ACCENT);
    doc.text(label, MARGIN.left, y);
    y += 5.5;
  };

  const paragraph = (text: string) => {
    if (!text.trim()) return;
    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);
    doc.setTextColor(51, 65, 85);
    const lines = doc.splitTextToSize(text, CONTENT_W);
    for (const line of lines) {
      ensureSpace(5.5);
      doc.text(line, MARGIN.left, y);
      y += 5;
    }
    y += 2;
  };

  const bulletList = (items: string[], mono = false) => {
    doc.setFont(mono ? "courier" : "helvetica", "normal");
    doc.setFontSize(mono ? 9 : 10);
    doc.setTextColor(51, 65, 85);
    const indent = 5;
    for (const item of items) {
      const lines = doc.splitTextToSize(item, CONTENT_W - indent);
      ensureSpace(lines.length * 5 + 1);
      doc.setFillColor(...ACCENT);
      doc.circle(MARGIN.left + 1.2, y - 1.3, 0.7, "F");
      doc.text(lines, MARGIN.left + indent, y);
      y += lines.length * 5 + 1;
    }
    y += 2;
  };

  const table = (head: string[], body: string[][], colWidths: number[]) => {
    const columnStyles: Record<number, { cellWidth: number }> = {};
    colWidths.forEach((w, i) => { columnStyles[i] = { cellWidth: w }; });
    autoTable(doc, {
      startY: y,
      head: [head],
      body,
      margin: { left: MARGIN.left, right: MARGIN.right },
      styles: {
        fontSize: 8,
        cellPadding: 1.8,
        overflow: "linebreak",
        textColor: [51, 65, 85],
        font: "courier",
      },
      headStyles: {
        fillColor: ACCENT,
        textColor: [255, 255, 255],
        fontSize: 8.5,
        font: "helvetica",
        fontStyle: "bold",
      },
      columnStyles,
      alternateRowStyles: { fillColor: [245, 247, 250] },
      theme: "grid",
    });
    // @ts-expect-error lastAutoTable is attached by the plugin
    y = (doc.lastAutoTable?.finalY ?? y) + 5;
  };

  // ── Scope ────────────────────────────────────────────────────────────────
  const scope = str(content, "task_scope");
  if (scope) {
    sectionTitle("What to build");
    paragraph(scope);
  }

  // ── Files ────────────────────────────────────────────────────────────────
  const filesCreate = strList(content, "files_to_create");
  const filesModify = strList(content, "files_to_modify");
  if (filesCreate.length || filesModify.length) {
    sectionTitle("Files");
    if (filesCreate.length) {
      paragraph("Create:");
      bulletList(filesCreate, true);
    }
    if (filesModify.length) {
      paragraph("Modify:");
      bulletList(filesModify, true);
    }
  }

  // ── Database ─────────────────────────────────────────────────────────────
  const db = content.database as { tables?: Array<{ name?: string; relevant_columns?: Array<{ name?: string; type?: string }> }> } | undefined;
  const tables = Array.isArray(db?.tables) ? db!.tables! : [];
  if (tables.length) {
    sectionTitle("Database");
    table(
      ["Table", "Relevant columns"],
      tables.map((t) => [
        t.name ?? "-",
        (t.relevant_columns ?? []).map((c) => `${c.name ?? ""}: ${c.type ?? ""}`).join(", ") || "-",
      ]),
      [48, CONTENT_W - 48],
    );
  }

  // ── API endpoints ────────────────────────────────────────────────────────
  const eps = content.api_endpoints as Array<{ method?: string; path?: string; request_body?: string; response_schema?: string; status_code?: string }> | undefined;
  const endpoints = Array.isArray(eps) ? eps : [];
  if (endpoints.length) {
    sectionTitle("API endpoints");
    table(
      ["Method", "Path", "Request / Response"],
      endpoints.map((e) => [
        (e.method ?? "").toUpperCase(),
        e.path ?? "",
        [
          e.request_body ? `Req: ${e.request_body}` : "",
          e.response_schema ? `Res: ${e.response_schema}${e.status_code ? ` (${e.status_code})` : ""}` : "",
        ].filter(Boolean).join("\n") || "-",
      ]),
      [20, 42, CONTENT_W - 62],
    );
  }

  // ── Frontend ─────────────────────────────────────────────────────────────
  const route = str(content, "frontend_route");
  const component = str(content, "frontend_component");
  if (route || component) {
    sectionTitle("Frontend");
    if (route) paragraph(`Route: ${route}`);
    if (component) paragraph(`Component: ${component}`);
  }

  // ── Acceptance criteria ──────────────────────────────────────────────────
  const criteria = strList(content, "acceptance_criteria");
  if (criteria.length) {
    sectionTitle("Acceptance criteria");
    bulletList(criteria.map((c) => `[ ] ${c}`));
  }

  // ── Technical notes ──────────────────────────────────────────────────────
  const notes = str(content, "technical_notes");
  if (notes) {
    sectionTitle("Technical notes");
    paragraph(notes);
  }

  // ── Implementation summary (cursor prompt) ───────────────────────────────
  const summary = str(content, "cursor_prompt");
  if (summary) {
    sectionTitle("Implementation summary");
    doc.setFont("courier", "normal");
    doc.setFontSize(8.5);
    doc.setTextColor(71, 85, 105);
    const lines = doc.splitTextToSize(summary, CONTENT_W);
    for (const line of lines) {
      ensureSpace(4.6);
      doc.text(line, MARGIN.left, y);
      y += 4.3;
    }
  }

  // ── Footers ──────────────────────────────────────────────────────────────
  const pageCount = doc.getNumberOfPages();
  for (let i = 1; i <= pageCount; i += 1) {
    doc.setPage(i);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(...MUTED);
    doc.text(
      `${projectName} — developer spec`,
      MARGIN.left,
      PAGE_H - 10,
    );
    doc.text(`Page ${i} of ${pageCount}`, PAGE_W - MARGIN.right, PAGE_H - 10, { align: "right" });
  }

  doc.save(`${slug(projectName)}-spec-${slug(task.title)}.pdf`);
}
