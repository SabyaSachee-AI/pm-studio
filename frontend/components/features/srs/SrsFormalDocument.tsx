type FrRecord = Record<string, unknown>;
type NfrRecord = Record<string, unknown>;

export type SrsFormalDocumentProps = {
  projectName?: string;
  clientName?: string;
  version: number;
  statusLabel: string;
  confirmedBy: string;
  confirmedDate: string;
  content: Record<string, unknown>;
  sourcePrdName?: string;
  frCount?: number;
  nfrCount?: number;
  qualityScore?: number | null;
  traceability?: Record<string, unknown> | null;
  clientApproved?: boolean;
  clientApprovedDate?: string;
  variant?: "print" | "portal";
  className?: string;
};

export function SrsFormalDocument({
  projectName,
  clientName,
  version,
  statusLabel,
  confirmedBy,
  confirmedDate,
  content,
  sourcePrdName,
  frCount,
  nfrCount,
  qualityScore,
  traceability,
  clientApproved,
  clientApprovedDate,
  variant = "print",
  className = "",
}: SrsFormalDocumentProps) {
  const intro = (content.introduction as Record<string, unknown> | string) ?? {};
  const introPurpose =
    typeof intro === "string" ? intro : String(intro.purpose ?? content.introduction ?? "");
  const introScope =
    typeof intro === "string" ? String(content.scope ?? "") : String(intro.scope ?? content.scope ?? "");
  const definitions =
    typeof intro === "object" && !Array.isArray(intro)
      ? ((intro.definitions as string[]) ?? (content.definitions as string[]) ?? [])
      : ((content.definitions as string[]) ?? []);

  const overall = (content.overall_description as Record<string, unknown>) ?? {};
  const frs = (content.functional_requirements as FrRecord[]) ?? [];
  const nfrs = (content.non_functional_requirements as NfrRecord[]) ??
    (content.nonfunctional_requirements as NfrRecord[]) ??
    [];
  const interfaces = (content.system_interfaces as Record<string, unknown>) ?? {};
  const dataReq = (content.data_requirements as Record<string, unknown>) ?? {};
  const entities = (dataReq.data_entities as Array<Record<string, unknown>>) ?? [];

  const nfrByCategory = nfrs.reduce<Record<string, NfrRecord[]>>((acc, nfr) => {
    const cat = String(nfr.category ?? "Other");
    acc[cat] = acc[cat] ?? [];
    acc[cat].push(nfr);
    return acc;
  }, {});

  const matrix = (traceability?.matrix as Record<string, string[]>) ?? {};
  const matrixEntries = Object.entries(matrix);
  const uncovered = (traceability?.uncovered_features as string[]) ?? [];

  const rootClass =
    variant === "print"
      ? `print-only prd-print-sheet mt-8 font-serif text-black ${className}`
      : `srs-formal-document rounded-xl border border-gray-700 bg-white p-8 font-serif text-black shadow-lg ${className}`;

  return (
    <div className={rootClass}>
      <div className="text-center">
        <h1 className="text-xl font-bold tracking-wide">
          SOFTWARE REQUIREMENTS SPECIFICATION
        </h1>
        <p className="mt-1 text-xs uppercase tracking-widest text-gray-600">
          {statusLabel} · IEEE 830 COMPLIANT
        </p>
      </div>

      <table className="mt-6 w-full border-collapse text-sm">
        <tbody>
          <tr>
            <td className="w-32 py-1 pr-3 align-top font-semibold">Project</td>
            <td className="py-1">{projectName ?? "—"}</td>
          </tr>
          <tr>
            <td className="py-1 pr-3 font-semibold">Client</td>
            <td className="py-1">{clientName ?? "—"}</td>
          </tr>
          <tr>
            <td className="py-1 pr-3 font-semibold">Version</td>
            <td className="py-1">v{version}</td>
          </tr>
          <tr>
            <td className="py-1 pr-3 font-semibold">Date</td>
            <td className="py-1">{confirmedDate}</td>
          </tr>
          <tr>
            <td className="py-1 pr-3 font-semibold">Prepared by</td>
            <td className="py-1">{confirmedBy}</td>
          </tr>
          <tr>
            <td className="py-1 pr-3 font-semibold">Status</td>
            <td className="py-1 font-semibold uppercase">{statusLabel}</td>
          </tr>
          {sourcePrdName ? (
            <tr>
              <td className="py-1 pr-3 font-semibold">Source PRD</td>
              <td className="py-1">{sourcePrdName}</td>
            </tr>
          ) : null}
          {frCount != null && frCount > 0 ? (
            <tr>
              <td className="py-1 pr-3 font-semibold">Scope</td>
              <td className="py-1">
                {frCount} FR{frCount === 1 ? "" : "s"}
                {nfrCount != null && nfrCount > 0
                  ? ` · ${nfrCount} NFR${nfrCount === 1 ? "" : "s"}`
                  : ""}
                {qualityScore != null ? ` · Quality ${qualityScore}/100` : ""}
              </td>
            </tr>
          ) : null}
          <tr>
            <td className="py-1 pr-3 font-semibold">Client approval</td>
            <td className="py-1">
              {clientApproved
                ? `Approved${clientApprovedDate ? ` on ${clientApprovedDate}` : ""}`
                : "Pending"}
            </td>
          </tr>
        </tbody>
      </table>

      <hr className="my-5 border-black/30" />

      <section className="print-section">
        <h2 className="text-sm font-bold">1. INTRODUCTION</h2>
        <p className="mt-2 text-xs">
          <span className="font-semibold">Purpose: </span>
          {introPurpose}
        </p>
        <p className="mt-2 text-xs">
          <span className="font-semibold">Scope: </span>
          {introScope}
        </p>
        {definitions.length > 0 ? (
          <ul className="mt-2 list-disc pl-5 text-xs">
            {definitions.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">2. OVERALL DESCRIPTION</h2>
        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed">
          {String(overall.product_perspective ?? "")}
        </p>
        {((overall.product_functions as string[]) ?? []).length > 0 ? (
          <>
            <p className="mt-2 text-xs font-semibold">Product functions</p>
            <ul className="mt-1 list-disc pl-5 text-xs">
              {((overall.product_functions as string[]) ?? []).map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </>
        ) : null}
        {((overall.user_characteristics as string[]) ?? []).length > 0 ? (
          <>
            <p className="mt-2 text-xs font-semibold">User characteristics</p>
            <ul className="mt-1 list-disc pl-5 text-xs">
              {((overall.user_characteristics as string[]) ?? []).map((u, i) => (
                <li key={i}>{u}</li>
              ))}
            </ul>
          </>
        ) : null}
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">3. FUNCTIONAL REQUIREMENTS</h2>
        {frs.map((fr, i) => (
          <div key={String(fr.id ?? fr.fr_number ?? i)} className="mt-3 text-xs">
            <p className="font-semibold">
              {String(fr.id ?? fr.fr_number ?? `FR-${i + 1}`)}: {String(fr.title ?? "")}{" "}
              [{String(fr.priority ?? "").toUpperCase()}]
            </p>
            <p className="mt-1 leading-relaxed">{String(fr.description ?? "")}</p>
            {fr.inputs ? <p className="mt-1">Input: {String(fr.inputs)}</p> : null}
            {fr.processing ? <p>Processing: {String(fr.processing)}</p> : null}
            {fr.outputs ? <p>Output: {String(fr.outputs)}</p> : null}
            {fr.error_handling ? <p>Error handling: {String(fr.error_handling)}</p> : null}
            {fr.linked_feature ? (
              <p>Linked PRD feature: {String(fr.linked_feature)}</p>
            ) : null}
            {((fr.test_criteria as string[]) ?? []).length > 0 ? (
              <>
                <p className="mt-1 font-medium">Test criteria:</p>
                <ul className="list-none pl-3">
                  {((fr.test_criteria as string[]) ?? []).map((c, j) => (
                    <li key={j}>✓ {c}</li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        ))}
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">4. NON-FUNCTIONAL REQUIREMENTS</h2>
        {Object.entries(nfrByCategory).map(([category, items]) => (
          <div key={category} className="mt-3 text-xs">
            <p className="font-semibold">[{category}]</p>
            {items.map((nfr, i) => (
              <div key={String(nfr.id ?? i)} className="mt-2">
                <p>{String(nfr.description ?? "")}</p>
                <p className="text-gray-700">
                  Metric: {String(nfr.metric ?? "—")} | Threshold:{" "}
                  {String(nfr.threshold ?? "—")}
                </p>
              </div>
            ))}
          </div>
        ))}
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">5. SYSTEM INTERFACES</h2>
        <ul className="mt-2 list-disc pl-5 text-xs">
          <li>
            User interfaces:{" "}
            {((interfaces.user_interfaces as string[]) ?? []).join(", ") || "—"}
          </li>
          <li>
            Hardware interfaces:{" "}
            {((interfaces.hardware_interfaces as string[]) ?? []).join(", ") || "—"}
          </li>
          <li>
            Software interfaces:{" "}
            {((interfaces.software_interfaces as string[]) ?? []).join(", ") || "—"}
          </li>
        </ul>
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">6. DATA REQUIREMENTS</h2>
        {entities.map((entity, i) => (
          <div key={i} className="mt-2 text-xs">
            <p className="font-semibold">Entity: {String(entity.name ?? "")}</p>
            <p>Fields: {((entity.fields as string[]) ?? []).join(", ")}</p>
            {entity.relationships ? <p>{String(entity.relationships)}</p> : null}
          </div>
        ))}
        <p className="mt-2 text-xs">Storage: {String(dataReq.data_storage ?? "—")}</p>
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">7. SECURITY REQUIREMENTS</h2>
        <ul className="mt-2 list-disc pl-5 text-xs">
          {((content.security_requirements as string[]) ?? []).map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">8. CONSTRAINTS</h2>
        <ul className="mt-2 list-disc pl-5 text-xs">
          {((content.constraints as string[]) ?? []).map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      </section>

      {matrixEntries.length > 0 ? (
        <section className="print-section mt-4">
          <h2 className="text-sm font-bold">9. TRACEABILITY MATRIX</h2>
          {traceability?.all_covered ? (
            <p className="mt-2 text-xs">All PRD features have linked FRs.</p>
          ) : (
            <p className="mt-2 text-xs">
              Uncovered features: {uncovered.join(", ") || "—"}
            </p>
          )}
          <table className="mt-3 w-full border-collapse text-xs">
            <thead>
              <tr>
                <th className="border border-black/30 px-2 py-1 text-left">PRD feature</th>
                <th className="border border-black/30 px-2 py-1 text-left">SRS FRs</th>
              </tr>
            </thead>
            <tbody>
              {matrixEntries.map(([feature, linkedFrs]) => (
                <tr key={feature}>
                  <td className="border border-black/30 px-2 py-1 font-mono">{feature}</td>
                  <td className="border border-black/30 px-2 py-1">
                    {linkedFrs.length > 0 ? linkedFrs.join(", ") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <hr className="my-5 border-black/30" />

      <footer className="text-xs">
        <p>
          Confirmed by: {confirmedBy} · Date: {confirmedDate} · Version v{version}
        </p>
        <p className="mt-2">Authorized signature: _________________________</p>
        <p className="mt-2">
          Client approval: {clientApproved ? "[x] Approved" : "[ ] Pending"}
          {clientApprovedDate ? ` — ${clientApprovedDate}` : ""}
        </p>
      </footer>
    </div>
  );
}
