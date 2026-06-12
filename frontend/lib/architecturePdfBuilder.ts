import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import {
  DOC_TAB_META,
  type ArchDocKey,
} from "@/components/features/architecture/ArchitecturePrintDocument";
import type {
  ArchitecturePdfArch,
  ArchitecturePdfMode,
  DiagramImageMap,
} from "@/lib/architecturePdfExport";

const MARGIN = { top: 28, right: 18, bottom: 22, left: 18 };
const PAGE_W = 210;
const PAGE_H = 297;
const CONTENT_W = PAGE_W - MARGIN.left - MARGIN.right;
const HEADER_COLOR: [number, number, number] = [30, 58, 95];
const ACCENT: [number, number, number] = [59, 130, 246];
const PX_TO_MM = 25.4 / 96;
const WIDE_ASPECT_RATIO = 1.25;

type JsPdfDoc = jsPDF & { lastAutoTable?: { finalY: number } };

interface TocEntry {
  number: string;
  title: string;
  page: number;
}

interface ReportMeta {
  projectName: string;
  docTitle: string;
  version: number;
  status: string;
  displayName?: string | null;
  mode: ArchitecturePdfMode;
}

function normalizeTechStack(
  raw: unknown,
): Array<{ layer: string; name: string; version: string; reason: string }> {
  if (!raw || typeof raw !== "object") return [];
  if (Array.isArray(raw)) {
    return raw.map((item, i) => {
      const row = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
      return {
        layer: String(row.layer ?? row.name ?? `layer_${i + 1}`),
        name: String(row.name ?? ""),
        version: String(row.version ?? ""),
        reason: String(row.reason ?? ""),
      };
    });
  }
  return Object.entries(raw as Record<string, unknown>).map(([layer, item]) => {
    if (typeof item === "string") return { layer, name: item, version: "", reason: "" };
    const row = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
    return {
      layer,
      name: String(row.name ?? ""),
      version: String(row.version ?? ""),
      reason: String(row.reason ?? ""),
    };
  });
}

function flattenFolder(node: unknown, prefix = ""): string[] {
  if (node === null || node === undefined) return [];
  if (typeof node === "string" || typeof node === "number" || typeof node === "boolean") {
    return [`${prefix}${node}`];
  }
  if (Array.isArray(node)) {
    return node.flatMap((item) => flattenFolder(item, `${prefix}  `));
  }
  if (typeof node === "object") {
    return Object.entries(node as Record<string, unknown>).flatMap(([name, child]) => {
      const line = `${prefix}${name}`;
      const children = flattenFolder(child, `${prefix}  `);
      return children.length > 0 ? [line, ...children] : [line];
    });
  }
  return [];
}

function humanize(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function methodColor(method: string): [number, number, number] {
  const m = method.toUpperCase();
  if (m === "GET") return [37, 99, 235];
  if (m === "POST") return [22, 163, 74];
  if (m === "PUT" || m === "PATCH") return [217, 119, 6];
  if (m === "DELETE") return [220, 38, 38];
  return [100, 116, 139];
}

class PdfWriter {
  private y = MARGIN.top;
  private readonly doc: JsPdfDoc;
  private readonly meta: ReportMeta;
  private currentSection = "";
  private subsectionCounter = 0;
  private figureCounter = 0;
  private readonly tocEntries: TocEntry[] = [];
  private tocPage = 0;

  constructor(meta: ReportMeta) {
    this.doc = new jsPDF({ unit: "mm", format: "a4", orientation: "portrait" }) as JsPdfDoc;
    this.meta = meta;
  }

  getCurrentPage(): number {
    return this.doc.getNumberOfPages();
  }

  private pageBottom(): number {
    return PAGE_H - MARGIN.bottom;
  }

  private newPage(): void {
    this.doc.addPage();
    this.y = MARGIN.top;
  }

  private ensureSpace(mm: number): void {
    if (this.y + mm > this.pageBottom()) {
      this.newPage();
    }
  }

  private lines(text: string, fontSize: number, maxWidth = CONTENT_W): string[] {
    this.doc.setFontSize(fontSize);
    return this.doc.splitTextToSize(text, maxWidth) as string[];
  }

  private writeJustified(text: string, fontSize: number, lineHeight: number): void {
    if (!text.trim()) return;
    const lines = this.lines(text, fontSize);
    this.doc.setFont("helvetica", "normal");
    this.doc.setFontSize(fontSize);
    this.doc.setTextColor(30, 41, 59);
    for (const line of lines) {
      this.ensureSpace(lineHeight);
      this.doc.text(line, MARGIN.left, this.y, { align: "justify", maxWidth: CONTENT_W });
      this.y += lineHeight;
    }
    this.y += 2;
    this.doc.setTextColor(0, 0, 0);
  }

  coverPage(): void {
    this.doc.setFillColor(...HEADER_COLOR);
    this.doc.rect(0, 0, PAGE_W, 42, "F");

    this.doc.setTextColor(255, 255, 255);
    this.doc.setFont("helvetica", "bold");
    this.doc.setFontSize(11);
    this.doc.text("PM STUDIO — TECHNICAL ARCHITECTURE REPORT", PAGE_W / 2, 18, { align: "center" });
    this.doc.setFontSize(9);
    this.doc.setFont("helvetica", "normal");
    this.doc.text("Formal architecture suite documentation", PAGE_W / 2, 28, { align: "center" });

    this.y = 62;
    this.doc.setTextColor(...HEADER_COLOR);
    this.doc.setFont("helvetica", "bold");
    this.doc.setFontSize(22);
    const titleLines = this.lines(this.meta.docTitle, 22, CONTENT_W - 10);
    titleLines.forEach((line, i) => {
      this.doc.text(line, PAGE_W / 2, this.y + i * 11, { align: "center" });
    });
    this.y += titleLines.length * 11 + 8;

    this.doc.setDrawColor(...ACCENT);
    this.doc.setLineWidth(0.8);
    this.doc.line(PAGE_W / 2 - 30, this.y, PAGE_W / 2 + 30, this.y);
    this.y += 14;

    this.doc.setTextColor(51, 65, 85);
    this.doc.setFont("helvetica", "bold");
    this.doc.setFontSize(14);
    this.doc.text(this.meta.projectName, PAGE_W / 2, this.y, { align: "center" });
    this.y += 20;

    const infoRows = [
      ["Document version", `v${this.meta.version}`],
      ["Document status", String(this.meta.status).toUpperCase()],
      ["Issue date", new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })],
      ["Classification", "Internal — Technical"],
      ...(this.meta.displayName ? [["Suite name", this.meta.displayName]] : []),
    ] as string[][];

    autoTable(this.doc, {
      startY: this.y,
      margin: { left: 35, right: 35 },
      body: infoRows,
      theme: "plain",
      styles: { fontSize: 10, cellPadding: 3, textColor: [51, 65, 85] },
      columnStyles: {
        0: { fontStyle: "bold", cellWidth: 55, textColor: HEADER_COLOR },
        1: { cellWidth: 85 },
      },
    });

    this.y = (this.doc.lastAutoTable?.finalY ?? this.y) + 20;
    this.doc.setFont("helvetica", "italic");
    this.doc.setFontSize(9);
    this.doc.setTextColor(100, 116, 139);
    this.doc.text(
      "This document describes the complete technical architecture for the project named above.",
      PAGE_W / 2,
      PAGE_H - 35,
      { align: "center", maxWidth: CONTENT_W },
    );
    this.doc.setTextColor(0, 0, 0);
    this.doc.setFont("helvetica", "normal");
  }

  documentControlPage(): void {
    this.newPage();
    this.y = MARGIN.top;
    this.pageHeading("Document control", false);

    this.subsection("Purpose", "This report consolidates all architecture suite deliverables into a single formal document suitable for technical review, implementation, and sign-off.");

    this.subsection("Scope", this.meta.mode === "full"
      ? "Full architecture suite: system architecture, database design, API specification, frontend architecture, security and RBAC, and UI/UX guidance."
      : `Single section export: ${this.meta.docTitle}.`);

    this.h4("Document contents");
    const contents = DOC_TAB_META.map((t, i) => [`${i + 1}.0`, t.title]);
    this.table([["Section", "Title"]], contents, { fontSize: 9.5 });

    this.h4("Revision history");
    this.table(
      [["Version", "Date", "Author", "Description"]],
      [[`v${this.meta.version}`, new Date().toLocaleDateString("en-GB"), "PM Studio", "Architecture suite generation"]],
      { fontSize: 9 },
    );

    this.tocPage = this.getCurrentPage() + 1;
    this.newPage();
    this.pageHeading("Table of contents", false);
    this.y += 4;
  }

  fillTableOfContents(): void {
    if (!this.tocPage || this.tocEntries.length === 0) return;
    this.doc.setPage(this.tocPage);
    this.y = MARGIN.top + 14;

    for (const entry of this.tocEntries) {
      const leader = ".".repeat(Math.max(4, 62 - entry.title.length - entry.number.length));
      this.doc.setFont("helvetica", "normal");
      this.doc.setFontSize(10);
      this.doc.setTextColor(30, 41, 59);
      this.doc.text(`${entry.number}  ${entry.title}`, MARGIN.left, this.y);
      this.doc.setTextColor(100, 116, 139);
      this.doc.text(`${leader} ${entry.page}`, PAGE_W - MARGIN.right, this.y, { align: "right" });
      this.y += 6;
    }
    this.doc.setTextColor(0, 0, 0);
  }

  beginSection(sectionNum: number, title: string): void {
    this.newPage();
    this.currentSection = `${sectionNum}`;
    this.subsectionCounter = 0;
    this.figureCounter = 0;
    this.tocEntries.push({ number: `${sectionNum}.0`, title, page: this.getCurrentPage() });

    this.doc.setFillColor(...HEADER_COLOR);
    this.doc.roundedRect(MARGIN.left, this.y - 6, CONTENT_W, 14, 2, 2, "F");
    this.doc.setTextColor(255, 255, 255);
    this.doc.setFont("helvetica", "bold");
    this.doc.setFontSize(14);
    this.doc.text(`${sectionNum}.0  ${title}`, MARGIN.left + 4, this.y + 3);
    this.doc.setTextColor(0, 0, 0);
    this.y += 16;
  }

  pageHeading(text: string, withRule = true): void {
    this.doc.setFont("helvetica", "bold");
    this.doc.setFontSize(16);
    this.doc.setTextColor(...HEADER_COLOR);
    this.doc.text(text, MARGIN.left, this.y);
    this.y += 8;
    if (withRule) {
      this.doc.setDrawColor(203, 213, 225);
      this.doc.setLineWidth(0.4);
      this.doc.line(MARGIN.left, this.y, PAGE_W - MARGIN.right, this.y);
      this.y += 6;
    }
    this.doc.setTextColor(0, 0, 0);
    this.doc.setFont("helvetica", "normal");
  }

  subsection(title: string, body?: string): void {
    this.subsectionCounter += 1;
    const num = `${this.currentSection}.${this.subsectionCounter}`;
    this.h4(`${num}  ${title}`);
    if (body) this.writeJustified(body, 10.5, 5.2);
  }

  h4(text: string): void {
    this.ensureSpace(10);
    this.doc.setFont("helvetica", "bold");
    this.doc.setFontSize(11);
    this.doc.setTextColor(51, 65, 85);
    const lines = this.lines(text, 11);
    for (const line of lines) {
      this.ensureSpace(5.5);
      this.doc.text(line, MARGIN.left, this.y);
      this.y += 5.5;
    }
    this.y += 2;
    this.doc.setTextColor(0, 0, 0);
    this.doc.setFont("helvetica", "normal");
  }

  overviewBlock(text: string): void {
    if (!text.trim()) return;
    this.ensureSpace(20);
    this.doc.setFillColor(248, 250, 252);
    this.doc.setDrawColor(226, 232, 240);
    const lines = this.lines(text, 10.5);
    const boxH = lines.length * 5.2 + 10;
    this.doc.roundedRect(MARGIN.left, this.y, CONTENT_W, boxH, 2, 2, "FD");
    this.doc.setFont("helvetica", "bold");
    this.doc.setFontSize(9);
    this.doc.setTextColor(...HEADER_COLOR);
    this.doc.text("Overview", MARGIN.left + 4, this.y + 6);
    this.doc.setFont("helvetica", "normal");
    this.doc.setFontSize(10.5);
    this.doc.setTextColor(30, 41, 59);
    let ly = this.y + 12;
    for (const line of lines) {
      this.doc.text(line, MARGIN.left + 4, ly, { align: "justify", maxWidth: CONTENT_W - 8 });
      ly += 5.2;
    }
    this.y += boxH + 6;
    this.doc.setTextColor(0, 0, 0);
  }

  labeledValue(label: string, value: string): void {
    if (!value.trim()) return;
    this.ensureSpace(6);
    this.doc.setFont("helvetica", "bold");
    this.doc.setFontSize(10);
    this.doc.setTextColor(51, 65, 85);
    this.doc.text(`${label}:`, MARGIN.left, this.y);
    this.doc.setFont("helvetica", "normal");
    this.doc.setTextColor(30, 41, 59);
    const labelW = this.doc.getTextWidth(`${label}: `);
    const lines = this.lines(value, 10, CONTENT_W - labelW);
    lines.forEach((line, i) => {
      this.doc.text(line, MARGIN.left + (i === 0 ? labelW : 0), this.y + i * 5);
    });
    this.y += lines.length * 5 + 3;
    this.doc.setTextColor(0, 0, 0);
  }

  bulletList(items: string[]): void {
    for (const item of items) {
      const lines = this.lines(`•  ${item}`, 10.5, CONTENT_W - 6);
      this.doc.setFont("helvetica", "normal");
      this.doc.setFontSize(10.5);
      this.doc.setTextColor(30, 41, 59);
      for (const line of lines) {
        this.ensureSpace(5.2);
        this.doc.text(line, MARGIN.left + 2, this.y);
        this.y += 5.2;
      }
    }
    this.y += 2;
    this.doc.setTextColor(0, 0, 0);
  }

  numberedList(items: string[]): void {
    items.forEach((item, i) => {
      const lines = this.lines(`${i + 1}.  ${item}`, 10.5, CONTENT_W - 6);
      for (const line of lines) {
        this.ensureSpace(5.2);
        this.doc.setFont("helvetica", "normal");
        this.doc.setFontSize(10.5);
        this.doc.setTextColor(30, 41, 59);
        this.doc.text(line, MARGIN.left + 2, this.y);
        this.y += 5.2;
      }
    });
    this.y += 2;
    this.doc.setTextColor(0, 0, 0);
  }

  table(
    head: string[][],
    body: string[][],
    opts?: { fontSize?: number; methodColumn?: boolean },
  ): void {
    if (body.length === 0) return;
    this.ensureSpace(14);
    autoTable(this.doc, {
      startY: this.y,
      margin: { left: MARGIN.left, right: MARGIN.right },
      head,
      body,
      styles: {
        fontSize: opts?.fontSize ?? 9,
        cellPadding: 2.5,
        overflow: "linebreak",
        lineColor: [226, 232, 240],
        lineWidth: 0.2,
        textColor: [30, 41, 59],
      },
      headStyles: {
        fillColor: HEADER_COLOR,
        textColor: 255,
        fontStyle: "bold",
        fontSize: (opts?.fontSize ?? 9) + 0.5,
      },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      theme: "grid",
      didParseCell: opts?.methodColumn
        ? (data) => {
            if (data.section === "body" && data.column.index === 0) {
              const method = data.cell.text[0] ?? "";
              data.cell.styles.textColor = methodColor(method);
              data.cell.styles.fontStyle = "bold";
            }
          }
        : undefined,
    });
    this.y = (this.doc.lastAutoTable?.finalY ?? this.y) + 6;
  }

  keyValueTable(data: Record<string, unknown>): void {
    const rows = Object.entries(data)
      .filter(([, v]) => v !== undefined && v !== null)
      .map(([k, v]) => [humanize(k), typeof v === "object" ? JSON.stringify(v) : String(v)]);
    if (rows.length === 0) {
      this.writeJustified("No conventions specified.", 10, 5);
      return;
    }
    this.table([["Field", "Value"]], rows);
  }

  beginFigures(): void {
    if (this.figureCounter > 0) return;
    this.ensureSpace(10);
    this.h4(`${this.currentSection}.x  Architecture diagrams`);
    this.writeJustified(
      "The following figures illustrate key structural and behavioural aspects of this section. Each diagram is rendered from the authoritative Mermaid source produced during architecture generation.",
      10,
      5,
    );
  }

  figurePage(
    name: string,
    dataUrl: string,
    widthPx: number,
    heightPx: number,
    aspectRatio: number,
  ): void {
    this.figureCounter += 1;
    const figureId = `Figure ${this.currentSection}-${this.figureCounter}`;
    const caption = humanize(name);
    const useLandscape = aspectRatio >= WIDE_ASPECT_RATIO;

    if (useLandscape) {
      this.doc.addPage("a4", "landscape");
    } else {
      this.newPage();
    }

    const pageW = useLandscape ? PAGE_H : PAGE_W;
    const pageH = useLandscape ? PAGE_W : PAGE_H;
    const contentW = pageW - MARGIN.left - MARGIN.right;
    const contentH = pageH - MARGIN.top - MARGIN.bottom - 24;

    this.doc.setFont("helvetica", "bold");
    this.doc.setFontSize(11);
    this.doc.setTextColor(...HEADER_COLOR);
    this.doc.text(figureId, MARGIN.left, MARGIN.top);
    this.doc.setFont("helvetica", "normal");
    this.doc.setFontSize(10);
    this.doc.setTextColor(71, 85, 105);
    this.doc.text(caption, MARGIN.left, MARGIN.top + 6);

    let imgWmm = widthPx * PX_TO_MM;
    let imgHmm = heightPx * PX_TO_MM;
    const scale = Math.min(contentW / imgWmm, contentH / imgHmm, 1);
    imgWmm *= scale;
    imgHmm *= scale;

    const x = MARGIN.left + (contentW - imgWmm) / 2;
    const y = MARGIN.top + 14 + (contentH - imgHmm) / 2;

    this.doc.setDrawColor(203, 213, 225);
    this.doc.setLineWidth(0.4);
    this.doc.setFillColor(255, 255, 255);
    this.doc.roundedRect(x - 2, y - 2, imgWmm + 4, imgHmm + 4, 2, 2, "FD");
    this.doc.addImage(dataUrl, "PNG", x, y, imgWmm, imgHmm, undefined, "SLOW");

    const captionY = y + imgHmm + 8;
    this.doc.setFont("helvetica", "italic");
    this.doc.setFontSize(9.5);
    this.doc.setTextColor(71, 85, 105);
    this.doc.text(`${figureId}: ${caption}`, pageW / 2, captionY, { align: "center", maxWidth: contentW });
    this.doc.setTextColor(0, 0, 0);

    if (useLandscape) {
      this.doc.addPage("a4", "portrait");
    }
    this.y = MARGIN.top;
  }

  diagramFallback(name: string, source: string): void {
    this.figureCounter += 1;
    this.newPage();
    this.h4(`Figure ${this.currentSection}-${this.figureCounter}: ${humanize(name)}`);
    this.writeJustified("Diagram could not be rendered. Source definition is provided below for reference.", 10, 5);
    const lines = this.lines(source.trim(), 8, CONTENT_W - 8);
    this.doc.setFillColor(248, 250, 252);
    const boxH = Math.min(lines.length * 4 + 8, 120);
    this.doc.roundedRect(MARGIN.left, this.y, CONTENT_W, boxH, 2, 2, "F");
    this.doc.setFont("courier", "normal");
    this.doc.setFontSize(8);
    let ly = this.y + 5;
    for (const line of lines.slice(0, 28)) {
      this.doc.text(line, MARGIN.left + 3, ly);
      ly += 4;
    }
    this.y += boxH + 6;
    this.doc.setFont("helvetica", "normal");
  }

  signatoryPage(): void {
    this.newPage();
    this.pageHeading("Document approval and sign-off", true);
    this.writeJustified(
      "By signing below, the parties confirm that this architecture document has been reviewed and is approved for use as the technical baseline for implementation.",
      10.5,
      5.2,
    );
    this.y += 6;

    const colW = CONTENT_W / 3;
    const roles = ["Prepared by", "Reviewed by", "Approved by"];
    const startY = this.y + 8;
    roles.forEach((role, i) => {
      const x = MARGIN.left + i * colW;
      this.doc.setFillColor(248, 250, 252);
      this.doc.roundedRect(x, startY, colW - 4, 48, 2, 2, "F");
      this.doc.setFont("helvetica", "bold");
      this.doc.setFontSize(10);
      this.doc.setTextColor(...HEADER_COLOR);
      this.doc.text(role, x + 4, startY + 8);
      this.doc.setFont("helvetica", "normal");
      this.doc.setFontSize(8.5);
      this.doc.setTextColor(100, 116, 139);
      let ly = startY + 18;
      for (const label of ["Name", "Signature", "Date"]) {
        this.doc.text(label, x + 4, ly);
        this.doc.setDrawColor(148, 163, 184);
        this.doc.line(x + 4, ly + 5, x + colW - 8, ly + 5);
        ly += 12;
      }
      this.doc.setTextColor(0, 0, 0);
    });
    this.y = startY + 58;
  }

  applyHeadersFooters(): void {
    const total = this.doc.getNumberOfPages();
    for (let p = 1; p <= total; p++) {
      this.doc.setPage(p);
      if (p === 1) continue;

      this.doc.setDrawColor(226, 232, 240);
      this.doc.setLineWidth(0.3);
      this.doc.line(MARGIN.left, 14, PAGE_W - MARGIN.right, 14);

      this.doc.setFont("helvetica", "normal");
      this.doc.setFontSize(8);
      this.doc.setTextColor(100, 116, 139);
      this.doc.text(this.meta.projectName, MARGIN.left, 10);
      this.doc.text("Architecture technical report", PAGE_W / 2, 10, { align: "center" });
      this.doc.text(`Page ${p} of ${total}`, PAGE_W - MARGIN.right, 10, { align: "right" });

      this.doc.line(MARGIN.left, PAGE_H - 12, PAGE_W - MARGIN.right, PAGE_H - 12);
      this.doc.text(`v${this.meta.version} · ${String(this.meta.status).toUpperCase()}`, MARGIN.left, PAGE_H - 7);
      this.doc.text(
        new Date().toLocaleDateString("en-GB"),
        PAGE_W - MARGIN.right,
        PAGE_H - 7,
        { align: "right" },
      );
      this.doc.setTextColor(0, 0, 0);
    }
  }

  save(filename: string): void {
    this.fillTableOfContents();
    this.applyHeadersFooters();
    this.doc.save(filename);
  }
}

function renderDiagrams(
  w: PdfWriter,
  docKey: ArchDocKey,
  doc: Record<string, unknown>,
  diagramImages: DiagramImageMap,
): void {
  const diagrams = (doc.diagrams as Record<string, string>) ?? {};
  const entries = Object.entries(diagrams).filter(([, src]) => src?.trim());
  if (entries.length === 0) return;

  w.beginFigures();
  for (const [name, source] of entries) {
    const mapKey = `${docKey}:${name}`;
    const img = diagramImages[mapKey];
    if (img) {
      w.figurePage(name, img.dataUrl, img.widthPx, img.heightPx, img.aspectRatio);
    } else {
      w.diagramFallback(name, source);
    }
  }
}

function renderSystemArch(w: PdfWriter, doc: Record<string, unknown>): void {
  w.overviewBlock(String(doc.overview ?? ""));
  w.labeledValue("Architecture pattern", String(doc.architecture_pattern ?? ""));
  w.subsection("Technology stack", "The following table lists technologies selected for each architectural layer, including version and rationale.");
  const stack = normalizeTechStack(doc.tech_stack);
  w.table(
    [["Layer", "Technology", "Version", "Rationale"]],
    stack.map((r) => [humanize(r.layer), r.name, r.version, r.reason]),
  );
  w.subsection("System components", "Deployable components and their responsibilities within the overall system.");
  const components = (doc.components as Array<Record<string, unknown>>) ?? [];
  w.table(
    [["Component", "Type", "Port", "Responsibility"]],
    components.map((c) => [
      String(c.name),
      String(c.type),
      c.port ? String(c.port) : "—",
      String(c.responsibility ?? ""),
    ]),
  );
  w.subsection("Data flow", "End-to-end sequence describing how data moves through the system.");
  w.numberedList((doc.data_flow as string[]) ?? []);
}

function renderDatabase(w: PdfWriter, doc: Record<string, unknown>): void {
  w.overviewBlock(String(doc.overview ?? ""));
  w.labeledValue("Database engine", String(doc.database ?? ""));
  w.subsection("Naming and schema conventions");
  w.keyValueTable((doc.conventions as Record<string, unknown>) ?? {});
  const tables = (doc.tables as Array<Record<string, unknown>>) ?? [];
  w.subsection("Entity tables", `${tables.length} table(s) derived from SRS entities.`);
  for (const tbl of tables) {
    w.h4(`Table: ${String(tbl.name)}`);
    w.labeledValue("Purpose", String(tbl.purpose ?? ""));
    w.labeledValue("Linked SRS entity", String(tbl.linked_srs_entity ?? ""));
    const cols = (tbl.columns as Array<Record<string, unknown>>) ?? [];
    w.table(
      [["Column", "Type", "Primary key", "Nullable", "Default"]],
      cols.map((col) => [
        String(col.name),
        String(col.type),
        col.pk ? "Yes" : "No",
        col.nullable ? "Yes" : "No",
        String(col.default ?? "—"),
      ]),
    );
  }
}

function renderApi(w: PdfWriter, doc: Record<string, unknown>): void {
  w.overviewBlock(String(doc.overview ?? ""));
  w.labeledValue("Base URL", String(doc.base_url ?? ""));
  w.labeledValue("Authentication", String(doc.auth ?? ""));
  const endpoints = (doc.endpoints as Array<Record<string, unknown>>) ?? [];
  const byModule = endpoints.reduce<Record<string, Array<Record<string, unknown>>>>((acc, ep) => {
    const mod = String(ep.module ?? "General");
    (acc[mod] ??= []).push(ep);
    return acc;
  }, {});
  w.subsection("API endpoints", `${endpoints.length} endpoint(s) organised by functional module.`);
  for (const [mod, eps] of Object.entries(byModule)) {
    w.h4(`Module: ${mod}`);
    w.table(
      [["Method", "Path", "Description", "Requirement"]],
      eps.map((ep) => [
        String(ep.method),
        String(ep.full_path ?? ep.path),
        String(ep.description ?? ""),
        String(ep.linked_fr ?? "—"),
      ]),
      { fontSize: 8.5, methodColumn: true },
    );
  }
}

function renderFrontend(w: PdfWriter, doc: Record<string, unknown>): void {
  w.overviewBlock(String(doc.overview ?? ""));
  w.labeledValue("Framework", String(doc.framework ?? ""));
  w.labeledValue("Styling approach", String(doc.styling ?? ""));
  w.subsection("Application pages", "Routes, purpose, and source file mapping.");
  const pages = (doc.pages as Array<Record<string, unknown>>) ?? [];
  w.table(
    [["Route", "Description", "Source file"]],
    pages.map((p) => [String(p.path), String(p.description ?? ""), String(p.file ?? "")]),
  );
  w.subsection("Folder structure", "Recommended project directory layout.");
  w.bulletList(flattenFolder(doc.folder_structure ?? {}));
}

function renderSecurity(w: PdfWriter, doc: Record<string, unknown>): void {
  w.overviewBlock(String(doc.overview ?? ""));
  const matrix = (doc.rbac as Record<string, unknown>)?.permission_matrix as
    | Array<Record<string, string>>
    | undefined;
  if (matrix && matrix.length > 0) {
    w.subsection("Role-based access control", "Permission matrix by resource and role.");
    w.table(
      [["Resource", "Studio owner", "Developer", "Client"]],
      matrix.map((row) => [row.resource, row.studio_owner, row.developer, row.client]),
    );
  }
  w.subsection("OWASP security checklist", "Mapped mitigations for common web application risks.");
  const owasp = (doc.owasp_checklist as Array<Record<string, string>>) ?? [];
  w.table(
    [["ID", "Risk", "Status", "Mitigation"]],
    owasp.map((item) => [item.id, item.name, item.status, item.how]),
    { fontSize: 8.5 },
  );
}

function renderUiux(w: PdfWriter, doc: Record<string, unknown>): void {
  w.overviewBlock(String(doc.overview ?? ""));
  const palette = (doc.design_system as Record<string, unknown>)?.color_palette as
    | Record<string, string>
    | undefined;
  if (palette) {
    w.subsection("Design system — color palette");
    w.table(
      [["Design token", "Value"]],
      Object.entries(palette).map(([name, value]) => [humanize(name), value]),
    );
  }
  w.subsection("UX rules", "Mandatory interaction and presentation guidelines.");
  w.bulletList((doc.ux_rules as string[]) ?? []);
}

const CONTENT_RENDERERS: Record<ArchDocKey, (w: PdfWriter, doc: Record<string, unknown>) => void> = {
  doc_system_arch: renderSystemArch,
  doc_database: renderDatabase,
  doc_api: renderApi,
  doc_frontend: renderFrontend,
  doc_security: renderSecurity,
  doc_uiux: renderUiux,
};

export function buildArchitecturePdf(options: {
  arch: ArchitecturePdfArch;
  projectName: string;
  mode: ArchitecturePdfMode;
  sectionKey?: ArchDocKey;
  sectionTitle?: string;
  filename: string;
  diagramImages?: DiagramImageMap;
}): void {
  const { arch, projectName, mode, sectionKey, sectionTitle, filename, diagramImages = {} } =
    options;

  const sections =
    mode === "section" && sectionKey
      ? DOC_TAB_META.filter((t) => t.key === sectionKey)
      : DOC_TAB_META;

  const docTitle =
    mode === "full"
      ? "Technical architecture document"
      : sectionTitle ?? "Architecture section";

  const w = new PdfWriter({
    projectName,
    docTitle,
    version: arch.version,
    status: arch.status,
    displayName: arch.display_name,
    mode,
  });

  w.coverPage();
  w.documentControlPage();

  sections.forEach((tab, index) => {
    const doc = arch[tab.key] as Record<string, unknown> | null | undefined;
    if (!doc) return;
    const sectionNum = index + 1;
    w.beginSection(sectionNum, tab.title);
    CONTENT_RENDERERS[tab.key](w, doc);
    renderDiagrams(w, tab.key, doc, diagramImages);
  });

  w.signatoryPage();
  w.save(filename);
}
