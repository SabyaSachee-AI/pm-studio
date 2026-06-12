import mermaid from "mermaid";
import { initMermaidForPdf } from "@/lib/mermaidRuntime";
import { sanitizeMermaid } from "@/lib/mermaidSanitize";
import { rasterizeSvgForPdf, type SvgPngImage } from "@/lib/svgToPdfImage";

let renderCounter = 0;

function safeRenderId(id: string): string {
  renderCounter += 1;
  const slug = id.replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 80);
  return `pdf-${slug}-${renderCounter}`;
}

function isErrorSvg(svg: string): boolean {
  return (
    svg.includes('aria-roledescription="error"') ||
    svg.includes("Syntax error in text") ||
    svg.includes("Parse error on line") ||
    svg.includes('class="mermaid-error"')
  );
}

/** Render Mermaid source to an SVG string for PDF embedding. */
export async function renderMermaidSvg(chart: string, id: string): Promise<string> {
  const sanitized = sanitizeMermaid(chart);
  if (!sanitized) return "";

  initMermaidForPdf();

  const renderId = safeRenderId(id);
  const host = document.createElement("div");
  host.style.cssText =
    "position:fixed;left:-10000px;top:0;width:1600px;opacity:0;pointer-events:none;background:#ffffff;color:#000000;";
  document.body.appendChild(host);

  try {
    const { svg, bindFunctions } = await mermaid.render(renderId, sanitized, host);
    bindFunctions?.(host);
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
    return svg && !isErrorSvg(svg) ? svg : "";
  } catch {
    return "";
  } finally {
    host.remove();
  }
}

/** Rasterize an on-screen diagram preview (SVG only). */
export async function rasterizeDiagramElement(
  element: HTMLElement,
  scale = 2,
): Promise<SvgPngImage | null> {
  const svg = element.querySelector("svg");
  if (!svg) return null;
  const markup = svg.outerHTML;
  if (isErrorSvg(markup)) return null;
  return rasterizeSvgForPdf(markup, scale);
}

/** Render Mermaid to a PNG for PDF embedding (isolated iframe — labels preserved). */
export async function renderMermaidPng(
  chart: string,
  id: string,
  scale = 2,
): Promise<SvgPngImage | null> {
  const svg = await renderMermaidSvg(chart, id);
  if (!svg) return null;
  return rasterizeSvgForPdf(svg, scale);
}

export { initMermaidForPdf };
