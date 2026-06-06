const DEFAULT_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export interface UserRegister {
  email: string;
  full_name: string;
  password: string;
  role?: string;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  avatar_url: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface TaskStatus {
  task_id: string;
  status: string;
  result?: unknown;
  error?: string;
}

export interface Client {
  id: string;
  name: string;
  company_name: string | null;
  email: string | null;
  phone: string | null;
  notes: string | null;
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  status: string;
  client_id: string;
  created_at: string;
}

export interface Requirement {
  id: string;
  project_id: string;
  original_filename: string;
  status: string;
  analysis_result?: Record<string, unknown> | null;
  cost_estimate?: Record<string, unknown> | null;
  error_message?: string | null;
  created_at: string;
}

export interface PRD {
  id: string;
  project_id: string;
  requirement_id: string | null;
  version: number;
  status: string;
  content_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface SRS {
  id: string;
  project_id: string;
  prd_id: string;
  version: number;
  status: string;
  content_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ScreenPermission {
  screen_key: string;
  can_view: boolean;
  can_edit: boolean;
}

export interface KanbanTask {
  id: string;
  project_id: string;
  srs_id: string | null;
  title: string;
  description: string | null;
  task_type: string;
  priority: string;
  status: string;
  assigned_to_id: string | null;
  effort_hours: number | null;
  fr_references: string[] | null;
  module_name: string | null;
  order_index: number;
  created_at: string;
  updated_at: string;
}

export interface KanbanBoard {
  backlog: KanbanTask[];
  assigned: KanbanTask[];
  in_progress: KanbanTask[];
  in_review: KanbanTask[];
  done: KanbanTask[];
}

export interface TaskSpec {
  id: string;
  task_id: string;
  status: string;
  content_json: Record<string, unknown> | null;
  assigned_to_id: string | null;
  generation_task_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeItem {
  id: string;
  project_id: string | null;
  item_type: string;
  source_type: string;
  source_id: string | null;
  title: string;
  description: string | null;
  content_json: Record<string, unknown> | null;
  tags: string[] | null;
  saved_by_id: string;
  created_at: string;
  updated_at: string;
}

export interface Decision {
  id: string;
  project_id: string;
  title: string;
  decision: string;
  reason: string;
  alternatives: string[] | null;
  decided_by_id: string;
  decided_at: string;
  created_at: string;
  updated_at: string;
}

export interface Notification {
  id: string;
  user_id: string;
  title: string;
  message: string;
  link: string | null;
  is_read: boolean;
  created_at: string;
}

export class ApiClient {
  private readonly baseUrl: string;
  private sessionActive = false;

  constructor(baseUrl: string = DEFAULT_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private getServerUrl(): string {
    return this.baseUrl.replace(/\/api\/v1$/, "");
  }

  /** True when a cookie-based session is believed active (not the token itself). */
  getAccessToken(): string | null {
    return this.sessionActive ? "cookie" : null;
  }

  clearTokens(): void {
    this.sessionActive = false;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
  ): Promise<T> {
    const headers = new Headers(options.headers);
    if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    const url = endpoint.startsWith("http")
      ? endpoint
      : `${this.baseUrl}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
    const fetchOptions: RequestInit = {
      ...options,
      headers,
      credentials: "include",
    };
    const response = await fetch(url, fetchOptions);
    if (
      response.status === 401 &&
      endpoint !== "/auth/refresh" &&
      endpoint !== "/auth/login"
    ) {
      try {
        await this.refresh();
        const retry = await fetch(url, fetchOptions);
        if (!retry.ok) throw new Error(await retry.text());
        if (retry.status === 204) return undefined as T;
        return (await retry.json()) as T;
      } catch {
        this.clearTokens();
        throw new Error("Session expired");
      }
    }
    if (!response.ok) {
      const text = await response.text();
      let message = `Request failed (${response.status})`;
      try {
        const body = JSON.parse(text) as { detail?: string };
        if (body.detail) message = body.detail;
      } catch {
        if (text) message = text;
      }
      throw new Error(message);
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  async health() {
    return this.request(`${this.getServerUrl()}/health`);
  }

  async register(body: UserRegister): Promise<UserResponse> {
    return this.request("/auth/register", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async login(body: { email: string; password: string }): Promise<TokenResponse> {
    const form = new URLSearchParams();
    form.set("username", body.email);
    form.set("password", body.password);
    const result = await this.request<TokenResponse>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
    });
    this.sessionActive = true;
    return result;
  }

  async refresh(): Promise<TokenResponse> {
    const result = await this.request<TokenResponse>("/auth/refresh", {
      method: "POST",
    });
    this.sessionActive = true;
    return result;
  }

  async logout(): Promise<void> {
    try {
      await this.request("/auth/logout", { method: "POST" });
    } finally {
      this.clearTokens();
    }
  }

  async me(): Promise<UserResponse> {
    const user = await this.request<UserResponse>("/auth/me");
    this.sessionActive = true;
    return user;
  }

  async getScreens(): Promise<ScreenPermission[]> {
    return this.request("/auth/screens");
  }

  async getTaskStatus(taskId: string): Promise<TaskStatus> {
    return this.request(`/jobs/${taskId}`);
  }

  subscribeTask(
    taskId: string,
    onUpdate: (data: TaskStatus) => void,
    onDone?: () => void,
  ): EventSource {
    const url = `${this.getServerUrl()}/api/v1/jobs/${taskId}/stream`;
    const es = new EventSource(url);
    es.onmessage = (event) => {
      const data = JSON.parse(event.data) as TaskStatus;
      onUpdate(data);
      if (data.status === "SUCCESS" || data.status === "FAILURE") {
        es.close();
        onDone?.();
      }
    };
    return es;
  }

  // Clients
  async listClients(): Promise<Client[]> {
    return this.request("/clients");
  }
  async createClient(body: Partial<Client>): Promise<Client> {
    return this.request("/clients", { method: "POST", body: JSON.stringify(body) });
  }
  async updateClient(id: string, body: Partial<Client>): Promise<Client> {
    return this.request(`/clients/${id}`, { method: "PATCH", body: JSON.stringify(body) });
  }
  async deleteClient(id: string): Promise<void> {
    return this.request(`/clients/${id}`, { method: "DELETE" });
  }

  // Projects
  async listProjects(): Promise<Project[]> {
    return this.request("/projects");
  }
  async listProjectsByClient(clientId: string): Promise<Project[]> {
    return this.request(`/projects/by-client/${clientId}`);
  }
  async createProject(body: {
    name: string;
    client_id: string;
    description?: string;
  }): Promise<Project> {
    return this.request("/projects", { method: "POST", body: JSON.stringify(body) });
  }

  // Requirements
  async uploadRequirement(projectId: string, file: File) {
    const form = new FormData();
    form.append("project_id", projectId);
    form.append("file", file);
    return this.request<{ requirement_id: string; task_id: string }>(
      "/requirements/upload",
      { method: "POST", body: form },
    );
  }
  async getRequirement(id: string): Promise<Requirement> {
    return this.request(`/requirements/${id}`);
  }
  async listRequirements(projectId: string): Promise<Requirement[]> {
    return this.request(`/requirements/project/${projectId}`);
  }
  async getCostEstimate(id: string): Promise<Record<string, unknown>> {
    return this.request(`/requirements/${id}/cost-estimate`);
  }
  async uploadFeedback(requirementId: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    return this.request(`/requirements/${requirementId}/feedback-upload`, {
      method: "POST",
      body: form,
    });
  }
  getClarificationPdfUrl(id: string): string {
    return `${this.baseUrl}/documents/requirements/${id}/clarification-pdf`;
  }

  // PRDs
  async generatePrd(projectId: string, requirementId: string) {
    return this.request("/prds/generate", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, requirement_id: requirementId }),
    });
  }
  async listPrds(projectId: string): Promise<PRD[]> {
    return this.request(`/prds/project/${projectId}`);
  }
  async getPrd(id: string): Promise<PRD> {
    return this.request(`/prds/${id}`);
  }
  async updatePrd(id: string, content: Record<string, unknown>, changeNote?: string): Promise<PRD> {
    return this.request(`/prds/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ content_json: content, change_note: changeNote }),
    });
  }
  async submitPrd(id: string): Promise<PRD> {
    return this.request(`/prds/${id}/submit`, { method: "PATCH" });
  }
  async approvePrd(id: string): Promise<PRD> {
    return this.request(`/prds/${id}/approve`, { method: "PATCH" });
  }
  getPrdPdfUrl(id: string): string {
    return `${this.baseUrl}/documents/prd/${id}/export-pdf/sync`;
  }

  // SRS
  async generateSrs(projectId: string, prdId: string) {
    return this.request("/srs/generate", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, prd_id: prdId }),
    });
  }
  async listSrs(projectId: string): Promise<SRS[]> {
    return this.request(`/srs/project/${projectId}`);
  }
  async getSrs(id: string): Promise<SRS> {
    return this.request(`/srs/${id}`);
  }
  async submitSrs(id: string): Promise<SRS> {
    return this.request(`/srs/${id}/submit`, { method: "PATCH" });
  }
  async approveSrs(id: string): Promise<SRS> {
    return this.request(`/srs/${id}/approve`, { method: "PATCH" });
  }
  getSrsPdfUrl(id: string): string {
    return `${this.baseUrl}/documents/srs/${id}/export-pdf/sync`;
  }

  // Kanban tasks
  async getKanban(projectId: string): Promise<KanbanBoard> {
    return this.request(`/tasks/kanban/${projectId}`);
  }
  async createTask(body: Partial<KanbanTask> & { project_id: string; title: string }) {
    return this.request<KanbanTask>("/tasks", { method: "POST", body: JSON.stringify(body) });
  }
  async updateTaskStatus(taskId: string, status: string, note?: string) {
    return this.request<KanbanTask>(`/tasks/${taskId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status, note }),
    });
  }
  async extractModules(projectId: string, srsId: string) {
    return this.request<{ task_id: string; status: string }>("/tasks/extract-modules", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, srs_id: srsId }),
    });
  }

  // Specs
  async generateSpec(taskId: string) {
    return this.request<{ spec_id: string; task_id_celery: string }>("/specs/generate", {
      method: "POST",
      body: JSON.stringify({ task_id: taskId }),
    });
  }
  async getSpec(specId: string): Promise<TaskSpec> {
    return this.request(`/specs/${specId}`);
  }
  async getSpecByTask(taskId: string): Promise<TaskSpec> {
    return this.request(`/specs/task/${taskId}`);
  }
  async assignSpec(specId: string, assignedToId: string): Promise<TaskSpec> {
    return this.request(`/specs/${specId}/assign`, {
      method: "PATCH",
      body: JSON.stringify({ assigned_to_id: assignedToId }),
    });
  }

  // Knowledge base
  async listKnowledgeItems(projectId?: string): Promise<KnowledgeItem[]> {
    const q = projectId ? `?project_id=${projectId}` : "";
    return this.request(`/knowledge/items${q}`);
  }
  async saveToKnowledge(body: {
    source_type: string;
    source_id: string;
    title?: string;
    tags?: string[];
  }): Promise<KnowledgeItem> {
    return this.request("/knowledge/items/save-from-source", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  // Decisions
  async listDecisions(projectId?: string): Promise<Decision[]> {
    const q = projectId ? `?project_id=${projectId}` : "";
    return this.request(`/decisions${q}`);
  }
  async createDecision(body: {
    project_id: string;
    title: string;
    decision: string;
    reason: string;
    alternatives?: string[];
  }): Promise<Decision> {
    return this.request("/decisions", { method: "POST", body: JSON.stringify(body) });
  }

  // Notifications
  async listNotifications(unreadOnly = false): Promise<Notification[]> {
    return this.request(`/notifications?unread_only=${unreadOnly}`);
  }
  async markNotificationRead(id: string): Promise<Notification> {
    return this.request(`/notifications/${id}/read`, { method: "PATCH" });
  }
  async markAllNotificationsRead(): Promise<void> {
    return this.request("/notifications/read-all", { method: "POST" });
  }

  // Users (admin)
  async listUsers(): Promise<UserResponse[]> {
    return this.request("/users");
  }
  async createUser(body: UserRegister): Promise<UserResponse> {
    return this.request("/users", { method: "POST", body: JSON.stringify(body) });
  }
  async updateUser(id: string, body: Partial<UserRegister & { is_active: boolean }>) {
    return this.request(`/users/${id}`, { method: "PATCH", body: JSON.stringify(body) });
  }
}

export const api = new ApiClient();
