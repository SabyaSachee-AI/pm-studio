const DEFAULT_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";

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

export class ApiClient {
  private readonly baseUrl: string;

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
    const response = await fetch(url, { ...options, headers });
    if (response.status === 401 && this.getRefreshToken()) {
      try {
        await this.refresh();
        headers.set("Authorization", `Bearer ${this.getAccessToken()}`);
        const retry = await fetch(url, { ...options, headers });
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

  async login(body: { email: string; password: string }): Promise<TokenResponse> {
    const form = new URLSearchParams();
    form.set("username", body.email);
    form.set("password", body.password);
    const result = await this.request<TokenResponse>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
    });
    this.setTokens(result.access_token, result.refresh_token);
    return result;
  }

  async refresh(): Promise<TokenResponse> {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) throw new Error("No refresh token");
    const result = await this.request<TokenResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    const existingRefresh = this.getRefreshToken() ?? refreshToken;
    this.setTokens(result.access_token, existingRefresh);
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
    return this.request("/auth/me");
  }

  async getTaskStatus(taskId: string): Promise<TaskStatus> {
    return this.request(`/tasks/${taskId}`);
  }

  subscribeTask(
    taskId: string,
    onUpdate: (data: TaskStatus) => void,
    onDone?: () => void,
  ): EventSource {
    const url = `${this.getServerUrl()}/api/v1/tasks/${taskId}/stream`;
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
  async updatePrd(id: string, content: Record<string, unknown>, changeNote?: string) {
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
