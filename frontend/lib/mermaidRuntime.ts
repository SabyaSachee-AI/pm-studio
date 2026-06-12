import mermaid from "mermaid";

/** Shared Mermaid config for UI + PDF (labels rasterized via isolated iframe). */
export function configureMermaid(theme: "neutral" | "dark" = "neutral"): void {
  mermaid.initialize({
    startOnLoad: false,
    theme,
    securityLevel: "loose",
    fontFamily: "Segoe UI, Calibri, Arial, sans-serif",
    flowchart: { curve: "basis", htmlLabels: true, padding: 16 },
    sequence: { diagramMarginX: 16, diagramMarginY: 16, useMaxWidth: false },
    er: { diagramPadding: 20 },
  });
}

export function initMermaidForPdf(): void {
  configureMermaid("neutral");
}

export function initMermaidForUi(): void {
  configureMermaid("dark");
}
