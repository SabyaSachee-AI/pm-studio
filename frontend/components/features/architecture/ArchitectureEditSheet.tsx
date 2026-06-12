"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { ArchModelSelector } from "@/components/ui/ArchModelSelector";
import { Button } from "@/components/ui/button";
import { api, type ModelChoice } from "@/lib/api";

type DocKey =
  | "doc_system_arch"
  | "doc_database"
  | "doc_api"
  | "doc_frontend"
  | "doc_security"
  | "doc_uiux";

interface ArchitectureEditSheetProps {
  open: boolean;
  docKey: DocKey;
  title: string;
  architectureId: string;
  initialContent: Record<string, unknown>;
  onClose: () => void;
  onSaved: (content: Record<string, unknown>) => void;
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-gray-300">{label}</span>
      {children}
    </label>
  );
}

function inputClass() {
  return "w-full rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-100";
}

function DiagramEditor({
  diagrams,
  onChange,
}: {
  diagrams: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
}) {
  const entries = Object.entries(diagrams);
  if (entries.length === 0) {
    return (
      <p className="text-xs text-gray-500">No diagrams in this document.</p>
    );
  }
  return (
    <div className="space-y-3">
      {entries.map(([name, chart]) => (
        <Field key={name} label={`Diagram: ${name.replace(/_/g, " ")}`}>
          <textarea
            className={`${inputClass()} min-h-[120px] font-mono text-xs`}
            value={chart}
            onChange={(e) =>
              onChange({ ...diagrams, [name]: e.target.value })
            }
          />
        </Field>
      ))}
    </div>
  );
}

function DocFields({
  docKey,
  draft,
  setDraft,
}: {
  docKey: DocKey;
  draft: Record<string, unknown>;
  setDraft: (next: Record<string, unknown>) => void;
}) {
  const diagrams = (draft.diagrams as Record<string, string>) ?? {};

  if (docKey === "doc_system_arch") {
    return (
      <div className="space-y-4">
        <Field label="Overview">
          <textarea
            className={`${inputClass()} min-h-[100px]`}
            value={String(draft.overview ?? "")}
            onChange={(e) => setDraft({ ...draft, overview: e.target.value })}
          />
        </Field>
        <Field label="Architecture pattern">
          <input
            className={inputClass()}
            value={String(draft.architecture_pattern ?? "")}
            onChange={(e) =>
              setDraft({ ...draft, architecture_pattern: e.target.value })
            }
          />
        </Field>
        <Field label="Tech stack (JSON)">
          <textarea
            className={`${inputClass()} min-h-[120px] font-mono text-xs`}
            value={JSON.stringify(draft.tech_stack ?? {}, null, 2)}
            onChange={(e) => {
              try {
                setDraft({ ...draft, tech_stack: JSON.parse(e.target.value) });
              } catch {
                /* keep typing */
              }
            }}
          />
        </Field>
        <Field label="Components (JSON array)">
          <textarea
            className={`${inputClass()} min-h-[120px] font-mono text-xs`}
            value={JSON.stringify(draft.components ?? [], null, 2)}
            onChange={(e) => {
              try {
                setDraft({ ...draft, components: JSON.parse(e.target.value) });
              } catch {
                /* keep typing */
              }
            }}
          />
        </Field>
        <Field label="Data flow (one item per line)">
          <textarea
            className={`${inputClass()} min-h-[80px]`}
            value={((draft.data_flow as string[]) ?? []).join("\n")}
            onChange={(e) =>
              setDraft({
                ...draft,
                data_flow: e.target.value.split("\n").filter(Boolean),
              })
            }
          />
        </Field>
        <DiagramEditor
          diagrams={diagrams}
          onChange={(next) => setDraft({ ...draft, diagrams: next })}
        />
      </div>
    );
  }

  if (docKey === "doc_database") {
    return (
      <div className="space-y-4">
        <Field label="Overview">
          <textarea
            className={`${inputClass()} min-h-[100px]`}
            value={String(draft.overview ?? "")}
            onChange={(e) => setDraft({ ...draft, overview: e.target.value })}
          />
        </Field>
        <Field label="Tables (JSON array)">
          <textarea
            className={`${inputClass()} min-h-[160px] font-mono text-xs`}
            value={JSON.stringify(draft.tables ?? [], null, 2)}
            onChange={(e) => {
              try {
                setDraft({ ...draft, tables: JSON.parse(e.target.value) });
              } catch {
                /* keep typing */
              }
            }}
          />
        </Field>
        <DiagramEditor
          diagrams={diagrams}
          onChange={(next) => setDraft({ ...draft, diagrams: next })}
        />
      </div>
    );
  }

  if (docKey === "doc_api") {
    return (
      <div className="space-y-4">
        <Field label="Overview">
          <textarea
            className={`${inputClass()} min-h-[100px]`}
            value={String(draft.overview ?? "")}
            onChange={(e) => setDraft({ ...draft, overview: e.target.value })}
          />
        </Field>
        <Field label="Base URL">
          <input
            className={inputClass()}
            value={String(draft.base_url ?? "")}
            onChange={(e) => setDraft({ ...draft, base_url: e.target.value })}
          />
        </Field>
        <Field label="Endpoints (JSON array)">
          <textarea
            className={`${inputClass()} min-h-[160px] font-mono text-xs`}
            value={JSON.stringify(draft.endpoints ?? [], null, 2)}
            onChange={(e) => {
              try {
                setDraft({ ...draft, endpoints: JSON.parse(e.target.value) });
              } catch {
                /* keep typing */
              }
            }}
          />
        </Field>
        <DiagramEditor
          diagrams={diagrams}
          onChange={(next) => setDraft({ ...draft, diagrams: next })}
        />
      </div>
    );
  }

  if (docKey === "doc_frontend") {
    return (
      <div className="space-y-4">
        <Field label="Overview">
          <textarea
            className={`${inputClass()} min-h-[100px]`}
            value={String(draft.overview ?? "")}
            onChange={(e) => setDraft({ ...draft, overview: e.target.value })}
          />
        </Field>
        <Field label="Framework">
          <input
            className={inputClass()}
            value={String(draft.framework ?? "")}
            onChange={(e) => setDraft({ ...draft, framework: e.target.value })}
          />
        </Field>
        <Field label="Pages (JSON array)">
          <textarea
            className={`${inputClass()} min-h-[120px] font-mono text-xs`}
            value={JSON.stringify(draft.pages ?? [], null, 2)}
            onChange={(e) => {
              try {
                setDraft({ ...draft, pages: JSON.parse(e.target.value) });
              } catch {
                /* keep typing */
              }
            }}
          />
        </Field>
        <DiagramEditor
          diagrams={diagrams}
          onChange={(next) => setDraft({ ...draft, diagrams: next })}
        />
      </div>
    );
  }

  if (docKey === "doc_security") {
    return (
      <div className="space-y-4">
        <Field label="Overview">
          <textarea
            className={`${inputClass()} min-h-[100px]`}
            value={String(draft.overview ?? "")}
            onChange={(e) => setDraft({ ...draft, overview: e.target.value })}
          />
        </Field>
        <Field label="RBAC (JSON)">
          <textarea
            className={`${inputClass()} min-h-[120px] font-mono text-xs`}
            value={JSON.stringify(draft.rbac ?? {}, null, 2)}
            onChange={(e) => {
              try {
                setDraft({ ...draft, rbac: JSON.parse(e.target.value) });
              } catch {
                /* keep typing */
              }
            }}
          />
        </Field>
        <Field label="OWASP checklist (JSON array)">
          <textarea
            className={`${inputClass()} min-h-[120px] font-mono text-xs`}
            value={JSON.stringify(draft.owasp_checklist ?? [], null, 2)}
            onChange={(e) => {
              try {
                setDraft({
                  ...draft,
                  owasp_checklist: JSON.parse(e.target.value),
                });
              } catch {
                /* keep typing */
              }
            }}
          />
        </Field>
        <DiagramEditor
          diagrams={diagrams}
          onChange={(next) => setDraft({ ...draft, diagrams: next })}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Field label="Overview">
        <textarea
          className={`${inputClass()} min-h-[100px]`}
          value={String(draft.overview ?? "")}
          onChange={(e) => setDraft({ ...draft, overview: e.target.value })}
        />
      </Field>
      <Field label="Design system (JSON)">
        <textarea
          className={`${inputClass()} min-h-[120px] font-mono text-xs`}
          value={JSON.stringify(draft.design_system ?? {}, null, 2)}
          onChange={(e) => {
            try {
              setDraft({
                ...draft,
                design_system: JSON.parse(e.target.value),
              });
            } catch {
              /* keep typing */
            }
          }}
        />
      </Field>
      <Field label="UX rules (one per line)">
        <textarea
          className={`${inputClass()} min-h-[80px]`}
          value={((draft.ux_rules as string[]) ?? []).join("\n")}
          onChange={(e) =>
            setDraft({
              ...draft,
              ux_rules: e.target.value.split("\n").filter(Boolean),
            })
          }
        />
      </Field>
      <DiagramEditor
        diagrams={diagrams}
        onChange={(next) => setDraft({ ...draft, diagrams: next })}
      />
    </div>
  );
}

export function ArchitectureEditSheet({
  open,
  docKey,
  title,
  architectureId,
  initialContent,
  onClose,
  onSaved,
}: ArchitectureEditSheetProps) {
  const [draft, setDraft] = useState<Record<string, unknown>>(initialContent);
  const [aiInstruction, setAiInstruction] = useState("");
  const [aiModel, setAiModel] = useState<ModelChoice | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setDraft(structuredClone(initialContent));
      setAiInstruction("");
      setError("");
    }
  }, [open, initialContent]);

  if (!open) return null;

  async function handleApplyAi() {
    if (!aiInstruction.trim()) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.aiEditArchitectureDoc(
        architectureId,
        docKey,
        draft,
        aiInstruction,
        aiModel,
      );
      setDraft(result.corrected_content);
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI edit failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleSave() {
    setBusy(true);
    setError("");
    try {
      await api.updateArchitectureDoc(architectureId, docKey, draft);
      onSaved(draft);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        aria-label="Close edit panel"
        className="fixed inset-0 z-40 bg-black/50"
        onClick={onClose}
      />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-gray-800 bg-gray-950 shadow-2xl">
        <header className="flex items-center justify-between border-b border-gray-800 px-4 py-3">
          <div>
            <p className="text-xs text-gray-500">Edit document</p>
            <h2 className="text-lg font-medium text-white">{title}</h2>
          </div>
          <button
            type="button"
            className="rounded-md p-2 text-gray-400 hover:bg-gray-900 hover:text-white"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-4">
          <DocFields docKey={docKey} draft={draft} setDraft={setDraft} />

          <div className="mt-6 border-t border-gray-800 pt-4">
            <Field label="Describe changes to AI">
              <textarea
                className={`${inputClass()} min-h-[90px]`}
                placeholder="e.g. Add Redis caching layer to tech stack and update deployment diagram"
                value={aiInstruction}
                onChange={(e) => setAiInstruction(e.target.value)}
              />
            </Field>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <ArchModelSelector
                value={aiModel}
                onChange={setAiModel}
                compact
              />
              <Button
                size="sm"
                disabled={busy || !aiInstruction.trim()}
                onClick={() => void handleApplyAi()}
              >
                Apply with AI
              </Button>
            </div>
          </div>

          {error ? (
            <p className="mt-3 text-sm text-red-400">{error}</p>
          ) : null}
        </div>

        <footer className="flex gap-2 border-t border-gray-800 px-4 py-3">
          <Button variant="outline" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={busy} onClick={() => void handleSave()}>
            Save changes
          </Button>
        </footer>
      </aside>
    </>
  );
}
