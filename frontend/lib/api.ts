const DEFAULT_BASE_URL = "http://localhost:8000/api/v1";
const ACCESS_TOKEN_KEY = "access_token";

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

export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
  version: string;
}

export class ApiClient {
  private readonly baseUrl: string;

  constructor(baseUrl: string = DEFAULT_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private getServerUrl(): string {
    return this.baseUrl.replace(/\/api\/v1$/, "");
  }

  private getAccessToken(): string | null {
    if (typeof window === "undefined") {
      return null;
    }
    return localStorage.getItem(ACCESS_TOKEN_KEY);
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

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const text = await response.text();
      let message = `Request failed with status ${response.status}`;

      try {
        const errorBody = JSON.parse(text) as { detail?: string | { msg: string }[] };
        if (typeof errorBody.detail === "string") {
          message = errorBody.detail;
        } else if (Array.isArray(errorBody.detail)) {
          message = errorBody.detail.map((item) => item.msg).join(", ");
        }
      } catch {
        if (text) {
          message = text;
        }
      }

      throw new Error(message);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  }

  async health(): Promise<HealthResponse> {
    const url = `${this.getServerUrl()}/health`;
    return this.request<HealthResponse>(url);
  }

  async register(body: UserRegister): Promise<UserResponse> {
    return this.request<UserResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async login(body: {
    email: string;
    password: string;
  }): Promise<TokenResponse> {
    const formData = new URLSearchParams();
    formData.set("username", body.email);
    formData.set("password", body.password);

    const headers = new Headers();
    headers.set("Content-Type", "application/x-www-form-urlencoded");

    return this.request<TokenResponse>("/auth/login", {
      method: "POST",
      headers,
      body: formData.toString(),
    });
  }

  async me(): Promise<UserResponse> {
    return this.request<UserResponse>("/auth/me");
  }

  async getTaskStatus(taskId: string): Promise<TaskStatus> {
    return this.request<TaskStatus>(`/tasks/${taskId}`);
  }
}

export const api = new ApiClient();
