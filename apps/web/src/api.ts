export type Job = {
  id: number;
  name: string;
  jd_text: string;
  score_threshold: number;
  greet_template: string;
  enabled: boolean;
};

export type Candidate = {
  id: number;
  name: string;
  boss_id: string | null;
  fingerprint: string;
  age: number | null;
  years_of_experience: number | null;
};

export type AgentRun = {
  machine_id: string;
  status: string;
  last_error: string;
};

export type UserMe = {
  id: number;
  username: string;
  role: string;
  is_active: boolean;
};

export type ApiKeyRow = {
  id: number;
  name: string;
  key_prefix: string;
  created_at?: string | null;
  revoked_at?: string | null;
};

function accessToken(): string {
  return sessionStorage.getItem("access_token") || "";
}

export function setTokens(access: string, refresh: string): void {
  sessionStorage.setItem("access_token", access);
  sessionStorage.setItem("refresh_token", refresh);
}

export function clearTokens(): void {
  sessionStorage.removeItem("access_token");
  sessionStorage.removeItem("refresh_token");
}

export function isLoggedIn(): boolean {
  return Boolean(accessToken());
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  const token = accessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    throw new Error(`${response.status} ${await response.text()}`);
  }
  return (await response.json()) as T;
}

export function register(username: string, password: string): Promise<{
  access_token: string;
  refresh_token: string;
}> {
  return request("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function login(username: string, password: string): Promise<{
  access_token: string;
  refresh_token: string;
}> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function me(): Promise<UserMe> {
  return request<UserMe>("/auth/me");
}

export function listApiKeys(): Promise<ApiKeyRow[]> {
  return request<ApiKeyRow[]>("/auth/api-keys");
}

export function createApiKey(name: string): Promise<ApiKeyRow & { api_key: string }> {
  return request("/auth/api-keys", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function revokeApiKey(id: number): Promise<ApiKeyRow> {
  return request(`/auth/api-keys/${id}`, { method: "DELETE" });
}

export function listJobs(): Promise<Job[]> {
  return request<Job[]>("/api/jobs");
}

export function createJob(payload: {
  name: string;
  jd_text: string;
  score_threshold: number;
  greet_template: string;
}): Promise<Job> {
  return request<Job>("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
}

export function listCandidates(q: string): Promise<Candidate[]> {
  const query = q ? `?q=${encodeURIComponent(q)}` : "";
  return request<Candidate[]>(`/api/candidates${query}`);
}

export function markExchange(candidateId: number, operator: string): Promise<{ id: number }> {
  return request<{ id: number }>(`/api/candidates/${candidateId}/exchanges`, {
    method: "POST",
    body: JSON.stringify({ operator, type: "exchange" }),
  });
}

export async function uploadResume(file: File): Promise<unknown> {
  const form = new FormData();
  form.append("file", file);
  form.append("source", "upload");
  return request("/api/resumes/upload", { method: "POST", body: form });
}

export function listAgentRuns(): Promise<AgentRun[]> {
  return request<AgentRun[]>("/api/agent/runs");
}
