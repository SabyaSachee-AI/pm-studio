const DEFAULT_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";

export interface PermissionCell {
  role: string;
  screen_key: string;
  can_view: boolean;
  can_edit: boolean;
}

export interface PermissionMatrix {
  roles: string[];
  admin_roles: string[];
  screens: string[];
  permissions: PermissionCell[];
}

export interface DashboardStats {
  generated_at: string;
  projects: { total: number; by_status: Record<string, number> };
  clients: { total: number };
  users: { total: number; by_role: Record<string, number> };
  pipeline: Record<string, number>;
  tasks: {
    total: number;
    by_status: Record<string, number>;
    specs_ready: number;
    specs_total: number;
  };
  ai: {
    total_requests_today: number;
    total_tokens_in: number;
    total_tokens_out: number;
    total_tokens: number;
    by_provider: Record<string, {
      label: string; tier: string; color: string;
      requests: number; requests_limit: number;
      tokens_in: number; tokens_out: number;
      tokens_total: number; tokens_limit: number;
    }>;
  };
  recent_projects: Array<{ id: string; name: string; status: string; updated_at: string | null }>;
}

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
  meta?: {
    current_model?: string;
    current_doc?: string;
    phase?: string;
    message?: string;
    attempt?: number;
    current_provider?: string;
  };
}

export interface ModelChoice {
  provider: string;
  model: string;
}

export interface AiModelOption {
  provider: string;
  model: string;
  label: string;
  tier: string;
  cost: string;
  context?: string;
  group: "premium" | "low_cost" | "free" | string;
  available?: boolean;
}

export interface AiModelCatalog {
  default_tier: string;
  models: AiModelOption[];
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

export interface BuildSummary {
  id: string;
  project_id: string;
  architecture_id: string | null;
  status: string;
  version: number;
  display_name: string | null;
  repo_url: string | null;
  github_full_name: string | null;
  default_branch: string;
  quality_score: number | null;
  quality_report: Record<string, unknown> | null;
  generation_progress: Record<string, unknown> | null;
  generation_task_id: string | null;
  can_resume: boolean;
  last_error: string | null;
  file_count: number;
  created_at: string;
  updated_at: string;
}

export interface GeneratedFileListItem {
  id: string;
  task_id: string | null;
  path: string;
  language: string;
  status: string;
}

export interface GeneratedFile extends GeneratedFileListItem {
  content: string;
  checksum: string | null;
}

export interface BuildDetail extends BuildSummary {
  files: GeneratedFileListItem[];
}

export interface Requirement {
  id: string;
  project_id: string;
  original_filename: string;
  display_name?: string;
  status: string;
  analysis_result?: Record<string, unknown> | null;
  cost_estimate?: Record<string, unknown> | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
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
  source_prd_display_name?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Architecture {
  id: string;
  project_id: string;
  srs_id: string;
  status: string;
  version: number;
  display_name?: string | null;
  created_by_id: string;
  confirmed_by_id?: string | null;
  confirmed_at?: string | null;
  generation_task_id?: string | null;
  doc_task_ids?: Record<string, string> | null;
  generation_progress?: Record<string, unknown> | null;
  doc_cancel_flags?: Record<string, boolean> | null;
  can_resume?: boolean;
  last_error?: string | null;
  resume_from?: string | null;
  suite_canon?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  doc_system_arch?: Record<string, unknown> | null;
  doc_database?: Record<string, unknown> | null;
  doc_api?: Record<string, unknown> | null;
  doc_frontend?: Record<string, unknown> | null;
  doc_security?: Record<string, unknown> | null;
  doc_uiux?: Record<string, unknown> | null;
  doc_system_arch_status?: string | null;
  doc_database_status?: string | null;
  doc_api_status?: string | null;
  doc_frontend_status?: string | null;
  doc_security_status?: string | null;
  doc_uiux_status?: string | null;
  consistency_report?: {
    scores?: Record<string, number>;
    overall?: number;
    issues?: string[];
    fr_coverage?: string;
    endpoint_count?: number;
    missing_frs?: string[];
    edited_docs?: string[];
  } | null;
  nfr_profile?: Record<string, string> | null;
  capabilities?: Record<string, boolean> | null;
}

export interface ArchitectureListItem {
  id: string;
  project_id: string;
  srs_id: string;
  status: string;
  version: number;
  display_name: string;
  created_at: string;
  updated_at?: string;
  source_srs_display_name?: string | null;
  docs_generated: number;
  docs_total: number;
  doc_system_arch_status?: string | null;
  doc_database_status?: string | null;
  doc_api_status?: string | null;
  doc_frontend_status?: string | null;
  doc_security_status?: string | null;
  doc_uiux_status?: string | null;
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
  linked_fr: string | null;
  module_name: string | null;
  order_index: number;
  suggested_file: string | null;
  suggested_endpoint: string | null;
  suggested_table: string | null;
  spec_id: string | null;
  spec_status: string | null;
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

export interface AiProviderStatus {
  provider: string;
  configured: boolean;
  is_enabled: boolean;
  masked_key: string | null;
  label?: string;
  signup_url?: string | null;
  note?: string | null;
  default_tier?: string;
}

export interface ModelCatalogEntry {
  provider: string;
  model: string;
  label: string;
  tier: string;
  cost: string;
  context: string;
  note: string;
  task_types: string[];
  in_routing: boolean;
  available: boolean;
}

export interface TierModelCatalog {
  free: ModelCatalogEntry[];
  low_cost: ModelCatalogEntry[];
  premium: ModelCatalogEntry[];
}

export interface AiRoutingRow {
  task_type: string;
  task_label: string;
  quality_stars: number;
  primary_model: string;
  fallback_chain: string;
  quality_note: string | null;
}

export interface ScreenModelInfo {
  screen: string;
  provider: string;
  model: string;
  label: string;
  source: string;
}

export type AiTier = "free" | "low_cost" | "premium";

export interface ProviderUsage {
  requests: number;
  tokens_in: number;
  tokens_out: number;
  requests_limit: number;
  tokens_limit: number;
  label: string;
  color: string;
}

export interface AiConfigResponse {
  ai_tier: AiTier;
  free_mode_enabled: boolean;
  providers: AiProviderStatus[];
  paid_routing: AiRoutingRow[];
  free_routing: AiRoutingRow[];
  low_cost_routing: AiRoutingRow[];
  screen_overrides: Record<string, { provider: string; model: string }>;
  screen_models: ScreenModelInfo[];
  paid_model_options: AiModelOption[];
  free_model_options: AiModelOption[];
  low_cost_model_options: AiModelOption[];
  daily_usage: Record<string, ProviderUsage>;
  model_catalog: TierModelCatalog;
  configured_model_catalog: TierModelCatalog;
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

  getAccessToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  }

  setTokens(access: string, refresh: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, access);
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
  }

  clearTokens(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    allowRefresh = true,
  ): Promise<T> {
    const headers = new Headers(options.headers);
    if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    const token = this.getAccessToken();
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    const url = endpoint.startsWith("http")
      ? endpoint
      : `${this.baseUrl}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
    let response: Response;
    try {
      response = await fetch(url, {
        ...options,
        headers,
        credentials: "include",
      });
    } catch {
      throw new Error(
        "Cannot reach the API server. Check that the backend is running on port 8000.",
      );
    }
    const isAuthEndpoint =
      endpoint.includes("/auth/refresh") || endpoint.includes("/auth/login");
    if (response.status === 401 && allowRefresh && !isAuthEndpoint) {
      try {
        await this.refresh();
        const retry = await fetch(url, {
          ...options,
          headers,
          credentials: "include",
        });
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
        const body = JSON.parse(text) as { detail?: string | unknown };
        if (body.detail) {
          message =
            typeof body.detail === "string"
              ? body.detail
              : JSON.stringify(body.detail);
        }
      } catch {
        if (text) message = text;
      }
      throw new Error(message);
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  getRefreshToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(REFRESH_TOKEN_KEY);
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

  async login(body: { email: string; password: string }): Promise<{ token_type: string }> {
    // Backend sets HttpOnly auth cookies; the response body has no tokens.
    const form = new URLSearchParams();
    form.set("username", body.email);
    form.set("password", body.password);
    return this.request<{ token_type: string }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
    });
  }

  async refresh(): Promise<{ token_type: string }> {
    // Refresh uses the HttpOnly refresh cookie; no body needed.
    const response = await fetch(`${this.baseUrl}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      this.clearTokens();
      throw new Error("Session expired");
    }
    return (await response.json()) as { token_type: string };
  }

  async logout(): Promise<void> {
    try {
      await this.request("/auth/logout", { method: "POST" });
    } finally {
      this.clearTokens();
    }
  }

  async getPermissionMatrix(): Promise<PermissionMatrix> {
    return this.request<PermissionMatrix>("/admin/screen-permissions");
  }

  async updatePermission(
    role: string,
    screen_key: string,
    can_view: boolean,
    can_edit: boolean,
  ): Promise<PermissionCell> {
    return this.request<PermissionCell>(`/admin/screen-permissions/${role}/${screen_key}`, {
      method: "PATCH",
      body: JSON.stringify({ can_view, can_edit }),
    });
  }

  async getDashboardStats(): Promise<DashboardStats> {
    return this.request<DashboardStats>("/dashboard/stats");
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

  async getSyncProgress(progressId: string): Promise<{
    progress_id: string;
    status: string;
    meta: TaskStatus["meta"];
  }> {
    return this.request(`/jobs/progress/${progressId}`);
  }

  // AI model catalog + per-action override
  async listAiModels(): Promise<AiModelCatalog> {
    return this.request("/ai/models");
  }

  /** Build ?model_provider=&model_id= query suffix for a one-shot model choice. */
  private modelQS(model?: ModelChoice | null, hasQuery = false): string {
    if (!model?.provider || !model?.model) return "";
    const sep = hasQuery ? "&" : "?";
    return `${sep}model_provider=${encodeURIComponent(model.provider)}&model_id=${encodeURIComponent(model.model)}`;
  }

  /** Query string for sync AI actions with optional live progress polling. */
  private aiActionQS(options?: {
    model?: ModelChoice | null;
    progressId?: string;
  }): string {
    const params = new URLSearchParams();
    if (options?.progressId) params.set("progress_id", options.progressId);
    if (options?.model?.provider && options?.model?.model) {
      params.set("model_provider", options.model.provider);
      params.set("model_id", options.model.model);
    }
    const qs = params.toString();
    return qs ? `?${qs}` : "";
  }

  subscribeTask(
    taskId: string,
    onUpdate: (data: TaskStatus) => void,
    onDone?: () => void,
  ): EventSource {
    const url = `${this.getServerUrl()}/api/v1/jobs/${taskId}/stream`;
    const es = new EventSource(url, { withCredentials: true });
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
  async uploadRequirement(projectId: string, file: File, model?: ModelChoice | null) {
    const form = new FormData();
    form.append("project_id", projectId);
    form.append("file", file);
    return this.request<{ requirement_id: string; task_id: string }>(
      `/requirements/upload${this.modelQS(model)}`,
      { method: "POST", body: form },
    );
  }
  async getRequirement(id: string): Promise<Requirement> {
    return this.request(`/requirements/${id}`);
  }
  async listRequirements(projectId: string): Promise<Requirement[]> {
    return this.request(`/requirements/project/${projectId}`);
  }
  async deleteRequirement(id: string): Promise<void> {
    return this.request(`/requirements/${id}`, { method: "DELETE" });
  }
  async regenerateRequirement(id: string, model?: ModelChoice | null) {
    return this.request<{ requirement_id: string; task_id: string; status: string }>(
      `/requirements/${id}/regenerate${this.modelQS(model)}`,
      { method: "POST" },
    );
  }
  async getCostEstimate(id: string): Promise<Record<string, unknown>> {
    return this.request(`/requirements/${id}/cost-estimate`);
  }
  async uploadFeedback(requirementId: string, file: File, model?: ModelChoice | null) {
    const form = new FormData();
    form.append("file", file);
    return this.request(`/requirements/${requirementId}/feedback-document${this.modelQS(model)}`, {
      method: "POST",
      body: form,
    });
  }
  async synthesizeRequirement(
    id: string,
    model?: ModelChoice | null,
    progressId?: string,
  ) {
    return this.request<Record<string, unknown>>(
      `/requirements/${id}/synthesize${this.aiActionQS({ model, progressId })}`,
      { method: "POST" },
    );
  }
  async reanalyzeRequirement(
    id: string,
    instructions: string,
    model?: ModelChoice | null,
    progressId?: string,
  ) {
    return this.request<Record<string, unknown>>(
      `/requirements/${id}/reanalyze${this.aiActionQS({ model, progressId })}`,
      {
        method: "POST",
        body: JSON.stringify({ instructions }),
      },
    );
  }
  async finalizeRequirement(id: string): Promise<Requirement> {
    return this.request<Requirement>(`/requirements/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "finalized" }),
    });
  }
  getClarificationPdfUrl(id: string): string {
    return `${this.baseUrl}/documents/requirements/${id}/clarification-pdf`;
  }

  async downloadClarificationPdf(id: string): Promise<void> {
    const url = this.getClarificationPdfUrl(id);
    const response = await fetch(url, { credentials: "include" });
    if (!response.ok) {
      let message = `Download failed (${response.status})`;
      try {
        const body = (await response.json()) as { detail?: string };
        if (body.detail) message = body.detail;
      } catch {
        /* non-JSON error body */
      }
      throw new Error(message);
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = `clarification-${id}.pdf`;
    link.click();
    URL.revokeObjectURL(objectUrl);
  }

  // PRDs
  async generatePrd(projectId: string, requirementId: string, model?: ModelChoice | null) {
    return this.request(`/prds/generate${this.modelQS(model)}`, {
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
  async deletePrd(id: string): Promise<void> {
    return this.request(`/prds/${id}`, { method: "DELETE" });
  }
  async regeneratePrd(id: string, model?: ModelChoice | null) {
    return this.request<{ prd_id: string; task_id: string; status: string }>(
      `/prds/${id}/regenerate${this.modelQS(model)}`,
      { method: "POST" },
    );
  }

  // SRS
  async generateSrs(projectId: string, prdId: string, model?: ModelChoice | null) {
    return this.request(`/srs/generate${this.modelQS(model)}`, {
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
  async deleteSrs(id: string): Promise<void> {
    return this.request(`/srs/${id}`, { method: "DELETE" });
  }
  async regenerateSrs(id: string, model?: ModelChoice | null) {
    return this.request<{ srs_id: string; task_id: string; status: string }>(
      `/srs/${id}/regenerate${this.modelQS(model)}`,
      { method: "POST" },
    );
  }

  // Architecture
  async generateArchitecture(
    projectId: string,
    srsId: string,
    model?: ModelChoice | null,
  ) {
    return this.request<{
      architecture_id: string;
      task_id: string;
      status: string;
    }>(`/architecture/generate${this.modelQS(model)}`, {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, srs_id: srsId }),
    });
  }
  async listArchitectures(projectId?: string): Promise<ArchitectureListItem[]> {
    const q = projectId ? `?project_id=${projectId}` : "";
    return this.request(`/architecture${q}`);
  }
  async getArchitecture(id: string): Promise<Architecture> {
    return this.request(`/architecture/${id}`);
  }
  async confirmArchitecture(id: string): Promise<Architecture> {
    return this.request(`/architecture/${id}/confirm`, { method: "PATCH" });
  }
  async finalizeArchitecture(id: string): Promise<Architecture> {
    return this.request(`/architecture/${id}/finalize`, { method: "PATCH" });
  }
  async setNfrProfile(id: string, profile: Record<string, string>): Promise<Architecture> {
    return this.request(`/architecture/${id}/nfr-profile`, {
      method: "PATCH",
      body: JSON.stringify({ nfr_profile: profile }),
    });
  }
  async setCapabilities(id: string, capabilities: Record<string, boolean>): Promise<Architecture> {
    return this.request(`/architecture/${id}/capabilities`, {
      method: "PATCH",
      body: JSON.stringify({ capabilities }),
    });
  }
  async updateArchitectureDoc(
    id: string,
    docKey: string,
    content: Record<string, unknown>,
  ): Promise<Architecture> {
    return this.request(`/architecture/${id}/doc`, {
      method: "PATCH",
      body: JSON.stringify({ doc_key: docKey, content }),
    });
  }
  async deleteArchitecture(id: string): Promise<void> {
    return this.request(`/architecture/${id}`, { method: "DELETE" });
  }
  async regenerateArchitecture(id: string) {
    return this.request<{
      architecture_id: string;
      task_id: string;
      status: string;
    }>(`/architecture/${id}/regenerate`, { method: "POST" });
  }
  async consolidateArchitecture(id: string) {
    return this.request<{
      architecture_id: string;
      task_id: string;
      status: string;
    }>(`/architecture/${id}/consolidate`, { method: "POST" });
  }
  async resumeArchitecture(id: string, model?: ModelChoice | null) {
    return this.request<{
      architecture_id: string;
      task_id: string;
      status: string;
    }>(`/architecture/${id}/resume${this.modelQS(model)}`, { method: "POST" });
  }
  async reassessArchitecture(id: string, model?: ModelChoice | null) {
    return this.request<{
      architecture_id: string;
      task_id: string;
      status: string;
    }>(`/architecture/${id}/reassess${this.modelQS(model)}`, { method: "POST" });
  }
  async editArchitectureSuite(id: string, instruction: string, model?: ModelChoice | null) {
    return this.request<{
      architecture_id: string;
      task_id: string;
      status: string;
    }>(`/architecture/${id}/edit-suite${this.modelQS(model)}`, {
      method: "POST",
      body: JSON.stringify({ instruction }),
    });
  }
  async generateArchitectureDoc(id: string, docKey: string, model?: ModelChoice | null) {
    return this.request<{
      architecture_id: string;
      task_id: string;
      status: string;
    }>(`/architecture/${id}/generate-doc/${docKey}${this.modelQS(model)}`, {
      method: "POST",
    });
  }
  async cancelArchitectureDoc(id: string, docKey: string) {
    return this.request<{
      architecture_id: string;
      doc_key: string;
      status: string;
    }>(`/architecture/${id}/cancel-doc/${docKey}`, { method: "POST" });
  }
  async regenerateArchitectureDoc(id: string, docKey: string, model?: ModelChoice | null) {
    return this.request<{
      architecture_id: string;
      task_id: string;
      status: string;
    }>(`/architecture/${id}/regenerate-doc/${docKey}${this.modelQS(model)}`, {
      method: "POST",
    });
  }
  async regenerateArchitectureDiagram(
    id: string,
    docKey: string,
    diagramName: string,
    model?: ModelChoice | null,
  ) {
    return this.request<{
      architecture_id: string;
      doc_key: string;
      diagram_name: string;
      task_id: string;
      status: string;
    }>(
      `/architecture/${id}/regenerate-diagram/${docKey}/${diagramName}${this.modelQS(model)}`,
      { method: "POST" },
    );
  }
  async deleteArchitectureDoc(id: string, docKey: string): Promise<Architecture> {
    return this.request(`/architecture/${id}/doc/${docKey}`, { method: "DELETE" });
  }
  async aiEditArchitectureDoc(
    id: string,
    docKey: string,
    currentContent: Record<string, unknown>,
    instruction: string,
    model?: ModelChoice | null,
  ): Promise<{ corrected_content: Record<string, unknown> }> {
    return this.request(`/architecture/${id}/doc/${docKey}/ai-edit${this.modelQS(model)}`, {
      method: "PATCH",
      body: JSON.stringify({
        instruction,
        current_content: currentContent,
      }),
    });
  }
  async polishArchitectureForExport(
    id: string,
    body: { mode: "full" | "section"; doc_key?: string },
    model?: ModelChoice | null,
  ): Promise<{ documents: Record<string, Record<string, unknown>> }> {
    return this.request(`/architecture/${id}/polish-export${this.modelQS(model)}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
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
  async updateTask(
    taskId: string,
    body: {
      title?: string;
      description?: string | null;
      priority?: string;
      module_name?: string | null;
    },
  ): Promise<KanbanTask> {
    return this.request<KanbanTask>(`/tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  }
  async extractModules(
    projectId: string,
    srsId: string,
    opts?: { replaceExisting?: boolean; fillGapsOnly?: boolean },
  ) {
    return this.request<{ task_id: string; status: string }>("/tasks/extract-modules", {
      method: "POST",
      body: JSON.stringify({
        project_id:       projectId,
        srs_id:           srsId,
        replace_existing: opts?.replaceExisting ?? false,
        fill_gaps_only:   opts?.fillGapsOnly   ?? false,
      }),
    });
  }
  async getProjectBible(projectId: string): Promise<{ content: string; project_name: string }> {
    return this.request(`/tasks/project-bible/${projectId}`);
  }

  // ── Code-generation builds ──────────────────────────────────────────────
  async listBuilds(projectId?: string): Promise<BuildSummary[]> {
    const qs = projectId ? `?project_id=${projectId}` : "";
    return this.request(`/builds${qs}`);
  }
  async createBuild(projectId: string, architectureId?: string): Promise<BuildSummary> {
    return this.request(`/builds`, {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, architecture_id: architectureId ?? null }),
    });
  }
  async getBuild(id: string): Promise<BuildDetail> {
    return this.request(`/builds/${id}`);
  }
  async getBuildFile(id: string, fileId: string): Promise<GeneratedFile> {
    return this.request(`/builds/${id}/file/${fileId}`);
  }
  async scaffoldBuild(id: string, model?: ModelChoice | null) {
    return this.request<{ build_id: string; task_id: string; status: string }>(
      `/builds/${id}/scaffold${this.modelQS(model)}`, { method: "POST" });
  }
  async generateBuild(id: string, resume = false, model?: ModelChoice | null) {
    const sep = this.modelQS(model) ? "&" : "?";
    return this.request<{ build_id: string; task_id: string; status: string }>(
      `/builds/${id}/generate${this.modelQS(model)}${sep}resume=${resume}`, { method: "POST" });
  }
  async generateTaskCode(id: string, taskId: string, model?: ModelChoice | null) {
    return this.request<{ build_id: string; task_id: string; status: string }>(
      `/builds/${id}/generate-task/${taskId}${this.modelQS(model)}`, { method: "POST" });
  }
  async updateBuildFile(id: string, fileId: string, content: string): Promise<GeneratedFile> {
    return this.request(`/builds/${id}/file/${fileId}`, {
      method: "PATCH",
      body: JSON.stringify({ content }),
    });
  }
  async aiEditBuildFile(id: string, fileId: string, instruction: string, model?: ModelChoice | null): Promise<GeneratedFile> {
    return this.request(`/builds/${id}/file/${fileId}/ai-edit${this.modelQS(model)}`, {
      method: "POST",
      body: JSON.stringify({ instruction }),
    });
  }
  async pushBuild(id: string) {
    return this.request<{ build_id: string; task_id: string; status: string }>(
      `/builds/${id}/push`, { method: "POST" });
  }
  async getBuildQa(id: string): Promise<{
    status?: string;
    conclusion?: string | null;
    run_url?: string;
    quality_score?: number | null;
    message?: string;
    error?: string;
  }> {
    return this.request(`/builds/${id}/qa`);
  }
  async repairBuild(id: string, model?: ModelChoice | null) {
    return this.request<{ build_id: string; task_id: string; status: string }>(
      `/builds/${id}/repair${this.modelQS(model)}`, { method: "POST" });
  }
  async markBuildReady(id: string): Promise<BuildSummary> {
    return this.request(`/builds/${id}/mark-ready`, { method: "POST" });
  }
  async syncBuildFromGithub(id: string): Promise<{
    status: string; added: number; updated: number; removed: number; total: number;
  }> {
    return this.request(`/builds/${id}/sync-from-github`, { method: "POST" });
  }
  async generateBuildTests(id: string, model?: ModelChoice | null) {
    return this.request<{ build_id: string; task_id: string; status: string }>(
      `/builds/${id}/generate-tests${this.modelQS(model)}`, { method: "POST" });
  }
  async polishBuild(id: string, scope: "critical" | "all", model?: ModelChoice | null) {
    const sep = this.modelQS(model) ? "&" : "?";
    return this.request<{ build_id: string; task_id: string; status: string }>(
      `/builds/${id}/polish${this.modelQS(model)}${sep}scope=${scope}`, { method: "POST" });
  }
  async getBuildUiChecklist(id: string): Promise<{
    repo_url: string | null;
    clone_cmd: string;
    run_cmd: string;
    items: { key: string; task_title: string; criterion: string }[];
  }> {
    return this.request(`/builds/${id}/ui-checklist`);
  }
  async saveBuildUiTest(
    id: string,
    results: { key: string; status: string; note: string }[],
    signedOff: boolean,
  ): Promise<BuildSummary> {
    return this.request(`/builds/${id}/ui-test`, {
      method: "POST",
      body: JSON.stringify({ results, signed_off: signedOff }),
    });
  }
  async deployBuild(id: string, port?: number) {
    const qs = port ? `?port=${port}` : "";
    return this.request<{ build_id: string; task_id: string; status: string }>(
      `/builds/${id}/deploy${qs}`, { method: "POST" });
  }
  async deleteBuild(id: string): Promise<void> {
    return this.request(`/builds/${id}`, { method: "DELETE" });
  }
  async getTraceability(projectId: string): Promise<any> {
    return this.request(`/tasks/traceability/${projectId}`);
  }
  async getTaskCoverage(projectId: string): Promise<{
    total_frs: number;
    covered_frs: number;
    missing_frs: string[];
    total_tasks: number;
    tasks_with_spec: number;
    tasks_done: number;
    has_tasks: boolean;
    all_done: boolean;
    coverage_pct: number;
  }> {
    return this.request(`/tasks/coverage/${projectId}`);
  }

  // Specs
  async generateSpec(taskId: string, model?: ModelChoice | null) {
    return this.request<{ spec_id: string; task_id_celery: string }>(
      `/specs/generate${this.modelQS(model)}`,
      {
        method: "POST",
        body: JSON.stringify({ task_id: taskId }),
      },
    );
  }
  async generateAllSpecs(projectId: string, onlyMissing = true, model?: ModelChoice | null) {
    return this.request<{ task_id: string; status: string }>(
      `/specs/generate-all${this.modelQS(model)}`,
      {
        method: "POST",
        body: JSON.stringify({ project_id: projectId, only_missing: onlyMissing }),
      },
    );
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
  async updateSpec(specId: string, content: Record<string, unknown>): Promise<TaskSpec> {
    return this.request(`/specs/${specId}`, {
      method: "PATCH",
      body: JSON.stringify({ content_json: content }),
    });
  }
  async deleteSpec(specId: string): Promise<void> {
    return this.request(`/specs/${specId}`, { method: "DELETE" });
  }
  async regenerateSpec(specId: string, model?: ModelChoice | null) {
    return this.request<{
      spec_id: string;
      task_id: string;
      task_id_celery: string;
      status: string;
    }>(`/specs/${specId}/regenerate${this.modelQS(model)}`, { method: "POST" });
  }
  async regenerateSpecByTask(taskId: string, model?: ModelChoice | null) {
    return this.request<{
      spec_id: string;
      task_id: string;
      task_id_celery: string;
      status: string;
    }>(`/specs/regenerate${this.modelQS(model)}`, {
      method: "POST",
      body: JSON.stringify({ task_id: taskId }),
    });
  }
  async deleteTask(taskId: string): Promise<void> {
    return this.request(`/tasks/${taskId}`, { method: "DELETE" });
  }
  async clearProjectTasks(projectId: string): Promise<{ deleted_tasks: number; deleted_specs: number }> {
    return this.request(`/tasks/clear/${projectId}`, { method: "DELETE" });
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

  // AI configuration
  async getAiConfig(): Promise<AiConfigResponse> {
    return this.request("/admin/ai-config");
  }
  async getAiConfigForScreens(): Promise<AiConfigResponse> {
    return this.request("/admin/ai-config/screen");
  }
  async setAiTier(tier: AiTier): Promise<AiConfigResponse> {
    return this.request("/admin/ai-config/tier", {
      method: "PATCH",
      body: JSON.stringify({ tier }),
    });
  }
  async setFreeMode(enabled: boolean): Promise<AiConfigResponse> {
    return this.request("/admin/ai-config/free-mode", {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
  }
  async useAllFree(): Promise<AiConfigResponse> {
    return this.request("/admin/ai-config/use-all-free", { method: "POST" });
  }
  async setScreenModelOverride(
    screen: string,
    provider: string | null,
    model: string | null,
  ): Promise<AiConfigResponse> {
    return this.request("/admin/ai-config/screen-override", {
      method: "PATCH",
      body: JSON.stringify({ screen, provider, model }),
    });
  }
  async updateAiProvider(
    provider: string,
    apiKey?: string,
    isEnabled?: boolean,
  ): Promise<AiConfigResponse> {
    return this.request("/admin/ai-config/provider", {
      method: "PATCH",
      body: JSON.stringify({
        provider,
        api_key: apiKey,
        is_enabled: isEnabled,
      }),
    });
  }
  async getGithubConfig(): Promise<{
    configured: boolean;
    masked_token: string | null;
    owner: string | null;
    source: string;
  }> {
    return this.request("/admin/ai-config/github");
  }
  async setGithubConfig(token: string | null, owner: string | null): Promise<{
    configured: boolean;
    masked_token: string | null;
    owner: string | null;
    source: string;
  }> {
    return this.request("/admin/ai-config/github", {
      method: "PATCH",
      body: JSON.stringify({ token, owner }),
    });
  }
  async verifyGithub(): Promise<{
    ok: boolean;
    login?: string | null;
    token_type?: string;
    scopes?: string[];
    checks?: Record<string, "pass" | "fail" | "unknown">;
    message?: string;
  }> {
    return this.request("/admin/ai-config/github/verify", { method: "POST" });
  }
  async getVpsConfig(): Promise<{
    configured: boolean; host: string | null; user: string | null; path: string | null; has_key: boolean;
  }> {
    return this.request("/admin/ai-config/vps");
  }
  async setVpsConfig(cfg: { host?: string; user?: string; ssh_key?: string; path?: string }): Promise<{
    configured: boolean; host: string | null; user: string | null; path: string | null; has_key: boolean;
  }> {
    return this.request("/admin/ai-config/vps", { method: "PATCH", body: JSON.stringify(cfg) });
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
