"use client";

import type { ArchitecturePdfArch } from "@/lib/architecturePdfExport";

export const DOC_TAB_META = [
  { key: "doc_system_arch", title: "System architecture" },
  { key: "doc_database", title: "Database design" },
  { key: "doc_api", title: "API specification" },
  { key: "doc_frontend", title: "Frontend architecture" },
  { key: "doc_security", title: "Security and RBAC" },
  { key: "doc_uiux", title: "UI/UX design guidance" },
] as const;

export type ArchDocKey = (typeof DOC_TAB_META)[number]["key"];

const PDF_STYLES = `
  .arch-pdf-root { width: 210mm; box-sizing: border-box; font-family: "Segoe UI", Calibri, Arial, sans-serif; font-size: 11pt; color: #111; background: #fff; }
  .arch-pdf-cover { min-height: 250mm; display: flex; flex-direction: column; justify-content: center; padding: 40mm 20mm; }
  .arch-pdf-cover h1 { font-size: 28pt; margin: 0 0 12pt; }
  .arch-pdf-cover p { font-size: 12pt; color: #444; margin: 4pt 0; }
  .arch-pdf-section { padding: 15mm 20mm; page-break-before: always; }
  .arch-pdf-section:first-of-type { page-break-before: auto; }
  .arch-pdf-section h2 { font-size: 16pt; border-bottom: 1px solid #ccc; padding-bottom: 6pt; margin: 0 0 12pt; }
  .arch-pdf-section h3 { font-size: 12pt; margin: 14pt 0 6pt; }
  .arch-pdf-section p { line-height: 1.5; margin: 0 0 8pt; }
  .arch-pdf-diagram { margin: 12pt 0; text-align: center; }
  .arch-pdf-diagram svg { max-width: 100%; height: auto; }
  .arch-pdf-diagram-fallback { font-size: 9pt; background: #f5f5f5; padding: 8pt; white-space: pre-wrap; }
  .pdf-page-break-before { page-break-before: always; }
  .pdf-avoid-break { page-break-inside: avoid; }
`;

function DiagramBlock({
  name,
  mapKey,
  svgMap,
  doc,
}: {
  name: string;
  mapKey: string;
  svgMap: Record<string, string>;
  doc: Record<string, unknown>;
}) {
  const svg = svgMap[mapKey];
  const source = (doc.diagrams as Record<string, string> | undefined)?.[name] ?? "";
  return (
    <div className="arch-pdf-diagram pdf-avoid-break">
      <h3>{name.replace(/_/g, " ")}</h3>
      {svg ? (
        <div dangerouslySetInnerHTML={{ __html: svg }} />
      ) : source ? (
        <pre className="arch-pdf-diagram-fallback">{source}</pre>
      ) : null}
    </div>
  );
}

function DocSection({
  docKey,
  title,
  arch,
  svgMap,
  index,
}: {
  docKey: ArchDocKey;
  title: string;
  arch: ArchitecturePdfArch;
  svgMap: Record<string, string>;
  index: number;
}) {
  const doc = arch[docKey] as Record<string, unknown> | null | undefined;
  if (!doc) return null;
  const diagrams = (doc.diagrams as Record<string, string>) ?? {};
  return (
    <section className={`arch-pdf-section ${index > 0 ? "pdf-page-break-before" : ""}`}>
      <h2>
        {index + 1}. {title}
      </h2>
      <p>{String(doc.overview ?? "")}</p>
      {Object.keys(diagrams).map((name) => (
        <DiagramBlock
          key={name}
          name={name}
          mapKey={`${docKey}:${name}`}
          svgMap={svgMap}
          doc={doc}
        />
      ))}
    </section>
  );
}

export function ArchitecturePrintDocument({
  arch,
  projectName,
  mode,
  sectionKey,
  sectionTitle,
  svgMap,
}: {
  arch: ArchitecturePdfArch;
  projectName: string;
  mode: "full" | "section";
  sectionKey?: ArchDocKey;
  sectionTitle?: string;
  svgMap: Record<string, string>;
}) {
  const keys =
    mode === "section" && sectionKey
      ? DOC_TAB_META.filter((t) => t.key === sectionKey)
      : DOC_TAB_META;

  return (
    <div className="arch-pdf-root">
      <style>{PDF_STYLES}</style>
      {mode === "full" ? (
        <div className="arch-pdf-cover">
          <h1>Technical architecture document</h1>
          <p>Project: {projectName}</p>
          <p>Version: v{arch.version}</p>
          <p>Status: {arch.status}</p>
          <p>Date: {new Date().toLocaleDateString()}</p>
        </div>
      ) : (
        <div className="arch-pdf-cover" style={{ minHeight: "80mm" }}>
          <h1>{sectionTitle ?? "Architecture section"}</h1>
          <p>Project: {projectName}</p>
        </div>
      )}
      {keys.map((tab, i) => (
        <DocSection
          key={tab.key}
          docKey={tab.key}
          title={tab.title}
          arch={arch}
          svgMap={svgMap}
          index={i}
        />
      ))}
    </div>
  );
}
