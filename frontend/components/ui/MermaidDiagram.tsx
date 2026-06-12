"use client";

import mermaid from "mermaid";
import { useEffect, useId, useRef } from "react";
import { initMermaidForUi } from "@/lib/mermaidRuntime";
import { sanitizeMermaid } from "@/lib/mermaidSanitize";

export function MermaidDiagram({ chart, id }: { chart: string; id: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const reactId = useId().replace(/:/g, "");
  const renderId = `mermaid-${id}-${reactId}`;

  useEffect(() => {
    if (!ref.current || !chart) return;
    let cancelled = false;
    const sanitized = sanitizeMermaid(chart);
    if (!sanitized) return;

    initMermaidForUi();
    mermaid
      .render(renderId, sanitized)
      .then(({ svg }) => {
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
          ref.current.classList.add("mermaid-container");
          ref.current.setAttribute("data-diagram-id", id);
        }
      })
      .catch(() => {
        if (!cancelled && ref.current) {
          ref.current.innerHTML = `<pre class="text-xs text-red-400 overflow-x-auto p-2">${sanitized}</pre>`;
        }
      });

    return () => {
      cancelled = true;
    };
  }, [chart, renderId]);

  return (
    <div
      ref={ref}
      className="overflow-x-auto rounded-lg border border-gray-800 bg-gray-950 p-4"
    />
  );
}
