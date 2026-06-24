"use client";

import mermaid from "mermaid";
import { useEffect, useRef, useState } from "react";
import { sanitizeMermaid } from "@/lib/mermaidSanitize";

// Initialize once at module level — never call mermaid.initialize() inside effects
let mermaidReady = false;
function ensureMermaid() {
  if (mermaidReady) return;
  mermaidReady = true;
  mermaid.initialize({
    startOnLoad: false,
    theme: "dark",
    securityLevel: "loose",
    fontFamily: "Segoe UI, Calibri, Arial, sans-serif",
    flowchart: { curve: "basis", htmlLabels: true, padding: 16 },
    sequence: { diagramMarginX: 16, diagramMarginY: 16, useMaxWidth: false },
    er: { diagramPadding: 20 },
  });
}

/** Strip diagram to skeleton (node/edge structure only) for retry */
function stripToSkeleton(chart: string): string {
  const lines = chart.split("\n");
  const header = lines[0] ?? "";
  const body = lines.slice(1).filter((l) => {
    const t = l.trim();
    if (!t) return false;
    if (/^(subgraph|end|participant|actor|loop|alt|else|opt)\b/i.test(t)) return true;
    if (/-->|-->>|===|---|\|\||o\{|}o/.test(t)) return true;
    if (/^\w[\w_]*\[/.test(t) || /^\w[\w_]*\(/.test(t)) return true;
    return false;
  });
  return [header, ...body].join("\n");
}

/** Render chart to SVG string using a unique ID each call to avoid DOM collision */
async function renderChart(chart: string): Promise<string> {
  const uid = `md-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  try {
    const { svg } = await mermaid.render(uid, chart);
    return svg;
  } finally {
    // Clean up any orphaned element mermaid may have left in the DOM
    document.getElementById(uid)?.remove();
    document.getElementById(`d${uid}`)?.remove();
  }
}

export type MermaidDiagramProps = {
  chart: string;
  id: string;
  /** When true, show AI regenerate action on render failure */
  regeneratable?: boolean;
  regenerating?: boolean;
  onRegenerate?: () => void;
};

export function MermaidDiagram({
  chart,
  id,
  regeneratable = false,
  regenerating = false,
  onRegenerate,
}: MermaidDiagramProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const [showSource, setShowSource] = useState(false);
  const [sanitized, setSanitized] = useState("");
  const [retryKey, setRetryKey] = useState(0);
  const lastChartRef = useRef("");

  useEffect(() => {
    if (!ref.current || !chart) return;
    const clean = sanitizeMermaid(chart);
    if (!clean) return;
    if (clean === lastChartRef.current && !failed) return;

    setSanitized(clean);
    setFailed(false);
    ensureMermaid();

    let cancelled = false;

    async function tryRender() {
      try {
        const svg = await renderChart(clean);
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
          ref.current.setAttribute("data-diagram-id", id);
          lastChartRef.current = clean;
        }
        return;
      } catch {
        // fall through to skeleton retry
      }

      if (cancelled) return;

      const skeleton = stripToSkeleton(clean);
      if (skeleton && skeleton !== clean) {
        try {
          const svg = await renderChart(skeleton);
          if (!cancelled && ref.current) {
            ref.current.innerHTML = svg;
            ref.current.setAttribute("data-diagram-id", id);
            lastChartRef.current = clean;
          }
          return;
        } catch {
          // fall through to failure
        }
      }

      if (!cancelled) {
        setFailed(true);
      }
    }

    void tryRender();
    return () => {
      cancelled = true;
    };
  }, [chart, id, failed, retryKey]);

  if (failed) {
    return (
      <div className="rounded-lg border border-amber-900/40 bg-amber-950/10 p-3 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-amber-400">
            Diagram unavailable
            {regeneratable ? " — regenerate with AI to fix" : " — retry render or regenerate document"}
          </span>
          <div className="flex flex-wrap items-center gap-2">
            {regeneratable && onRegenerate ? (
              <button
                type="button"
                className="rounded border border-blue-800 bg-blue-950/40 px-2 py-1 text-blue-200 hover:bg-blue-900/50 disabled:opacity-50"
                disabled={regenerating}
                onClick={() => onRegenerate()}
              >
                {regenerating ? "Regenerating…" : "Regenerate diagram"}
              </button>
            ) : (
              <button
                type="button"
                className="rounded border border-gray-700 px-2 py-1 text-gray-300 hover:bg-gray-800"
                onClick={() => {
                  setFailed(false);
                  setRetryKey((k) => k + 1);
                }}
              >
                Retry render
              </button>
            )}
            <button
              type="button"
              className="text-gray-400 underline hover:text-gray-200"
              onClick={() => setShowSource((v) => !v)}
            >
              {showSource ? "Hide source" : "View source"}
            </button>
          </div>
        </div>
        {showSource ? (
          <pre className="mt-2 max-h-64 overflow-x-auto overflow-y-auto whitespace-pre-wrap rounded bg-gray-950 p-2 text-gray-400">
            {sanitized}
          </pre>
        ) : null}
      </div>
    );
  }

  return (
    <div
      ref={ref}
      id={`mermaid-view-${id}`}
      className="overflow-x-auto rounded-lg border border-gray-800 bg-gray-950 p-4"
    />
  );
}
