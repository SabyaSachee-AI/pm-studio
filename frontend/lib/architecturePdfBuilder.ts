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
import { buildDiagramsForDoc } from "@/lib/architectureDiagrams";
import { buildDiagramExplanation, buildDiagramStory } from "@/lib/diagramExplanations";

const MARGIN = { top: 20, right: 20, bottom: 20, left: 25 };
const PAGE_W = 210;
const PAGE_H = 297;
const CONTENT_W = PAGE_W - MARGIN.left - MARGIN.right;
const HEADER_COLOR: [number, number, number] = [30, 58, 95];
const ACCENT: [number, number, number] = [59, 130, 246];
const PX_TO_MM = 25.4 / 96;

/** Keep narrative text short and implementation-focused. */
function conciseText(text: string, maxLen = 420): string {
  const trimmed = text.replace(/\s+/g, " ").trim();
  if (trimmed.length <= maxLen) return trimmed;
  const cut = trimmed.slice(0, maxLen);
  const lastStop = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("; "));
  return (lastStop > 120 ? cut.slice(0, lastStop + 1) : cut).trim() + "…";
}

function trimList<T>(items: T[], max = 12): T[] {
  return items.length <= max ? items : items.slice(0, max);
}

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
    this.doc.text("PM STUDIO — ARCHITECTURE SUITE", PAGE_W / 2, 18, { align: "center" });
    this.doc.setFontSize(9);
    this.doc.setFont("helvetica", "normal");
    this.doc.text("Formal technical architecture report", PAGE_W / 2, 28, { align: "center" });

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
      ["Project", this.meta.projectName],
      ["Document", this.meta.docTitle],
      ["Version", `v${this.meta.version}`],
      ["Status", String(this.meta.status).toUpperCase()],
      ["Date", new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })],
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

    this.y = (this.doc.lastAutoTable?.finalY ?? this.y) + 12;
    this.doc.setTextColor(0, 0, 0);
    this.doc.setFont("helvetica", "normal");
  }

  /** Compact TOC only — skipped for single-section exports. */
  tableOfContentsPage(sectionTitles: string[]): void {
    if (this.meta.mode === "section") return;

    this.newPage();
    this.pageHeading("Contents", false);
    this.y += 2;

    sectionTitles.forEach((title, i) => {
      this.doc.setFont("helvetica", "normal");
      this.doc.setFontSize(10.5);
      this.doc.setTextColor(30, 41, 59);
      this.doc.text(`${i + 1}. ${title}`, MARGIN.left, this.y);
      this.y += 7;
    });

    this.tocPage = 0;
  }

  documentControlPage(): void {
    if (this.meta.mode === "section") return;
    /* Full report uses cover + inline contents — no extra control pages. */
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
    const body = conciseText(text, 380);
    if (!body) return;
    this.ensureSpace(20);
    this.doc.setFillColor(248, 250, 252);
    this.doc.setDrawColor(226, 232, 240);
    const lines = this.lines(body, 10.5);
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

  beginFigures(): void {
    if (this.figureCounter > 0) return;
    this.h4("Diagrams");
  }

  /** Every architecture diagram renders on its own landscape A4 page. */
  private figurePage(
    name: string,
    dataUrl: string,
    widthPx: number,
    heightPx: number,
    explanation: string,
  ): void {
    this.figureCounter += 1;
    const figureId = `Fig ${this.currentSection}-${this.figureCounter}`;
    const caption = humanize(name);

    this.doc.addPage("a4", "landscape");

    const pageW = PAGE_H;
    const pageH = PAGE_W;
    const contentW = pageW - MARGIN.left - MARGIN.right;
    let contentTop = MARGIN.top + 10;

    this.doc.setFont("helvetica", "bold");
    this.doc.setFontSize(11);
    this.doc.setTextColor(...HEADER_COLOR);
    this.doc.text(`${figureId}: ${caption}`, MARGIN.left, contentTop);
    contentTop += 7;

    if (explanation.trim()) {
      this.doc.setFont("helvetica", "normal");
      this.doc.setFontSize(8.5);
      this.doc.setTextColor(51, 65, 85);
      const explLines = this.lines(explanation.trim(), 8.5, contentW);
      const explLineH = 3.8;
      const maxExplLines = 10;
      const shown = explLines.slice(0, maxExplLines);
      this.doc.text(shown, MARGIN.left, contentTop);
      contentTop += shown.length * explLineH + 4;
      if (explLines.length > maxExplLines) {
        this.doc.setFont("helvetica", "italic");
        this.doc.setFontSize(8);
        this.doc.setTextColor(100, 116, 139);
        this.doc.text(
          `…and ${explLines.length - maxExplLines} more line(s); see PM Studio for the full walkthrough.`,
          MARGIN.left,
          contentTop,
        );
        contentTop += 5;
      }
    }

    const footerReserve = 10;
    const contentH = pageH - contentTop - MARGIN.bottom - footerReserve;

    let imgWmm = widthPx * PX_TO_MM;
    let imgHmm = heightPx * PX_TO_MM;
    const scale = Math.min(contentW / imgWmm, contentH / imgHmm, 1);
    imgWmm *= scale;
    imgHmm *= scale;

    const x = MARGIN.left + (contentW - imgWmm) / 2;
    const y = contentTop + Math.max(0, (contentH - imgHmm) / 2);

    this.doc.setDrawColor(203, 213, 225);
    this.doc.setLineWidth(0.4);
    this.doc.setFillColor(255, 255, 255);
    this.doc.roundedRect(x - 2, y - 2, imgWmm + 4, imgHmm + 4, 2, 2, "FD");
    this.doc.addImage(dataUrl, "PNG", x, y, imgWmm, imgHmm, undefined, "SLOW");

    this.doc.setFont("helvetica", "italic");
    this.doc.setFontSize(9);
    this.doc.setTextColor(100, 116, 139);
    this.doc.text(
      `${figureId}: ${caption}`,
      pageW / 2,
      pageH - MARGIN.bottom + 4,
      { align: "center", maxWidth: contentW },
    );
    this.doc.setTextColor(0, 0, 0);

    this.doc.addPage("a4", "portrait");
    this.y = MARGIN.top;
  }

  /** Portrait narrative page placed immediately after each diagram figure. */
  private writeFigureStoryPage(name: string, story: string): void {
    const figureId = `Fig ${this.currentSection}-${this.figureCounter}`;
    const caption = humanize(name);

    this.pageHeading(`${figureId} — narrative`, false);
    this.doc.setFont("helvetica", "italic");
    this.doc.setFontSize(10);
    this.doc.setTextColor(71, 85, 105);
    this.doc.text(
      `How ${caption.toLowerCase()} is used, why it matters, and which dependencies it relies on`,
      MARGIN.left,
      this.y,
    );
    this.y += 8;
    this.doc.setTextColor(0, 0, 0);

    this.writeJustified(story, 10.5, 5.4);
  }

  figureWithStory(
    name: string,
    dataUrl: string,
    widthPx: number,
    heightPx: number,
    explanation: string,
    story: string,
  ): void {
    this.figurePage(name, dataUrl, widthPx, heightPx, explanation);
    if (story.trim()) {
      this.writeFigureStoryPage(name, story);
    }
  }

  diagramFallbackWithStory(name: string, explanation = "", story = ""): void {
    this.diagramFallback(name, explanation);
    if (story.trim()) {
      this.writeFigureStoryPage(name, story);
    }
  }

  private diagramFallback(name: string, explanation = ""): void {
    this.figureCounter += 1;
    this.doc.addPage("a4", "landscape");
    const pageW = PAGE_H;

    this.doc.setFont("helvetica", "bold");
    this.doc.setFontSize(12);
    this.doc.setTextColor(...HEADER_COLOR);
    this.doc.text(
      `Fig ${this.currentSection}-${this.figureCounter}: ${humanize(name)}`,
      MARGIN.left,
      MARGIN.top,
    );
    this.doc.setFont("helvetica", "normal");
    this.doc.setFontSize(9);
    this.doc.setTextColor(51, 65, 85);
    if (explanation.trim()) {
      const lines = this.lines(explanation.trim(), 9, pageW - MARGIN.left - MARGIN.right);
      this.doc.text(lines.slice(0, 12), MARGIN.left, MARGIN.top + 10);
    }
    this.doc.setFontSize(10);
    this.doc.setTextColor(100, 116, 139);
    this.doc.text(
      "Diagram image could not be embedded. View this section in PM Studio for the interactive diagram.",
      MARGIN.left,
      MARGIN.top + 52,
      { maxWidth: pageW - MARGIN.left - MARGIN.right },
    );
    this.doc.setTextColor(0, 0, 0);
    this.doc.addPage("a4", "portrait");
    this.y = MARGIN.top;
  }

  signatoryPage(): void {
    this.newPage();
    this.pageHeading("Approval sign-off", true);
    this.writeJustified(
      "Signatures confirm review and approval of this architecture document for implementation.",
      10.5,
      5.2,
    );
    this.y += 8;

    const headers = ["Role", "Name", "Signature", "Date"];
    const rows = [
      ["Prepared by", "", "", ""],
      ["Reviewed by", "", "", ""],
      ["Approved by", "", "", ""],
    ];
    autoTable(this.doc, {
      startY: this.y,
      margin: { left: MARGIN.left, right: MARGIN.right },
      head: [headers],
      body: rows,
      styles: { fontSize: 10, cellPadding: 8, minCellHeight: 14 },
      headStyles: { fillColor: HEADER_COLOR, textColor: 255, fontStyle: "bold" },
      columnStyles: {
        0: { cellWidth: 38, fontStyle: "bold" },
        1: { cellWidth: 42 },
        2: { cellWidth: 48 },
        3: { cellWidth: 32 },
      },
      theme: "grid",
    });
    this.y = (this.doc.lastAutoTable?.finalY ?? this.y) + 8;
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
  // Same programmatic builders as screen + image collection — keeps names aligned
  const diagrams = buildDiagramsForDoc(docKey, doc);
  const entries = Object.entries(diagrams).filter(([, src]) => src?.trim());
  if (entries.length === 0) return;

  w.beginFigures();
  for (const [name, source] of entries) {
    const mapKey = `${docKey}:${name}`;
    const img = diagramImages[mapKey];
    const explanation = buildDiagramExplanation(name, source, doc);
    const story = buildDiagramStory(name, source, doc);
    if (img) {
      w.figureWithStory(name, img.dataUrl, img.widthPx, img.heightPx, explanation, story);
    } else {
      w.diagramFallbackWithStory(name, explanation, story);
    }
  }
}

function renderSystemArch(w: PdfWriter, doc: Record<string, unknown>): void {
  w.overviewBlock(String(doc.overview ?? ""));
  w.labeledValue("Pattern", String(doc.architecture_pattern ?? ""));
  const stack = normalizeTechStack(doc.tech_stack);
  if (stack.length > 0) {
    w.h4("Technology stack");
    w.table(
      [["Layer", "Technology", "Version"]],
      stack.map((r) => [humanize(r.layer), r.name, r.version || "—"]),
      { fontSize: 9 },
    );
  }
  const components = trimList((doc.components as Array<Record<string, unknown>>) ?? [], 10);
  if (components.length > 0) {
    w.h4("Components");
    w.table(
      [["Component", "Type", "Responsibility"]],
      components.map((c) => [
        String(c.name),
        String(c.type ?? "—"),
        conciseText(String(c.responsibility ?? ""), 120),
      ]),
      { fontSize: 9 },
    );
  }
  const flow = trimList((doc.data_flow as string[]) ?? [], 8);
  if (flow.length > 0) {
    w.h4("Data flow");
    w.numberedList(flow.map((s) => conciseText(s, 140)));
  }
}

function renderDatabase(w: PdfWriter, doc: Record<string, unknown>): void {
  w.overviewBlock(String(doc.overview ?? ""));
  w.labeledValue("Engine", String(doc.database ?? ""));
  const conventions = (doc.conventions as Record<string, unknown>) ?? {};
  const convRows = Object.entries(conventions)
    .filter(([, v]) => v)
    .slice(0, 8)
    .map(([k, v]) => [humanize(k), String(v)]);
  if (convRows.length > 0) {
    w.h4("Conventions");
    w.table([["Rule", "Value"]], convRows, { fontSize: 9 });
  }
  const tables = trimList((doc.tables as Array<Record<string, unknown>>) ?? [], 8);
  for (const tbl of tables) {
    w.h4(String(tbl.name));
    const purpose = String(tbl.purpose ?? "");
    if (purpose) w.labeledValue("Purpose", conciseText(purpose, 100));
    const cols = trimList((tbl.columns as Array<Record<string, unknown>>) ?? [], 14);
    if (cols.length > 0) {
      w.table(
        [["Column", "Type", "PK", "Null"]],
        cols.map((col) => [
          String(col.name),
          String(col.type),
          col.pk ? "Y" : "",
          col.nullable === false ? "N" : "Y",
        ]),
        { fontSize: 8.5 },
      );
    }
  }
}

function renderApi(w: PdfWriter, doc: Record<string, unknown>): void {
  w.overviewBlock(String(doc.overview ?? ""));
  w.labeledValue("Base URL", String(doc.base_url ?? ""));
  w.labeledValue("Auth", conciseText(String(doc.auth ?? ""), 160));
  const endpoints = trimList((doc.endpoints as Array<Record<string, unknown>>) ?? [], 24);
  if (endpoints.length > 0) {
    w.h4("Endpoints");
    w.table(
      [["Method", "Path", "Description", "FR"]],
      endpoints.map((ep) => [
        String(ep.method),
        String(ep.full_path ?? ep.path),
        conciseText(String(ep.description ?? ""), 90),
        String(ep.linked_fr ?? "—"),
      ]),
      { fontSize: 8, methodColumn: true },
    );
  }
}

function renderFrontend(w: PdfWriter, doc: Record<string, unknown>): void {
  w.overviewBlock(String(doc.overview ?? ""));
  w.labeledValue("Framework", String(doc.framework ?? ""));
  w.labeledValue("Styling", String(doc.styling ?? ""));
  const pages = trimList((doc.pages as Array<Record<string, unknown>>) ?? [], 16);
  if (pages.length > 0) {
    w.h4("Pages");
    w.table(
      [["Route", "Purpose", "File"]],
      pages.map((p) => [
        String(p.path),
        conciseText(String(p.description ?? ""), 80),
        String(p.file ?? ""),
      ]),
      { fontSize: 8.5 },
    );
  }
}

function renderSecurity(w: PdfWriter, doc: Record<string, unknown>): void {
  w.overviewBlock(String(doc.overview ?? ""));
  const matrix = (doc.rbac as Record<string, unknown>)?.permission_matrix as
    | Array<Record<string, string>>
    | undefined;
  if (matrix && matrix.length > 0) {
    w.h4("RBAC matrix");
    w.table(
      [["Resource", "Owner", "Developer", "Client"]],
      trimList(matrix, 12).map((row) => [
        row.resource,
        row.studio_owner,
        row.developer,
        row.client,
      ]),
      { fontSize: 8.5 },
    );
  }
  const owasp = trimList((doc.owasp_checklist as Array<Record<string, string>>) ?? [], 10);
  if (owasp.length > 0) {
    w.h4("OWASP checklist");
    w.table(
      [["ID", "Risk", "Mitigation"]],
      owasp.map((item) => [item.id, item.name, conciseText(item.how ?? "", 100)]),
      { fontSize: 8 },
    );
  }
}

function renderUiux(w: PdfWriter, doc: Record<string, unknown>): void {
  w.overviewBlock(String(doc.overview ?? ""));
  const palette = (doc.design_system as Record<string, unknown>)?.color_palette as
    | Record<string, string>
    | undefined;
  if (palette && Object.keys(palette).length > 0) {
    w.h4("Color palette");
    w.table(
      [["Token", "Value"]],
      Object.entries(palette)
        .slice(0, 10)
        .map(([name, value]) => [humanize(name), value]),
      { fontSize: 9 },
    );
  }
  const rules = trimList((doc.ux_rules as string[]) ?? [], 10);
  if (rules.length > 0) {
    w.h4("UX rules");
    w.bulletList(rules.map((r) => conciseText(r, 120)));
  }
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
      ? "Full architecture report"
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

  const includedSections = sections
    .map((tab) => ({
      tab,
      doc: arch[tab.key] as Record<string, unknown> | null | undefined,
    }))
    .filter((s) => s.doc);

  if (mode === "full") {
    w.tableOfContentsPage(includedSections.map((s) => s.tab.title));
  }

  includedSections.forEach(({ tab, doc }, index) => {
    if (!doc) return;
    const sectionNum = index + 1;
    w.beginSection(sectionNum, tab.title);
    CONTENT_RENDERERS[tab.key](w, doc);
    renderDiagrams(w, tab.key, doc, diagramImages);
  });

  w.signatoryPage();
  w.save(filename);
}
