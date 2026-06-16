import mermaid from "mermaid";

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

// UI rendering now uses a module-level singleton in MermaidDiagram.tsx
// This export kept for any legacy callers
export function initMermaidForUi(): void {
  configureMermaid("dark");
}
