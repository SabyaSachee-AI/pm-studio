import { createRoot } from "react-dom/client";
import {
  ArchitecturePrintDocument,
  type ArchDocKey,
  DOC_TAB_META,
} from "@/components/features/architecture/ArchitecturePrintDocument";
import { renderMermaidSvg } from "@/lib/renderMermaidSvg";

export type ArchitecturePdfMode = "full" | "section";

export interface ArchitecturePdfArch {
  version: number;
  status: string;
  display_name?: string | null;
  doc_system_arch?: Record<string, unknown> | null;
  doc_database?: Record<string, unknown> | null;
  doc_api?: Record<string, unknown> | null;
  doc_frontend?: Record<string, unknown> | null;
  doc_security?: Record<string, unknown> | null;
  doc_uiux?: Record<string, unknown> | null;
}

export interface ExportArchitecturePdfOptions {
  arch: ArchitecturePdfArch;
  projectName: string;
  mode: ArchitecturePdfMode;
  sectionKey?: ArchDocKey;
  onProgress?: (message: string) => void;
}

function slugFilename(value: string): string {
  return value.replace(/[^\w.-]+/g, "-").replace(/-+/g, "-").slice(0, 80);
}

async function collectDiagramSvgs(
  arch: ArchitecturePdfArch,
  keys: ArchDocKey[],
): Promise<Record<string, string>> {
  const svgMap: Record<string, string> = {};
  let idx = 0;
  for (const key of keys) {
    const doc = arch[key] as Record<string, unknown> | null | undefined;
    const diagrams = doc?.diagrams as Record<string, string> | undefined;
    if (!diagrams) continue;
    for (const [name, chart] of Object.entries(diagrams)) {
      if (!chart?.trim()) continue;
      const mapKey = `${key}:${name}`;
      svgMap[mapKey] = await renderMermaidSvg(chart, `arch-pdf-${idx++}`);
    }
  }
  return svgMap;
}

export async function exportArchitecturePdf(
  options: ExportArchitecturePdfOptions,
): Promise<void> {
  const { arch, projectName, mode, sectionKey, onProgress } = options;
  const keys: ArchDocKey[] =
    mode === "section" && sectionKey
      ? [sectionKey]
      : (DOC_TAB_META.map((t) => t.key) as ArchDocKey[]);

  onProgress?.("Preparing diagrams…");
  const svgMap = await collectDiagramSvgs(arch, keys);

  onProgress?.("Building document…");
  const host = document.createElement("div");
  host.style.position = "fixed";
  host.style.left = "-10000px";
  host.style.top = "0";
  host.style.width = "210mm";
  host.style.pointerEvents = "none";
  document.body.appendChild(host);

  const root = createRoot(host);
  const sectionTitle = sectionKey
    ? DOC_TAB_META.find((t) => t.key === sectionKey)?.title
    : undefined;

  root.render(
    <ArchitecturePrintDocument
      arch={arch}
      projectName={projectName}
      mode={mode}
      sectionKey={sectionKey}
      sectionTitle={sectionTitle}
      svgMap={svgMap}
    />,
  );

  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  await new Promise((r) => setTimeout(r, 400));

  onProgress?.("Generating PDF…");
  const html2pdf = (await import("html2pdf.js")).default;
  const element = host.firstElementChild as HTMLElement | null;
  if (!element) {
    root.unmount();
    document.body.removeChild(host);
    throw new Error("PDF document failed to render");
  }

  const baseName =
    mode === "full"
      ? `${slugFilename(projectName)}-architecture-v${arch.version}`
      : `${slugFilename(projectName)}-${slugFilename(sectionTitle ?? "section")}`;

  await html2pdf()
    .set({
      margin: [20, 15, 20, 15],
      filename: `${baseName}.pdf`,
      image: { type: "jpeg", quality: 0.96 },
      html2canvas: {
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: "#ffffff",
      },
      jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
      pagebreak: {
        mode: ["css", "legacy"],
        before: [".pdf-page-break-before"],
        avoid: [".pdf-avoid-break", "tr", "h2", "h3", ".pdf-table-wrap"],
      },
    })
    .from(element)
    .save();

  root.unmount();
  document.body.removeChild(host);
}
