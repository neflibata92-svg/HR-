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
  default_requested_count?: number;
  critical_fields?: CriticalField[];
  critical_fields_confirmed?: boolean;
  readiness?: { ready: boolean; missing: string[] };
  enabled: boolean;
  created_at: string | null;
};

export type JobWrite = {
  name: string;
  jd_text: string;
  score_threshold: number;
  greet_template: string;
  boss_entry_url: string;
  hourly_greet_limit: number;
  min_action_delay_ms: number;
  max_action_delay_ms: number;
  default_requested_count: number | null;
  critical_fields: CriticalField[];
  critical_fields_confirmed: boolean;
};

export type Candidate = {
  id: number;
  name: string;
  boss_id: string | null;
  fingerprint: string;
  phone: string | null;
  email: string | null;
  phone_normalized: string | null;
  email_normalized: string | null;
  merged_into_candidate_id: number | null;
  age: number | null;
  years_of_experience: number | null;
  job_segments_json: string;
  source: string;
  created_at: string | null;
};

export type Resume = {
  id: number;
  candidate_id: number | null;
  version_number: number | null;
  original_filename: string;
  file_path: string;
  file_hash: string | null;
  parsed_text: string;
  source: string;
  parse_status: string;
  uploaded_by_user_id: number | null;
  supersedes_resume_id: number | null;
  created_at: string | null;
};

export type ResumeBatchImportItem = {
  original_filename: string;
  status: "imported" | "duplicate" | "failed";
  resume_id: number | null;
  error: string;
};

export type ResumeBatchImportResult = {
  job_id: number;
  summary: { imported: number; duplicate: number; failed: number };
  items: ResumeBatchImportItem[];
};

export type AgentRun = {
  id: number;
  machine_id: string;
  owner_user_id?: number | null;
  status: string;
  availability?: string;
  current_task_id?: number | null;
  current_job_id?: number | null;
  boss_login_status?: string;
  last_error: string;
  last_heartbeat: string | null;
};

export type UserMe = {
  id: number;
  username: string;
  role: "admin" | "lead" | "member";
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

export type CriticalField = {
  key: string;
  label: string;
};

export type CriticalFieldSuggestion = CriticalField & {
  reason: string;
};

export type CriticalFieldSuggestionResponse = {
  suggestions: CriticalFieldSuggestion[];
  model: string;
};

export type CandidateJob = {
  id: number;
  candidate_id: number;
  job_id: number;
  status: string;
  active_resume_id: number | null;
  latest_score_event_id: number | null;
  review_reason_json: string;
  created_at: string | null;
  updated_at: string | null;
};

export type ScoreEvent = {
  id: number;
  candidate_id: number;
  job_id: number;
  candidate_job_id: number | null;
  resume_id: number | null;
  task_id: number | null;
  hard_filter_passed: boolean;
  hard_filter_reasons: string[];
  score: number | null;
  reason: string;
  evidence: string[];
  missing_fields: string[];
  estimated_fields: string[];
  critical_fields: Array<CriticalField & { present: boolean; evidence: string }>;
  confidence: number | null;
  decision: string;
  model: string;
  created_at: string | null;
};

export type ScreeningTask = {
  id: number;
  job_id: number;
  created_by_user_id: number;
  machine_id: string | null;
  assigned_agent_run_id?: number | null;
  requested_count: number;
  critical_fields: CriticalField[];
  critical_fields_source: Record<string, unknown>;
  job_name_snapshot: string;
  jd_text_snapshot: string;
  score_threshold_snapshot: number;
  greet_template_snapshot: string;
  status: string;
  pause_reason: string;
  processed_count: number;
  eligible_count: number;
  contacted_count: number;
  review_count: number;
  skipped_count: number;
  failed_count: number;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type ScreeningTaskWrite = {
  job_id: number;
  assigned_agent_run_id: number;
  requested_count?: number;
  critical_fields?: CriticalField[];
  critical_fields_source?: Record<string, unknown>;
};

export type ReviewItem = {
  candidate_job_id: number;
  candidate: { id: number; name: string };
  job: { id: number; name: string };
  score: number | null;
  reason: string;
  threshold: number;
  confidence: number | null;
  missing_critical_fields: string[];
  estimated_fields: string[];
  evidence: string[];
  model: string;
  task_id: number | null;
  scored_at: string | null;
};

export type CandidateMergePayload = {
  source_candidate_id: number;
  target_candidate_id: number;
  field_choices: Record<string, "source" | "target">;
};

export type MergeConflict = {
  entity_type: string;
  entity_id?: number | null;
  reason: string;
  other_entity_id?: number | null;
  task_id?: number | null;
  job_id?: number | null;
};

export type CandidateMergePreview = {
  source_candidate_id: number;
  target_candidate_id: number;
  merged_fields: Record<string, string | number | null>;
  moved_counts: Record<string, number>;
  conflicts: MergeConflict[];
};

export type CandidateMerge = {
  id: number;
  source_candidate_id: number;
  target_candidate_id: number;
  field_choices: Record<string, "source" | "target">;
  status: string;
  performed_by_user_id: number;
  performed_at: string | null;
};

export type MergeRevertResult = {
  id: number;
  status: string;
  reverted: boolean;
  idempotent: boolean;
  conflicts: MergeConflict[];
};

export type AuditEvent = {
  id: number;
  actor_type: string;
  actor_user_id: number | null;
  actor_api_key_id: number | null;
  event_type: string;
  candidate_id: number | null;
  job_id: number | null;
  candidate_job_id: number | null;
  task_id: number | null;
  payload: Record<string, unknown>;
  created_at: string | null;
};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.name = "ApiError";
  }
}

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

async function fetchWithAuth(path: string, init: RequestInit = {}): Promise<Response> {
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
    const raw = await response.text();
    let detail: unknown = raw;
    try {
      const parsed = JSON.parse(raw) as { detail?: unknown };
      detail = parsed.detail ?? parsed;
    } catch {
      // 非 JSON 错误保持原始文本，便于定位代理或网关问题。
    }
    throw new ApiError(response.status, detail);
  }
  return response;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetchWithAuth(path, init);
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

export function createHr(
  username: string,
  temporaryPassword: string,
  role: "member" | "lead" = "member",
): Promise<UserRow> {
  return request<UserRow>("/auth/users", {
    method: "POST",
    body: JSON.stringify({ username, temporary_password: temporaryPassword, role }),
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

export function listCandidates(
  q = "",
  filters: { jobId?: number; status?: string; minScore?: number; needsReview?: boolean } = {},
): Promise<Candidate[]> {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (filters.jobId !== undefined) params.set("job_id", String(filters.jobId));
  if (filters.status) params.set("status", filters.status);
  if (filters.minScore !== undefined) params.set("min_score", String(filters.minScore));
  if (filters.needsReview !== undefined) params.set("needs_review", String(filters.needsReview));
  const query = params.toString();
  return request<Candidate[]>(`/api/candidates${query ? `?${query}` : ""}`);
}

export function markExchange(candidateId: number, operator: string): Promise<{ id: number }> {
  return request<{ id: number }>(`/api/candidates/${candidateId}/exchanges`, {
    method: "POST",
    body: JSON.stringify({ operator, type: "exchange" }),
  });
}

export function batchImportResumes(files: File[], jobId: number): Promise<ResumeBatchImportResult> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  form.append("job_id", String(jobId));
  return request<ResumeBatchImportResult>("/api/resumes/batch-import", { method: "POST", body: form });
}

export async function downloadResumeFile(resumeId: number): Promise<Blob> {
  const response = await fetchWithAuth(`/api/resumes/${resumeId}/file`);
  return response.blob();
}

export async function uploadResume(file: File, candidateId: number, jobId?: number): Promise<Resume> {
  const form = new FormData();
  form.append("file", file);
  form.append("source", "upload");
  form.append("candidate_id", String(candidateId));
  if (jobId !== undefined) form.append("job_id", String(jobId));
  return request<Resume>("/api/resumes/upload", { method: "POST", body: form });
}

export function listResumes(filters: { candidateId?: number; jobId?: number } = {}): Promise<Resume[]> {
  const params = new URLSearchParams();
  if (filters.candidateId !== undefined) params.set("candidate_id", String(filters.candidateId));
  if (filters.jobId !== undefined) params.set("job_id", String(filters.jobId));
  const query = params.toString();
  return request<Resume[]>(`/api/resumes${query ? `?${query}` : ""}`);
}

export function listAgentRuns(): Promise<AgentRun[]> {
  return request<AgentRun[]>("/api/agent/runs");
}

export function suggestCriticalFields(jobId: number): Promise<CriticalFieldSuggestionResponse> {
  return request<CriticalFieldSuggestionResponse>(`/api/jobs/${jobId}/critical-fields/suggest`, {
    method: "POST",
  });
}

export function listScreeningTasks(jobId?: number): Promise<ScreeningTask[]> {
  const query = jobId === undefined ? "" : `?job_id=${jobId}`;
  return request<ScreeningTask[]>(`/api/screening-tasks${query}`);
}

export function createScreeningTask(payload: ScreeningTaskWrite): Promise<ScreeningTask> {
  return request<ScreeningTask>("/api/screening-tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getScreeningTask(id: number): Promise<ScreeningTask> {
  return request<ScreeningTask>(`/api/screening-tasks/${id}`);
}

export function pauseScreeningTask(id: number, reason: string): Promise<ScreeningTask> {
  return request<ScreeningTask>(`/api/screening-tasks/${id}/pause`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function resumeScreeningTask(id: number): Promise<ScreeningTask> {
  return request<ScreeningTask>(`/api/screening-tasks/${id}/resume`, { method: "POST" });
}

export function cancelScreeningTask(id: number): Promise<ScreeningTask> {
  return request<ScreeningTask>(`/api/screening-tasks/${id}/cancel`, { method: "POST" });
}

export function listCandidateJobs(candidateId: number): Promise<CandidateJob[]> {
  return request<CandidateJob[]>(`/api/candidates/${candidateId}/jobs`);
}

export function getCandidateJob(id: number): Promise<CandidateJob> {
  return request<CandidateJob>(`/api/candidate-jobs/${id}`);
}

export function listCandidateResumes(candidateId: number): Promise<Resume[]> {
  return request<Resume[]>(`/api/candidates/${candidateId}/resumes`);
}

export function setActiveResume(
  candidateId: number,
  jobId: number,
  resumeId: number,
): Promise<CandidateJob> {
  return request<CandidateJob>(`/api/candidates/${candidateId}/jobs/${jobId}/active-resume`, {
    method: "PATCH",
    body: JSON.stringify({ resume_id: resumeId }),
  });
}

export function reEvaluateCandidateJob(
  candidateId: number,
  jobId: number,
  resumeId: number,
): Promise<ScoreEvent> {
  return request<ScoreEvent>(`/api/candidates/${candidateId}/jobs/${jobId}/re-evaluate`, {
    method: "POST",
    body: JSON.stringify({ resume_id: resumeId }),
  });
}

export function listReviews(jobId?: number): Promise<ReviewItem[]> {
  const query = jobId === undefined ? "" : `?job_id=${jobId}`;
  return request<ReviewItem[]>(`/api/reviews${query}`);
}

export function reviewCandidateJob(
  candidateJobId: number,
  action: "keep_pending" | "archive",
): Promise<{ candidate_job_id: number; status: string }> {
  return request(`/api/reviews/${candidateJobId}`, {
    method: "PATCH",
    body: JSON.stringify({ action }),
  });
}

export function previewCandidateMerge(payload: CandidateMergePayload): Promise<CandidateMergePreview> {
  return request<CandidateMergePreview>("/api/candidate-merges/preview", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function mergeCandidates(payload: CandidateMergePayload): Promise<CandidateMerge> {
  return request<CandidateMerge>("/api/candidate-merges", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function revertCandidateMerge(id: number): Promise<MergeRevertResult> {
  return request<MergeRevertResult>(`/api/candidate-merges/${id}/revert`, { method: "POST" });
}
