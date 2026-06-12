"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { AiStatusBar, aiJobStatusBarProps } from "@/components/ui/AiStatusBar";
import { ScreenModelSelector } from "@/components/ui/ScreenModelSelector";
import {
  aiButtonClassName,
  aiButtonLabel,
  useAiJob,
} from "@/lib/hooks/useAiJob";
import {
  api,
  type AiModelOption,
  type KanbanBoard,
  type KanbanTask,
  type ModelChoice,
  type Project,
  type SRS,
  type TaskSpec,
  type UserResponse,
} from "@/lib/api";

const COLUMNS: { key: keyof KanbanBoard; label: string }[] = [
  { key: "backlog", label: "Backlog" },
  { key: "assigned", label: "Assigned" },
  { key: "in_progress", label: "In progress" },
  { key: "in_review", label: "In review" },
  { key: "done", label: "Done" },
];

const SYSTEM_TASK_MIN_ORDER = 99996;
const PROJECT_BIBLE_ORDER = 99996;
const CODE_AUDIT_ORDER = 99997;
const LOCAL_UI_TEST_ORDER = 99998;
const DEPLOY_ORDER = 99999;

interface SystemTaskStyle {
  badge: string;
  badgeClass: string;
  cardClass: string;
}

const SYSTEM_TASK_STYLES: Record<number, SystemTaskStyle> = {
  [PROJECT_BIBLE_ORDER]: {
    badge: "SETUP FIRST",
    badgeClass: "bg-amber-500/20 text-amber-300",
    cardClass: "border-amber-500/50 bg-amber-950/20",
  },
  [CODE_AUDIT_ORDER]: {
    badge: "FINAL — STEP 1",
    badgeClass: "bg-purple-500/20 text-purple-300",
    cardClass: "border-purple-500/50 bg-purple-950/20",
  },
  [LOCAL_UI_TEST_ORDER]: {
    badge: "FINAL — STEP 2",
    badgeClass: "bg-teal-500/20 text-teal-300",
    cardClass: "border-teal-500/50 bg-teal-950/20",
  },
  [DEPLOY_ORDER]: {
    badge: "DEPLOY",
    badgeClass: "bg-blue-500/20 text-blue-300",
    cardClass: "border-blue-500/50 bg-blue-950/20",
  },
};

interface SpecTable {
  name?: string;
  relevant_columns?: Array<{ name?: string; type?: string }>;
}

interface SpecEndpoint {
  method?: string;
  path?: string;
  request_body?: string;
  response_schema?: string;
  status_code?: string;
}

interface TaskDraft {
  title: string;
  description: string;
  priority: string;
  module_name: string;
}

function isSystemTask(task: KanbanTask): boolean {
  return task.order_index >= SYSTEM_TASK_MIN_ORDER;
}

function strField(content: Record<string, unknown>, key: string): string {
  const v = content[key];
  return typeof v === "string" ? v : "";
}

function strList(content: Record<string, unknown>, key: string): string[] {
  const v = content[key];
  if (!Array.isArray(v)) return [];
  return v.map((item) => String(item));
}

function specTables(content: Record<string, unknown>): SpecTable[] {
  const db = content.database;
  if (!db || typeof db !== "object") return [];
  const tables = (db as { tables?: unknown }).tables;
  if (!Array.isArray(tables)) return [];
  return tables.filter((t): t is SpecTable => typeof t === "object" && t !== null);
}

function specEndpoints(content: Record<string, unknown>): SpecEndpoint[] {
  const eps = content.api_endpoints;
  if (!Array.isArray(eps)) return [];
  return eps.filter((e): e is SpecEndpoint => typeof e === "object" && e !== null);
}

function SectionHeader({ title }: { title: string }) {
  return (
    <p className="border-b border-gray-800 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
      {title}
    </p>
  );
}

function SpecDetailPanel({
  content,
  summaryText,
  copiedKey,
  onCopySummary,
}: {
  content: Record<string, unknown>;
  summaryText: string;
  copiedKey: string | null;
  onCopySummary: () => void;
}) {
  const tables = specTables(content);
  const endpoints = specEndpoints(content);
  const filesCreate = strList(content, "files_to_create");
  const filesModify = strList(content, "files_to_modify");
  const criteria = strList(content, "acceptance_criteria");

  return (
    <div className="mt-4 space-y-5">
      <div>
        <SectionHeader title="What to build" />
        <p className="mt-2 text-sm text-gray-300">{strField(content, "task_scope")}</p>
        <p className="mt-1 text-xs text-gray-500">
          FR: {strField(content, "linked_fr") || "—"} | Feature:{" "}
          {strField(content, "linked_prd_feature") || "—"}
        </p>
      </div>

      {(filesCreate.length > 0 || filesModify.length > 0) && (
        <div>
          <SectionHeader title="Files" />
          {filesCreate.length > 0 && (
            <div className="mt-2">
              <p className="text-xs text-gray-500">Create:</p>
              <ul className="mt-1 list-inside list-disc text-sm text-gray-300">
                {filesCreate.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </div>
          )}
          {filesModify.length > 0 && (
            <div className="mt-2">
              <p className="text-xs text-gray-500">Modify:</p>
              <ul className="mt-1 list-inside list-disc text-sm text-gray-300">
                {filesModify.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {tables.length > 0 && (
        <div>
          <SectionHeader title="Database — exact table and column names" />
          <div className="mt-2 space-y-2">
            {tables.map((table) => (
              <div key={table.name} className="text-sm text-gray-300">
                <p className="font-medium">Table: {table.name}</p>
                <p className="text-xs text-gray-500">
                  Columns:{" "}
                  {(table.relevant_columns ?? [])
                    .map((c) => `${c.name ?? ""}: ${c.type ?? ""}`.trim())
                    .join(", ") || "—"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {endpoints.length > 0 && (
        <div>
          <SectionHeader title="API endpoints" />
          <div className="mt-2 space-y-2">
            {endpoints.map((ep, i) => (
              <div key={i} className="text-sm text-gray-300">
                <p className="font-medium">
                  {ep.method} {ep.path}
                </p>
                {ep.request_body && (
                  <p className="text-xs text-gray-500">Request: {ep.request_body}</p>
                )}
                {ep.response_schema && (
                  <p className="text-xs text-gray-500">
                    Response: {ep.response_schema} HTTP {ep.status_code ?? "200"}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {(strField(content, "frontend_route") || strField(content, "frontend_component")) && (
        <div>
          <SectionHeader title="Frontend" />
          <p className="mt-2 text-sm text-gray-300">
            Page route: {strField(content, "frontend_route") || "—"}
          </p>
          <p className="text-sm text-gray-300">
            Component: {strField(content, "frontend_component") || "—"}
          </p>
        </div>
      )}

      {criteria.length > 0 && (
        <div>
          <SectionHeader title="Acceptance criteria" />
          <ul className="mt-2 space-y-1 text-sm text-gray-300">
            {criteria.map((c, i) => (
              <li key={i}>☐ {c}</li>
            ))}
          </ul>
        </div>
      )}

      {strField(content, "technical_notes") && (
        <div>
          <SectionHeader title="Technical notes" />
          <p className="mt-2 whitespace-pre-wrap text-sm text-gray-300">
            {strField(content, "technical_notes")}
          </p>
        </div>
      )}

      <div className="rounded-lg border border-blue-800/60 bg-blue-950/20 p-3">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-semibold text-blue-300">Implementation summary</p>
          <Button size="sm" onClick={onCopySummary} disabled={!summaryText}>
            {copiedKey === "summary" ? "Copied!" : "📋 Copy summary"}
          </Button>
        </div>
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap text-xs leading-5 text-gray-300">
          {summaryText || "No summary generated yet."}
        </pre>
      </div>
    </div>
  );
}

export default function TasksPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [board, setBoard] = useState<KanbanBoard | null>(null);
  const [srsList, setSrsList] = useState<SRS[]>([]);
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [selectedTask, setSelectedTask] = useState<KanbanTask | null>(null);
  const [spec, setSpec] = useState<TaskSpec | null>(null);
  const [clearLoading, setClearLoading] = useState(false);
  const [specLoadingTaskId, setSpecLoadingTaskId] = useState<string | null>(null);
  const [dragTaskId, setDragTaskId] = useState<string | null>(null);
  const [bible, setBible] = useState<{ content: string; project_name: string } | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [models, setModels] = useState<AiModelOption[]>([]);
  const [specModel, setSpecModel] = useState<ModelChoice | null>(null);
  const [editingTask, setEditingTask] = useState(false);
  const [taskDraft, setTaskDraft] = useState<TaskDraft>({
    title: "",
    description: "",
    priority: "medium",
    module_name: "",
  });
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingSpecRef = useRef<{ specId: string } | null>(null);

  const extractJob = useAiJob({
    onComplete: () => {
      void loadBoard(projectId);
    },
  });

  const specJob = useAiJob({
    onComplete: async () => {
      const pending = pendingSpecRef.current;
      if (pending) {
        try {
          setSpec(await api.getSpec(pending.specId));
        } catch {
          setSpec(null);
        }
        pendingSpecRef.current = null;
      }
      setSpecLoadingTaskId(null);
      await loadBoard(projectId);
    },
    onFailed: () => {
      pendingSpecRef.current = null;
      setSpecLoadingTaskId(null);
    },
  });

  const extractBtn = aiButtonLabel(
    "Generate Tasks",
    extractJob.status,
    extractJob.operationName === "Extracting modules",
  );

  const loadBoard = useCallback(async (pid: string) => {
    if (!pid) return;
    setBoard(await api.getKanban(pid));
  }, []);

  useEffect(() => {
    api.listProjects().then((p) => {
      setProjects(p);
      const fromUrl =
        typeof window !== "undefined"
          ? new URLSearchParams(window.location.search).get("project")
          : null;
      const id = fromUrl || p[0]?.id || "";
      setProjectId(id);
    });
    api
      .listAiModels()
      .then((catalog) => setModels(catalog.models.filter((m) => m.available)))
      .catch(() => setModels([]));
  }, []);

  useEffect(() => {
    if (!projectId) return;
    setBible(null);
    setSelectedTask(null);
    setSpec(null);
    loadBoard(projectId);
    api.listSrs(projectId).then(setSrsList);
    api.listUsers().then(setUsers).catch(() => setUsers([]));
  }, [projectId, loadBoard]);

  useEffect(() => {
    return () => {
      if (copiedTimer.current) clearTimeout(copiedTimer.current);
    };
  }, []);

  function showCopied(key: string) {
    setCopiedKey(key);
    if (copiedTimer.current) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopiedKey(null), 2000);
  }

  async function copyText(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      showCopied(key);
    } catch {
      alert("Could not copy to clipboard.");
    }
  }

  async function fetchBible(force = false): Promise<string | null> {
    if (bible && !force) return bible.content;
    try {
      const data = await api.getProjectBible(projectId);
      setBible(data);
      return data.content;
    } catch (err) {
      alert(err instanceof Error ? err.message : "Could not build the project bible.");
      return null;
    }
  }

  async function fetchSystemGuide(task: KanbanTask): Promise<string | null> {
    try {
      const taskSpec = await api.getSpecByTask(task.id);
      const guide = taskSpec.content_json?.cursor_prompt;
      if (typeof guide === "string" && guide) return guide;
      alert("No guide content found for this task.");
      return null;
    } catch {
      alert("Could not load the guide for this task.");
      return null;
    }
  }

  async function handleCopyBible() {
    const content = await fetchBible();
    if (content) await copyText("bible", content);
  }

  async function handleRefreshBible() {
    await fetchBible(true);
    showCopied("bible-refreshed");
  }

  async function handleCopySystemGuide(task: KanbanTask, key: string) {
    const guide = await fetchSystemGuide(task);
    if (guide) await copyText(key, guide);
  }

  async function handleDownloadChecklist(task: KanbanTask) {
    const guide = await fetchSystemGuide(task);
    if (!guide) return;
    const blob = new Blob([guide], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "local-ui-test-checklist.txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleGenerateTasks() {
    const ELIGIBLE = ["approved", "finalized", "confirmed"];
    const approved = srsList.find(
      (s) =>
        ELIGIBLE.includes(s.status) ||
        ELIGIBLE.includes((s as SRS & { workflow_status?: string }).workflow_status ?? ""),
    );
    if (!approved) {
      alert("No eligible SRS found. The SRS must be approved or finalized before generating tasks.");
      return;
    }
    extractJob.startManual("Extracting modules");
    try {
      const { task_id } = await api.extractModules(projectId, approved.id);
      extractJob.startJob(task_id, "Extracting modules");
    } catch (err) {
      extractJob.failManual(
        err instanceof Error ? err.message : "Failed to start task generation",
      );
    }
  }

  async function handleClearAllTasks() {
    const projectName = projects.find((p) => p.id === projectId)?.name ?? "this project";
    const taskCount = COLUMNS.reduce((sum, { key }) => sum + (board?.[key]?.length ?? 0), 0);
    if (taskCount === 0) {
      alert("No tasks to delete.");
      return;
    }
    if (
      !confirm(
        `Delete all ${taskCount} tasks for "${projectName}"?\n\nThis removes feature tasks, system tasks, and their specs. You can Generate Tasks again afterward.`,
      )
    ) {
      return;
    }
    setClearLoading(true);
    try {
      const result = await api.clearProjectTasks(projectId);
      setSelectedTask(null);
      setSpec(null);
      setBible(null);
      await loadBoard(projectId);
      alert(`Deleted ${result.deleted_tasks} task(s) and ${result.deleted_specs} spec(s).`);
    } finally {
      setClearLoading(false);
    }
  }

  async function handleDrop(column: keyof KanbanBoard) {
    if (!dragTaskId) return;
    await api.updateTaskStatus(dragTaskId, column);
    setDragTaskId(null);
    await loadBoard(projectId);
  }

  async function openTask(task: KanbanTask) {
    setSelectedTask(task);
    setEditingTask(false);
    setTaskDraft({
      title: task.title,
      description: task.description ?? "",
      priority: task.priority,
      module_name: task.module_name ?? "",
    });
    try {
      setSpec(await api.getSpecByTask(task.id));
    } catch {
      setSpec(null);
    }
  }

  async function handleGenerateSpec(task: KanbanTask) {
    setSelectedTask(task);
    setSpecLoadingTaskId(task.id);
    specJob.startManual("Generating spec");
    try {
      const { spec_id, task_id_celery } = await api.generateSpec(task.id, specModel);
      pendingSpecRef.current = { specId: spec_id };
      specJob.startJob(task_id_celery, "Generating spec");
    } catch (err) {
      setSpecLoadingTaskId(null);
      specJob.failManual(
        err instanceof Error ? err.message : "Failed to start spec generation",
      );
    }
  }

  async function handleRegenerateSpec(task: KanbanTask) {
    setSelectedTask(task);
    setSpecLoadingTaskId(task.id);
    specJob.startManual("Generating spec");
    try {
      const { spec_id, task_id_celery } = await api.regenerateSpecByTask(task.id, specModel);
      pendingSpecRef.current = { specId: spec_id };
      specJob.startJob(task_id_celery, "Generating spec");
    } catch (err) {
      setSpecLoadingTaskId(null);
      specJob.failManual(
        err instanceof Error ? err.message : "Failed to regenerate spec",
      );
    }
  }

  async function handleSaveTaskEdit() {
    if (!selectedTask) return;
    const updated = await api.updateTask(selectedTask.id, {
      title: taskDraft.title,
      description: taskDraft.description || null,
      priority: taskDraft.priority,
      module_name: taskDraft.module_name || null,
    });
    setSelectedTask({ ...selectedTask, ...updated });
    setEditingTask(false);
    await loadBoard(projectId);
  }

  async function handleDeleteTask(task: KanbanTask) {
    if (!confirm("Delete this task? This cannot be undone.")) return;
    await api.deleteTask(task.id);
    if (selectedTask?.id === task.id) {
      setSelectedTask(null);
      setSpec(null);
    }
    await loadBoard(projectId);
  }

  async function handleAssignSpec(userId: string) {
    if (!spec) return;
    setSpec(await api.assignSpec(spec.id, userId));
  }

  function renderRegularTaskCard(task: KanbanTask) {
    const isSelected = selectedTask?.id === task.id;
    const isLoading =
      specLoadingTaskId === task.id &&
      (specJob.isRunning || specJob.status === "pending" || specJob.status === "failed");
    const hasReadySpec = task.spec_status === "ready";
    const showRegenerate =
      isSelected && (spec?.status === "ready" || task.spec_status === "ready");

    return (
      <div
        key={task.id}
        draggable={!isSelected}
        onDragStart={() => setDragTaskId(task.id)}
        onClick={() => openTask(task)}
        className={`cursor-pointer rounded-md border p-2 text-sm transition-colors ${
          isSelected
            ? "border-blue-500/60 bg-gray-900 ring-1 ring-blue-500/30"
            : "border-gray-700 bg-gray-950 hover:border-gray-500"
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <p className="font-medium leading-snug">{task.title}</p>
          {hasReadySpec && (
            <span className="shrink-0 rounded bg-green-500/15 px-1.5 py-0.5 text-[10px] text-green-400">
              Spec
            </span>
          )}
        </div>

        {isSelected ? (
          <div className="mt-2 space-y-2" onClick={(e) => e.stopPropagation()}>
            {task.description && (
              <p className="text-xs leading-relaxed text-gray-400">{task.description}</p>
            )}

            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-gray-500">
              {task.module_name && <span>Module: {task.module_name}</span>}
              <span>
                FR: {task.linked_fr ?? task.fr_references?.join(", ") ?? "—"}
              </span>
              <span>Priority: {task.priority}</span>
              {task.effort_hours != null && <span>Effort: {task.effort_hours}h</span>}
            </div>

            {editingTask && isSelected ? (
              <div className="space-y-2">
                <input
                  title="Task title"
                  className="w-full rounded-md border border-gray-700 bg-gray-950 px-2 py-1 text-xs"
                  value={taskDraft.title}
                  onChange={(e) => setTaskDraft({ ...taskDraft, title: e.target.value })}
                />
                <textarea
                  title="Task description"
                  className="h-16 w-full rounded-md border border-gray-700 bg-gray-950 px-2 py-1 text-xs"
                  value={taskDraft.description}
                  onChange={(e) => setTaskDraft({ ...taskDraft, description: e.target.value })}
                />
                <div className="flex flex-wrap gap-2">
                  <select
                    title="Priority"
                    className="rounded-md border border-gray-700 bg-gray-950 px-2 py-1 text-xs"
                    value={taskDraft.priority}
                    onChange={(e) => setTaskDraft({ ...taskDraft, priority: e.target.value })}
                  >
                    {["critical", "high", "medium", "low"].map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                  <input
                    title="Module name"
                    placeholder="Module name"
                    className="min-w-0 flex-1 rounded-md border border-gray-700 bg-gray-950 px-2 py-1 text-xs"
                    value={taskDraft.module_name}
                    onChange={(e) => setTaskDraft({ ...taskDraft, module_name: e.target.value })}
                  />
                </div>
                <div className="flex gap-1">
                  <Button size="sm" className="h-7 text-xs" onClick={handleSaveTaskEdit}>
                    Save
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    onClick={() => setEditingTask(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <select
                  title="AI model for spec generation"
                  className="w-full rounded-md border border-gray-700 bg-gray-950 px-2 py-1.5 text-xs"
                  value={specModel ? `${specModel.provider}::${specModel.model}` : ""}
                  onChange={(e) => {
                    const [provider, model] = e.target.value.split("::");
                    setSpecModel(provider && model ? { provider, model } : null);
                  }}
                >
                  <option value="">Auto model</option>
                  {models.map((m) => (
                    <option key={`${m.provider}::${m.model}`} value={`${m.provider}::${m.model}`}>
                      {m.label} ({m.cost})
                    </option>
                  ))}
                </select>

                <div className="flex flex-wrap gap-1">
                  {!showRegenerate ? (
                    <Button
                      size="sm"
                      className="h-7 flex-1 text-xs"
                      onClick={() => handleGenerateSpec(task)}
                      disabled={isLoading}
                    >
                      {isLoading ? "Generating..." : "Generate spec"}
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 flex-1 text-xs"
                      onClick={() => handleRegenerateSpec(task)}
                      disabled={isLoading}
                    >
                      {isLoading ? "Regenerating..." : "↺ Regenerate"}
                    </Button>
                  )}

                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    onClick={() => {
                      setEditingTask(true);
                      setTaskDraft({
                        title: task.title,
                        description: task.description ?? "",
                        priority: task.priority,
                        module_name: task.module_name ?? "",
                      });
                    }}
                  >
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs border-red-800/60 text-red-400 hover:bg-red-950/40"
                    onClick={() => handleDeleteTask(task)}
                  >
                    Delete
                  </Button>
                </div>

                {specLoadingTaskId === task.id && specJob.isVisible && (
                  <AiStatusBar
                    {...aiJobStatusBarProps(specJob)}
                    onCancel={() => {
                      specJob.cancel();
                      setSpecLoadingTaskId(null);
                    }}
                    onTryAgain={() => handleGenerateSpec(task)}
                  />
                )}
              </>
            )}
          </div>
        ) : (
          task.module_name && <p className="mt-1 text-xs text-gray-500">{task.module_name}</p>
        )}
      </div>
    );
  }

  function renderSystemCard(task: KanbanTask) {
    const style = SYSTEM_TASK_STYLES[task.order_index];
    if (!style) return null;
    const isBible = task.order_index === PROJECT_BIBLE_ORDER;
    const isAudit = task.order_index === CODE_AUDIT_ORDER;
    const isUiTest = task.order_index === LOCAL_UI_TEST_ORDER;
    const isDeploy = task.order_index === DEPLOY_ORDER;

    return (
      <div
        key={task.id}
        className={`rounded-md border p-2 text-sm ${style.cardClass}`}
      >
        <div className="flex items-start justify-between gap-2">
          <p className="font-medium">{task.title}</p>
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ${style.badgeClass}`}
          >
            {style.badge}
          </span>
        </div>
        {task.module_name && <p className="mt-1 text-xs text-gray-500">{task.module_name}</p>}

        {isBible && (
          <div className="mt-2 space-y-2">
            <p className="text-xs leading-5 text-gray-400">
              Copy this file into your project root before writing any code. The AI coding
              assistant will read it automatically.
            </p>
            <Button className="w-full" onClick={handleCopyBible}>
              {copiedKey === "bible" ? "Copied!" : "📋 Copy project bible"}
            </Button>
            <Button variant="outline" size="sm" className="w-full" onClick={handleRefreshBible}>
              {copiedKey === "bible-refreshed" ? "Refreshed" : "↺ Refresh"}
            </Button>
          </div>
        )}

        {isAudit && (
          <div className="mt-2">
            <Button className="w-full" onClick={() => handleCopySystemGuide(task, "audit")}>
              {copiedKey === "audit" ? "Copied!" : "📋 Copy audit guide"}
            </Button>
          </div>
        )}

        {isUiTest && (
          <div className="mt-2">
            <Button className="w-full" onClick={() => handleDownloadChecklist(task)}>
              📥 Download checklist
            </Button>
          </div>
        )}

        {isDeploy && (
          <div className="mt-2">
            <Button className="w-full" onClick={() => handleCopySystemGuide(task, "deploy")}>
              {copiedKey === "deploy" ? "Copied!" : "📋 Copy deploy guide"}
            </Button>
          </div>
        )}
      </div>
    );
  }

  const selectedIsSystem = selectedTask !== null && isSystemTask(selectedTask);
  const summaryText =
    typeof spec?.content_json?.cursor_prompt === "string"
      ? (spec.content_json.cursor_prompt as string)
      : "";
  const specContent = (spec?.content_json ?? {}) as Record<string, unknown>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">Kanban board</h1>
        <ScreenModelSelector screen="tasks" />
        <select
          title="Select project"
          className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <Button
          variant="outline"
          onClick={() => void handleGenerateTasks()}
          disabled={extractBtn.disabled || extractJob.isRunning}
          className={aiButtonClassName(extractBtn.variant)}
        >
          {extractBtn.label}
        </Button>
        <Button
          variant="outline"
          onClick={handleClearAllTasks}
          disabled={clearLoading || extractJob.isRunning}
          className="border-red-800/60 text-red-400 hover:bg-red-950/40 hover:text-red-300"
        >
          Delete all tasks
        </Button>
        <p className="text-xs text-gray-500">Uses SRS + PRD + architecture suite</p>
      </div>

      {extractJob.isVisible ? (
        <AiStatusBar
          {...aiJobStatusBarProps(extractJob)}
          onCancel={extractJob.cancel}
          onTryAgain={() => void handleGenerateTasks()}
        />
      ) : null}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-5">
        {COLUMNS.map(({ key, label }) => {
          const columnTasks = board?.[key] ?? [];
          const systemTasks = columnTasks
            .filter(isSystemTask)
            .sort((a, b) => a.order_index - b.order_index);
          const regularTasks = columnTasks.filter((t) => !isSystemTask(t));

          return (
            <div
              key={key}
              className="min-h-48 rounded-xl border border-gray-800 bg-gray-900/50 p-3"
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => handleDrop(key)}
            >
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-gray-500">
                {label} ({columnTasks.length})
              </p>
              <div className="space-y-2">
                {regularTasks.map((task) => renderRegularTaskCard(task))}
                {systemTasks.length > 0 && regularTasks.length > 0 && (
                  <div className="flex items-center gap-2 py-1">
                    <div className="h-px flex-1 bg-gray-700" />
                    <span className="text-[10px] text-gray-500">System tasks</span>
                    <div className="h-px flex-1 bg-gray-700" />
                  </div>
                )}
                {systemTasks.map((task) => renderSystemCard(task))}
              </div>
            </div>
          );
        })}
      </div>

      {selectedTask && !selectedIsSystem && spec?.status === "ready" && spec.content_json && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <h2 className="mb-1 text-lg font-medium">{selectedTask.title}</h2>
          <p className="mb-4 text-xs text-gray-500">Developer spec — read below or copy the summary</p>
          <SpecDetailPanel
            content={specContent}
            summaryText={summaryText}
            copiedKey={copiedKey}
            onCopySummary={() => copyText("summary", summaryText)}
          />
          <select
            title="Assign spec to developer"
            className="mt-4 rounded-md border border-gray-700 bg-gray-950 px-2 py-1 text-sm"
            value={spec.assigned_to_id ?? ""}
            onChange={(e) => e.target.value && handleAssignSpec(e.target.value)}
          >
            <option value="">Assign to developer...</option>
            {users
              .filter((u) => u.role === "code_creator" || u.role === "developer")
              .map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                </option>
              ))}
          </select>
        </div>
      )}
    </div>
  );
}
