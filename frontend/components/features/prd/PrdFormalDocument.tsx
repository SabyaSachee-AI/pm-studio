type FeatureRecord = Record<string, unknown>;
type StoryRecord = Record<string, unknown>;

function FormalSectionList({ title, items }: { title: string; items: unknown }) {
  const list = (items as string[]) ?? [];
  if (list.length === 0) return null;
  return (
    <div className="print-section mt-3">
      {title ? <h2 className="text-sm font-bold">{title}</h2> : null}
      <ul className="mt-1 list-disc pl-5 text-xs">
        {list.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export type PrdFormalDocumentProps = {
  projectName?: string;
  clientName?: string;
  version: number;
  statusLabel: string;
  confirmedBy: string;
  confirmedDate: string;
  content: Record<string, unknown>;
  sourceRequirementName?: string;
  featureCount?: number;
  storyCount?: number;
  qualityScore?: number | null;
  clientApproved?: boolean;
  clientApprovedDate?: string;
  /** print = hidden sheet; portal = visible review document */
  variant?: "print" | "portal";
  className?: string;
};

export function PrdFormalDocument({
  projectName,
  clientName,
  version,
  statusLabel,
  confirmedBy,
  confirmedDate,
  content,
  sourceRequirementName,
  featureCount,
  storyCount,
  qualityScore,
  clientApproved,
  clientApprovedDate,
  variant = "print",
  className = "",
}: PrdFormalDocumentProps) {
  const features = (content.features as FeatureRecord[]) ?? [];
  const stories = (content.user_stories as StoryRecord[]) ?? [];

  const rootClass =
    variant === "print"
      ? `print-only prd-print-sheet mt-8 font-serif text-black ${className}`
      : `prd-formal-document rounded-xl border border-gray-700 bg-white p-8 font-serif text-black shadow-lg ${className}`;

  return (
    <div className={rootClass}>
      <div className="text-center">
        <h1 className="text-xl font-bold tracking-wide">
          PRODUCT REQUIREMENTS DOCUMENT
        </h1>
        <p className="mt-1 text-xs uppercase tracking-widest text-gray-600">
          {statusLabel}
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
          {sourceRequirementName ? (
            <tr>
              <td className="py-1 pr-3 font-semibold">Source requirement</td>
              <td className="py-1">{sourceRequirementName}</td>
            </tr>
          ) : null}
          {featureCount != null && featureCount > 0 ? (
            <tr>
              <td className="py-1 pr-3 font-semibold">Scope</td>
              <td className="py-1">
                {featureCount} feature{featureCount === 1 ? "" : "s"}
                {storyCount != null && storyCount > 0
                  ? ` · ${storyCount} user stor${storyCount === 1 ? "y" : "ies"}`
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
        <h2 className="text-sm font-bold">1. EXECUTIVE SUMMARY</h2>
        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed">
          {String(content.executive_summary ?? "")}
        </p>
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">2. PROBLEM STATEMENT</h2>
        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed">
          {String(content.problem_statement ?? "")}
        </p>
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">3. TARGET USERS</h2>
        <ul className="mt-2 list-disc pl-5 text-xs">
          {((content.target_users as string[]) ?? []).map((user, i) => (
            <li key={i}>{user}</li>
          ))}
        </ul>
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">4. FEATURES</h2>
        {features.map((feature, i) => (
          <div key={String(feature.id ?? i)} className="mt-3 text-xs">
            <p className="font-semibold">
              {String(feature.id ?? `F-${i + 1}`)}: {String(feature.title ?? "")}{" "}
              [{String(feature.priority ?? "").toUpperCase()}]
              {feature.depends_on
                ? ` (Depends on: ${String(feature.depends_on)})`
                : ""}
            </p>
            <p className="mt-1 leading-relaxed">{String(feature.description ?? "")}</p>
            {((feature.acceptance_criteria as string[]) ?? []).length > 0 ? (
              <>
                <p className="mt-1 font-medium">Acceptance criteria:</p>
                <ul className="list-none pl-3">
                  {((feature.acceptance_criteria as string[]) ?? []).map((c, j) => (
                    <li key={j}>✓ {c}</li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        ))}
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">5. USER STORIES</h2>
        {stories.map((story, i) => (
          <p key={String(story.id ?? i)} className="mt-2 text-xs leading-relaxed">
            {String(story.id ?? `US-${i + 1}`)}: As a {String(story.as_a)}, I want to{" "}
            {String(story.i_want_to)} so that {String(story.so_that)}
          </p>
        ))}
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">
          6. NON-FUNCTIONAL REQUIREMENTS
        </h2>
        <FormalSectionList title="" items={content.non_functional_requirements} />
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">7. OUT OF SCOPE</h2>
        <FormalSectionList title="" items={content.out_of_scope} />
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">8. SUCCESS METRICS</h2>
        <FormalSectionList title="" items={content.success_metrics} />
      </section>

      <section className="print-section mt-4">
        <h2 className="text-sm font-bold">9. RISKS & ASSUMPTIONS</h2>
        <FormalSectionList title="Risks" items={content.risks} />
        <FormalSectionList title="Assumptions" items={content.assumptions} />
      </section>

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
