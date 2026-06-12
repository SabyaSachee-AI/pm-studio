"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  api,
  type KanbanBoard,
  type KanbanTask,
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

export default function TasksPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [board, setBoard] = useState<KanbanBoard | null>(null);
  const [srsList, setSrsList] = useState<SRS[]>([]);
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [selectedTask, setSelectedTask] = useState<KanbanTask | null>(null);
  const [spec, setSpec] = useState<TaskSpec | null>(null);
  const [loading, setLoading] = useState(false);
  const [dragTaskId, setDragTaskId] = useState<string | null>(null);

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
  }, []);

  useEffect(() => {
    if (!projectId) return;
    loadBoard(projectId);
    api.listSrs(projectId).then(setSrsList);
    api.listUsers().then(setUsers).catch(() => setUsers([]));
  }, [projectId, loadBoard]);

  async function handleExtractModules() {
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
    setLoading(true);
    const { task_id } = await api.extractModules(projectId, approved.id);
    api.subscribeTask(task_id, () => {}, async () => {
      await loadBoard(projectId);
      setLoading(false);
    });
  }

  async function handleDrop(column: keyof KanbanBoard) {
    if (!dragTaskId) return;
    await api.updateTaskStatus(dragTaskId, column);
    setDragTaskId(null);
    await loadBoard(projectId);
  }

  async function openTask(task: KanbanTask) {
    setSelectedTask(task);
    try {
      setSpec(await api.getSpecByTask(task.id));
    } catch {
      setSpec(null);
    }
  }

  async function handleGenerateSpec() {
    if (!selectedTask) return;
    setLoading(true);
    const { spec_id, task_id_celery } = await api.generateSpec(selectedTask.id);
    api.subscribeTask(task_id_celery, () => {}, async () => {
      setSpec(await api.getSpec(spec_id));
      setLoading(false);
    });
  }

  async function handleAssignSpec(userId: string) {
    if (!spec) return;
    setSpec(await api.assignSpec(spec.id, userId));
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">Kanban board</h1>
        <select
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
        <Button variant="outline" onClick={handleExtractModules} disabled={loading}>
          Extract modules from SRS
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-5">
        {COLUMNS.map(({ key, label }) => (
          <div
            key={key}
            className="min-h-48 rounded-xl border border-gray-800 bg-gray-900/50 p-3"
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => handleDrop(key)}
          >
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-gray-500">
              {label} ({board?.[key]?.length ?? 0})
            </p>
            <div className="space-y-2">
              {(board?.[key] ?? []).map((task) => (
                <div
                  key={task.id}
                  draggable
                  onDragStart={() => setDragTaskId(task.id)}
                  onClick={() => openTask(task)}
                  className="cursor-pointer rounded-md border border-gray-700 bg-gray-950 p-2 text-sm hover:border-gray-500"
                >
                  <p className="font-medium">{task.title}</p>
                  {task.module_name && (
                    <p className="text-xs text-gray-500">{task.module_name}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {selectedTask && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <h2 className="text-lg font-medium">{selectedTask.title}</h2>
          <p className="mt-1 text-sm text-gray-400">{selectedTask.description}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {!spec && (
              <Button onClick={handleGenerateSpec} disabled={loading}>
                Generate technical spec
              </Button>
            )}
            {spec?.status === "generating" && (
              <p className="text-sm text-yellow-400">Generating spec...</p>
            )}
            {spec?.status === "ready" && spec.content_json && (
              <Button
                variant="outline"
                onClick={() =>
                  api.saveToKnowledge({
                    source_type: "spec",
                    source_id: spec.id,
                    title: selectedTask.title,
                  })
                }
              >
                Save to knowledge base
              </Button>
            )}
          </div>
          {spec?.content_json && (
            <div className="mt-4 space-y-3 text-sm">
              <p className="text-gray-300">
                {String(spec.content_json.task_scope ?? "").slice(0, 400)}
              </p>
              <select
                className="rounded-md border border-gray-700 bg-gray-950 px-2 py-1 text-sm"
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
      )}
    </div>
  );
}
