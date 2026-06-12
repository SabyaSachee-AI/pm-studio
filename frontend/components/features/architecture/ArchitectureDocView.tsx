"use client";

import { MermaidDiagram } from "@/components/ui/MermaidDiagram";

function Diagrams({
  diagrams,
  prefix,
}: {
  diagrams?: Record<string, string>;
  prefix: string;
}) {
  if (!diagrams || Object.keys(diagrams).length === 0) return null;
  return (
    <div className="space-y-4">
      {Object.entries(diagrams).map(([name, chart]) => (
        <div key={name} className="print:break-inside-avoid">
          <h4 className="mb-2 text-sm font-medium text-gray-300">
            {name.replace(/_/g, " ")}
          </h4>
          <MermaidDiagram chart={chart} id={`${prefix}-${name}`} />
        </div>
      ))}
    </div>
  );
}

function methodBadgeClass(method: string): string {
  const m = method.toUpperCase();
  if (m === "POST") return "bg-green-800 text-green-100";
  if (m === "GET") return "bg-blue-800 text-blue-100";
  if (m === "PATCH" || m === "PUT") return "bg-amber-800 text-amber-100";
  if (m === "DELETE") return "bg-red-800 text-red-100";
  return "bg-gray-700 text-gray-200";
}

export function ArchitectureDocView({
  docKey,
  doc,
}: {
  docKey: string;
  doc: Record<string, unknown> | null;
}) {
  if (!doc) {
    return <p className="text-gray-500">Document not generated yet.</p>;
  }

  const diagrams = doc.diagrams as Record<string, string> | undefined;

  if (docKey === "doc_system_arch") {
    const stack = (doc.tech_stack as Record<string, Record<string, string>>) ?? {};
    const components = (doc.components as Array<Record<string, unknown>>) ?? [];
    return (
      <div className="space-y-6 text-sm text-gray-300">
        <p>{String(doc.overview ?? "")}</p>
        {doc.architecture_pattern ? (
          <p>
            <strong>Pattern:</strong> {String(doc.architecture_pattern)}
          </p>
        ) : null}
        {Object.keys(stack).length > 0 ? (
          <section>
            <h3 className="font-medium text-white">Tech stack</h3>
            <table className="mt-2 w-full text-xs">
              <thead>
                <tr className="border-b border-gray-700 text-left text-gray-500">
                  <th className="py-1">Layer</th>
                  <th>Name</th>
                  <th>Version</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(stack).map(([layer, item]) => (
                  <tr key={layer} className="border-b border-gray-800">
                    <td className="py-2 capitalize">{layer.replace(/_/g, " ")}</td>
                    <td>{item?.name ?? ""}</td>
                    <td>{item?.version ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ) : null}
        {components.length > 0 ? (
          <section>
            <h3 className="font-medium text-white">Components</h3>
            <ul className="mt-2 space-y-2">
              {components.map((c, i) => (
                <li key={i} className="rounded border border-gray-800 p-3">
                  <strong>{String(c.name)}</strong> ({String(c.type)})
                  <p className="mt-1 text-gray-400">{String(c.responsibility ?? "")}</p>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        <Diagrams diagrams={diagrams} prefix="sys" />
      </div>
    );
  }

  if (docKey === "doc_database") {
    const tables = (doc.tables as Array<Record<string, unknown>>) ?? [];
    return (
      <div className="space-y-6 text-sm text-gray-300">
        <p>{String(doc.overview ?? "")}</p>
        {tables.map((tbl, i) => (
          <section key={i} className="rounded border border-gray-800 p-4">
            <h3 className="font-medium text-white">{String(tbl.name)}</h3>
            <p className="text-xs text-gray-500">{String(tbl.purpose ?? "")}</p>
          </section>
        ))}
        <Diagrams diagrams={diagrams} prefix="db" />
      </div>
    );
  }

  if (docKey === "doc_api") {
    const endpoints = (doc.endpoints as Array<Record<string, unknown>>) ?? [];
    return (
      <div className="space-y-6 text-sm text-gray-300">
        <p>{String(doc.overview ?? "")}</p>
        <div className="space-y-3">
          {endpoints.map((ep, i) => (
            <div key={i} className="rounded border border-gray-800 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded px-2 py-0.5 text-xs font-mono ${methodBadgeClass(String(ep.method))}`}
                >
                  {String(ep.method)}
                </span>
                <code className="text-xs">{String(ep.full_path ?? ep.path)}</code>
              </div>
              <p className="mt-2">{String(ep.description ?? "")}</p>
            </div>
          ))}
        </div>
        <Diagrams diagrams={diagrams} prefix="api" />
      </div>
    );
  }

  if (docKey === "doc_frontend") {
    const pages = (doc.pages as Array<Record<string, unknown>>) ?? [];
    return (
      <div className="space-y-6 text-sm text-gray-300">
        <p>{String(doc.overview ?? "")}</p>
        <ul className="space-y-2">
          {pages.map((p, i) => (
            <li key={i} className="rounded border border-gray-800 p-3">
              <code>{String(p.path)}</code> — {String(p.description ?? "")}
            </li>
          ))}
        </ul>
        <Diagrams diagrams={diagrams} prefix="fe" />
      </div>
    );
  }

  if (docKey === "doc_security") {
    const matrix = (doc.rbac as Record<string, unknown>)?.permission_matrix as
      | Array<Record<string, string>>
      | undefined;
    return (
      <div className="space-y-6 text-sm text-gray-300">
        <p>{String(doc.overview ?? "")}</p>
        {matrix && matrix.length > 0 ? (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-700 text-gray-500">
                <th className="py-1 text-left">Resource</th>
                <th>Owner</th>
                <th>Developer</th>
                <th>Client</th>
              </tr>
            </thead>
            <tbody>
              {matrix.map((row, i) => (
                <tr key={i} className="border-b border-gray-800">
                  <td className="py-1">{row.resource}</td>
                  <td>{row.studio_owner}</td>
                  <td>{row.developer}</td>
                  <td>{row.client}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        <Diagrams diagrams={diagrams} prefix="sec" />
      </div>
    );
  }

  return (
    <div className="space-y-6 text-sm text-gray-300">
      <p>{String(doc.overview ?? "")}</p>
      <Diagrams diagrams={diagrams} prefix="ux" />
    </div>
  );
}
