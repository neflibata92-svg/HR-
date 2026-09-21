export type Job = {
  id: number;
  name: string;
  jd_text: string;
  score_threshold: number;
  greet_template: string;
  boss_entry_url: string;
  hourly_greet_limit: number;
  min_action_delay_ms: number;
  max_action_delay_ms: number;
  enabled: boolean;
  created_at: string | null;
};

export type JobWrite = {
  name: string;
  jd_text: string;
  score_threshold: number;
  greet_template: string;
};

export type Candidate = {
  id: number;
  name: string;
  boss_id: string | null;
  fingerprint: string;
  age: number | null;
  years_of_experience: number | null;
  job_segments_json: string;
  source: string;
  created_at: string | null;
};

export type Resume = {
  id: number;
  candidate_id: number | null;
  file_path: string;
  parsed_text: string;
  source: string;
  parse_status: string;
  created_at: string | null;
};

export type AgentRun = {
  id: number;
  machine_id: string;
  status: string;
  last_error: string;
  last_heartbeat: string | null;
};

export type UserMe = {
  id: number;
  username: string;
  role: "admin" | "member";
  is_active: boolean;
  must_change_password: boolean;
};

export type UserRow = UserMe & {
  created_at: string | null;
};

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export type ApiKeyRow = {
  id: number;
  name: string;
  key_prefix: string;
  created_at?: string | null;
  revoked_at?: string | null;
};

export type ApiKeyCreated = ApiKeyRow & {
  api_key: string;
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
    if (response.status === 401 && token) {
      window.dispatchEvent(new Event("resume-screening:unauthorized"));
    }
    throw new Error(`${response.status} ${await response.text()}`);
  }
  return (await response.json()) as T;
}

export function register(username: string, password: string): Promise<TokenResponse> {
  return request("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function login(username: string, password: string): Promise<TokenResponse> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function me(): Promise<UserMe> {
  return request<UserMe>("/auth/me");
}

export function changePassword(currentPassword: string, newPassword: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export function listUsers(): Promise<UserRow[]> {
  return request<UserRow[]>("/auth/users");
}

export function createHr(username: string, temporaryPassword: string): Promise<UserRow> {
  return request<UserRow>("/auth/users", {
    method: "POST",
    body: JSON.stringify({ username, temporary_password: temporaryPassword }),
  });
}

export function setUserStatus(id: number, isActive: boolean): Promise<UserRow> {
  return request<UserRow>(`/auth/users/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive }),
  });
}

export function resetUserPassword(id: number, temporaryPassword: string): Promise<UserRow> {
  return request<UserRow>(`/auth/users/${id}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ temporary_password: temporaryPassword }),
  });
}

export function listApiKeys(): Promise<ApiKeyRow[]> {
  return request<ApiKeyRow[]>("/auth/api-keys");
}

export function createApiKey(name: string): Promise<ApiKeyCreated> {
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

export function createJob(payload: JobWrite): Promise<Job> {
  return request<Job>("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
}

export function updateJob(id: number, payload: Partial<JobWrite> & { enabled?: boolean }): Promise<Job> {
  return request<Job>(`/api/jobs/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
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

export async function uploadResume(file: File, candidateId?: number): Promise<Resume> {
  const form = new FormData();
  form.append("file", file);
  form.append("source", "upload");
  if (candidateId !== undefined) {
    form.append("candidate_id", String(candidateId));
  }
  return request<Resume>("/api/resumes/upload", { method: "POST", body: form });
}

export function listAgentRuns(): Promise<AgentRun[]> {
  return request<AgentRun[]>("/api/agent/runs");
}
