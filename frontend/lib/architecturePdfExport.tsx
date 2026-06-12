import {
  DOC_TAB_META,
  type ArchDocKey,
} from "@/components/features/architecture/ArchitecturePrintDocument";
import { buildArchitecturePdf } from "@/lib/architecturePdfBuilder";
import { renderMermaidSvg } from "@/lib/renderMermaidSvg";
import { svgStringToPngDataUrl, type SvgPngImage } from "@/lib/svgToPdfImage";

export type ArchitecturePdfMode = "full" | "section";

export type DiagramImageMap = Record<string, SvgPngImage>;

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

const DOC_KEY_PREFIX: Record<ArchDocKey, string> = {
  doc_system_arch: "sys",
  doc_database: "db",
  doc_api: "api",
  doc_frontend: "fe",
  doc_security: "sec",
  doc_uiux: "ux",
};

function slugFilename(value: string): string {
  return value.replace(/[^\w.-]+/g, "-").replace(/-+/g, "-").slice(0, 80);
}

function isErrorSvg(svg: string): boolean {
  return (
    svg.includes('aria-roledescription="error"') ||
    svg.includes("Syntax error in text") ||
    svg.includes("Parse error on line") ||
    svg.includes('class="mermaid-error"')
  );
}

function scrapeDiagramSvg(diagramId: string): string {
  const svg = document.querySelector(`[data-diagram-id="${diagramId}"] svg`);
  if (!svg) return "";
  const html = svg.outerHTML;
  return isErrorSvg(html) ? "" : html;
}

async function collectDiagramImages(
  arch: ArchitecturePdfArch,
  keys: ArchDocKey[],
  onProgress?: (message: string) => void,
): Promise<DiagramImageMap> {
  const jobs: Array<{ mapKey: string; chart: string; diagramId: string }> = [];

  for (const key of keys) {
    const doc = arch[key] as Record<string, unknown> | null | undefined;
    const diagrams = doc?.diagrams as Record<string, string> | undefined;
    if (!diagrams) continue;
    const prefix = DOC_KEY_PREFIX[key];
    for (const [name, chart] of Object.entries(diagrams)) {
      if (!chart?.trim()) continue;
      jobs.push({
        mapKey: `${key}:${name}`,
        chart,
        diagramId: `${prefix}-${name}`,
      });
    }
  }

  if (jobs.length === 0) return {};

  const images: DiagramImageMap = {};
  let done = 0;

  await Promise.all(
    jobs.map(async ({ mapKey, chart, diagramId }) => {
      onProgress?.(`Rendering diagram ${done + 1}/${jobs.length}…`);

      let svg = await renderMermaidSvg(chart, mapKey);
      if (!svg) {
        svg = scrapeDiagramSvg(diagramId);
      }
      if (!svg) {
        done += 1;
        return;
      }

      const png = await svgStringToPngDataUrl(svg, 3);
      if (png) images[mapKey] = png;
      done += 1;
    }),
  );

  return images;
}

export async function exportArchitecturePdf(
  options: ExportArchitecturePdfOptions,
): Promise<void> {
  const { arch, projectName, mode, sectionKey, onProgress } = options;

  const keys: ArchDocKey[] =
    mode === "section" && sectionKey
      ? [sectionKey]
      : (DOC_TAB_META.map((t) => t.key) as ArchDocKey[]);

  onProgress?.("Rendering diagrams…");
  const diagramImages = await collectDiagramImages(arch, keys, onProgress);

  onProgress?.("Building PDF…");

  const sectionTitle = sectionKey
    ? DOC_TAB_META.find((t) => t.key === sectionKey)?.title
    : undefined;

  const baseName =
    mode === "full"
      ? `${slugFilename(projectName)}-architecture-v${arch.version}`
      : `${slugFilename(projectName)}-${slugFilename(sectionTitle ?? "section")}`;

  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

  buildArchitecturePdf({
    arch,
    projectName,
    mode,
    sectionKey,
    sectionTitle,
    filename: `${baseName}.pdf`,
    diagramImages,
  });
}
