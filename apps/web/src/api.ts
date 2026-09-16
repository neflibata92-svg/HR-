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

function token(): string {
  return localStorage.getItem("api_token") || "";
}

export function setToken(value: string): void {
  localStorage.setItem("api_token", value);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  headers.set("X-Api-Token", token());
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    throw new Error(`${response.status} ${await response.text()}`);
  }
  return (await response.json()) as T;
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
