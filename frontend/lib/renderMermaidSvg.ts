import mermaid from "mermaid";
import { sanitizeMermaid } from "@/lib/mermaidSanitize";

let mermaidReady = false;

function ensureMermaid(): void {
  if (mermaidReady) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: "neutral",
    securityLevel: "loose",
    flowchart: { curve: "basis", htmlLabels: true },
    sequence: { diagramMarginX: 12, diagramMarginY: 12 },
  });
  mermaidReady = true;
}

/** Render Mermaid source to an SVG string for PDF embedding. */
export async function renderMermaidSvg(chart: string, id: string): Promise<string> {
  const sanitized = sanitizeMermaid(chart);
  if (!sanitized) return "";
  ensureMermaid();
  try {
    await mermaid.parse(sanitized);
    const { svg } = await mermaid.render(`pdf-${id}`, sanitized);
    return svg;
  } catch {
    return "";
  }
}
