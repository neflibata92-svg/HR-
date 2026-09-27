"""Pydantic schemas。"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ALLOWED_TEMPLATE_VARIABLES = {"candidate_name", "job_name"}
_TEMPLATE_VARIABLE_RE = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


def _validate_greet_template(value: str | None) -> str | None:
    if value is None:
        return value
    if value.count("{{") != value.count("}}"):
        raise ValueError("template variable is not closed")
    variables = set(_TEMPLATE_VARIABLE_RE.findall(value))
    if "{{" in _TEMPLATE_VARIABLE_RE.sub("", value) or "}}" in _TEMPLATE_VARIABLE_RE.sub("", value):
        raise ValueError("template variable is invalid")
    unknown = variables - _ALLOWED_TEMPLATE_VARIABLES
    if unknown:
        raise ValueError("template contains unsupported variables")
    return value


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    must_change_password: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AdminCreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=2, max_length=100)
    temporary_password: str = Field(min_length=8, max_length=128)
    role: Literal["member", "lead"] = "member"

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) < 2:
            raise ValueError("username must contain at least 2 characters")
        return normalized


class UserStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temporary_password: str = Field(min_length=8, max_length=128)


class ApiKeyCreateRequest(BaseModel):
    name: str = "default"


class ApiKeyCreatedOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    api_key: str
    created_at: datetime | None = None


class ApiKeyOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    created_at: datetime | None = None
    revoked_at: datetime | None = None

    model_config = {"from_attributes": True}


class CriticalFieldInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)


class JobReadinessOut(BaseModel):
    ready: bool
    missing: list[str]


class JobCreate(BaseModel):
    name: str
    jd_text: str
    score_threshold: int = Field(default=80, ge=0, le=100)
    greet_template: str = "您好，看了您的经历很匹配，方便发一下附件简历吗？"
    boss_entry_url: str = ""
    hourly_greet_limit: int = Field(default=20, ge=1)
    min_action_delay_ms: int = Field(default=1500, ge=0)
    max_action_delay_ms: int = Field(default=4000, ge=0)
    default_requested_count: int | None = Field(default=None, ge=1, le=50)
    critical_fields: list[CriticalFieldInput] = Field(default_factory=list)
    critical_fields_confirmed: bool = False
    enabled: bool = True

    _validate_template = field_validator("greet_template")(_validate_greet_template)


class JobUpdate(BaseModel):
    name: str | None = None
    jd_text: str | None = None
    score_threshold: int | None = Field(default=None, ge=0, le=100)
    greet_template: str | None = None
    boss_entry_url: str | None = None
    hourly_greet_limit: int | None = Field(default=None, ge=1)
    min_action_delay_ms: int | None = Field(default=None, ge=0)
    max_action_delay_ms: int | None = Field(default=None, ge=0)
    default_requested_count: int | None = Field(default=None, ge=1, le=50)
    critical_fields: list[CriticalFieldInput] | None = None
    critical_fields_confirmed: bool | None = None
    enabled: bool | None = None

    _validate_template = field_validator("greet_template")(_validate_greet_template)


class JobOut(BaseModel):
    id: int
    name: str
    jd_text: str
    score_threshold: int
    greet_template: str
    boss_entry_url: str
    hourly_greet_limit: int
    min_action_delay_ms: int
    max_action_delay_ms: int
    default_requested_count: int | None
    critical_fields: list[CriticalFieldInput]
    critical_fields_confirmed: bool
    readiness: JobReadinessOut
    enabled: bool
    created_at: datetime | None = None


class CandidateUpsert(BaseModel):
    boss_id: str | None = None
    fingerprint: str
    name: str = ""
    phone: str | None = None
    email: str | None = None
    age: int | None = None
    years_of_experience: float | None = None
    job_segments_json: str = "[]"
    source: str = "boss"


class CandidateOut(CandidateUpsert):
    id: int
    phone_normalized: str | None = None
    email_normalized: str | None = None
    merged_into_candidate_id: int | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class CandidateJobOut(BaseModel):
    id: int
    candidate_id: int
    job_id: int
    status: str
    active_resume_id: int | None = None
    latest_score_event_id: int | None = None
    review_reason_json: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ActiveResumeUpdate(BaseModel):
    resume_id: int


class CandidateMergeFieldChoices(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["source", "target"] = "target"
    phone_normalized: Literal["source", "target"] = "target"
    email_normalized: Literal["source", "target"] = "target"
    age: Literal["source", "target"] = "target"
    years_of_experience: Literal["source", "target"] = "target"
    source: Literal["source", "target"] = "target"


class CandidateMergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_candidate_id: int
    target_candidate_id: int
    field_choices: CandidateMergeFieldChoices = Field(
        default_factory=CandidateMergeFieldChoices
    )


class CandidateMergeSuggestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_candidate_id: int
    target_candidate_id: int
    reasons: list[str] = Field(default_factory=list)


class CandidateMergeSuggestionOut(BaseModel):
    id: int
    source_candidate_id: int
    target_candidate_id: int
    status: str

    model_config = {"from_attributes": True}


class CandidateMergeConflictOut(BaseModel):
    entity_type: str
    entity_id: int | None = None
    reason: str
    other_entity_id: int | None = None
    task_id: int | None = None
    job_id: int | None = None


class CandidateMergePreviewOut(BaseModel):
    source_candidate_id: int
    target_candidate_id: int
    merged_fields: dict[str, str | int | float | None]
    moved_counts: dict[str, int]
    conflicts: list[CandidateMergeConflictOut]


class CandidateMergeOut(BaseModel):
    id: int
    source_candidate_id: int
    target_candidate_id: int
    field_choices: CandidateMergeFieldChoices
    status: str
    performed_by_user_id: int
    performed_at: datetime | None = None


class CandidateMergeRevertOut(BaseModel):
    id: int
    status: str
    reverted: bool
    idempotent: bool
    conflicts: list[CandidateMergeConflictOut] = Field(default_factory=list)


class ExchangeCreate(BaseModel):
    operator: str
    type: str = Field(pattern="^(exchange|forward)$")


class ExchangeBlockedOut(BaseModel):
    blocked: bool


class CriticalFieldResultOut(CriticalFieldInput):
    present: bool
    evidence: str


class CriticalFieldSuggestionOut(CriticalFieldInput):
    reason: str


class CriticalFieldSuggestionResponse(BaseModel):
    suggestions: list[CriticalFieldSuggestionOut]
    model: str


class ScoreEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jd: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    critical_fields: list[CriticalFieldInput] = Field(default_factory=list)
    threshold: int = Field(default=80, ge=0, le=100)

    @field_validator("jd", "summary")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class ScoreEvaluateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100)
    reason: str
    evidence: list[str]
    missing_fields: list[str]
    estimated_fields: list[str]
    critical_fields: list[CriticalFieldResultOut]
    confidence: float = Field(ge=0, le=1)
    decision: Literal["eligible", "needs_review", "below_threshold", "error"]
    model: str


class ScoreEventCreate(BaseModel):
    candidate_id: int
    job_id: int
    candidate_job_id: int | None = None
    resume_id: int | None = None
    task_id: int | None = None
    hard_filter_passed: bool
    hard_filter_reasons: list[str] = Field(default_factory=list)
    score: int | None = Field(default=None, ge=0, le=100)
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    estimated_fields: list[str] = Field(default_factory=list)
    critical_fields: list[CriticalFieldResultOut] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    decision: Literal["eligible", "needs_review", "below_threshold", "error"] = "error"
    model: str = ""


class ScoreEventOut(BaseModel):
    id: int
    candidate_id: int
    job_id: int
    candidate_job_id: int | None
    resume_id: int | None
    task_id: int | None
    hard_filter_passed: bool
    hard_filter_reasons: list[str]
    score: int | None
    reason: str
    evidence: list[str]
    missing_fields: list[str]
    estimated_fields: list[str]
    critical_fields: list[CriticalFieldResultOut]
    confidence: float | None
    decision: str
    model: str
    created_at: datetime | None = None


class ReviewActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["keep_pending", "archive"]


class ReviewActionOut(BaseModel):
    candidate_job_id: int
    status: str


class ReviewCandidateOut(BaseModel):
    id: int
    name: str


class ReviewJobOut(BaseModel):
    id: int
    name: str


class ReviewItemOut(BaseModel):
    candidate_job_id: int
    candidate: ReviewCandidateOut
    job: ReviewJobOut
    score: int | None
    reason: str = ""
    threshold: int
    confidence: float | None
    missing_critical_fields: list[str]
    estimated_fields: list[str]
    evidence: list[str]
    model: str
    task_id: int | None
    scored_at: datetime | None


class ReEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume_id: int
    critical_fields: list[CriticalFieldInput] = Field(default_factory=list)


class OutreachCreate(BaseModel):
    candidate_id: int
    job_id: int
    greeted: bool = True
    attachment_received: bool = False


class OutreachOut(BaseModel):
    id: int
    candidate_id: int
    job_id: int
    greeted: bool
    attachment_received: bool
    status: str
    confirmed_at: datetime | None = None
    created_at: datetime | None = None
    idempotent_hit: bool = False

    model_config = {"from_attributes": True}


class ScreeningTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: int
    assigned_agent_run_id: int | None = None
    requested_count: int | None = Field(default=None, ge=1, le=50)
    critical_fields: list[CriticalFieldInput] | None = None
    critical_fields_source: dict[str, object] | None = None


class ScreeningTaskOut(BaseModel):
    id: int
    job_id: int
    created_by_user_id: int
    machine_id: str | None
    assigned_agent_run_id: int | None
    active_job_guard: int | None
    control_requested_at: datetime | None
    requested_count: int
    critical_fields: list[CriticalFieldInput]
    critical_fields_source: dict[str, object]
    job_name_snapshot: str
    jd_text_snapshot: str
    score_threshold_snapshot: int
    greet_template_snapshot: str
    boss_entry_url: str
    status: str
    pause_reason: str
    processed_count: int
    eligible_count: int
    contacted_count: int
    review_count: int
    skipped_count: int
    failed_count: int
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TaskClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    machine_id: str = Field(min_length=1, max_length=100)


class TaskCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    machine_id: str = Field(min_length=1, max_length=100)


class TaskPauseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1)


class TaskItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    machine_id: str = Field(min_length=1, max_length=100)
    candidate_id: int
    position_index: int = Field(ge=1)


class ScreeningRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    machine_id: str = Field(min_length=1, max_length=100)
    boss_id: str | None = Field(default=None, max_length=100)
    fingerprint: str = Field(min_length=1, max_length=64)
    display_name: str = Field(default="", max_length=100)
    source_payload: dict[str, object] = Field(default_factory=dict)
    position_index: int = Field(ge=1)


class ScreeningRecordComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    machine_id: str = Field(min_length=1, max_length=100)
    status: Literal[
        "needs_review", "below_threshold", "contacted", "duplicate_contact", "failed"
    ]
    score_snapshot: dict[str, object] = Field(default_factory=dict)
    outreach_event_id: int | None = None
    failure_code: str = Field(default="", max_length=100)
    failure_detail: str = ""


class ScreeningRecordOut(BaseModel):
    id: int
    task_id: int
    job_id: int
    boss_id: str | None
    fingerprint: str
    display_name: str
    source_payload: dict[str, object]
    position_index: int
    status: str
    candidate_id: int | None
    outreach_event_id: int | None
    score_snapshot: dict[str, object]
    idempotent_hit: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TaskItemComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    machine_id: str = Field(min_length=1, max_length=100)
    status: Literal[
        "needs_review", "below_threshold", "contacted", "duplicate_contact"
    ]
    score_event_id: int | None = None
    outreach_event_id: int | None = None


class TaskItemFail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    machine_id: str = Field(min_length=1, max_length=100)
    failure_code: str = Field(min_length=1, max_length=100)
    failure_detail: str = ""


class ScreeningTaskItemOut(BaseModel):
    id: int
    task_id: int
    candidate_id: int
    candidate_job_id: int
    job_id: int
    position_index: int
    status: str
    score_event_id: int | None
    outreach_event_id: int | None
    failure_code: str
    failure_detail: str
    idempotent_hit: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OutreachReservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: int | None = None
    screening_record_id: int | None = None
    job_id: int
    task_id: int | None = None
    message: str = Field(min_length=1)

    @field_validator("screening_record_id")
    @classmethod
    def require_one_subject(cls, value: int | None, info):
        if value is None and info.data.get("candidate_id") is None:
            raise ValueError("candidate_id or screening_record_id is required")
        return value


class OutreachFailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1)


class OutreachReservationOut(BaseModel):
    id: int
    candidate_id: int | None
    screening_record_id: int | None
    job_id: int
    task_id: int | None
    message_snapshot: str
    status: str
    failure_reason: str
    manual_override_by_user_id: int | None
    created_at: datetime | None = None
    confirmed_at: datetime | None = None

    model_config = {"from_attributes": True}


class OutreachOverrideCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: int
    job_id: int
    reason: str = Field(min_length=1)


class OutreachOverrideOut(BaseModel):
    id: int
    candidate_id: int
    job_id: int
    authorized_by_user_id: int
    reason: str
    status: str
    consumed_by_outreach_event_id: int | None
    created_at: datetime | None = None
    consumed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ResumeInboxJobOut(BaseModel):
    job_id: int
    job_name: str
    contact_event_id: int


class ResumeInboxCandidateOut(BaseModel):
    candidate_id: int
    candidate_name: str
    boss_id: str | None = None
    waiting_jobs: list[ResumeInboxJobOut]


class AgentResumeUploadOut(BaseModel):
    resume_id: int
    candidate_id: int
    assignment_status: Literal["assigned", "pending_job_assignment"]
    job_ids: list[int]
    idempotent_hit: bool = False


class ResumeJobAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: int


class ResumeBatchImportItemOut(BaseModel):
    original_filename: str
    status: Literal["imported", "duplicate", "failed"]
    resume_id: int | None = None
    error: str = ""


class ResumeBatchImportSummaryOut(BaseModel):
    imported: int = 0
    duplicate: int = 0
    failed: int = 0


class ResumeBatchImportOut(BaseModel):
    job_id: int
    summary: ResumeBatchImportSummaryOut
    items: list[ResumeBatchImportItemOut]


class ResumeOut(BaseModel):
    id: int
    candidate_id: int | None
    version_number: int | None
    original_filename: str
    file_path: str
    file_hash: str | None
    parsed_text: str
    source: str
    parse_status: str
    uploaded_by_user_id: int | None = None
    supersedes_resume_id: int | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentRunUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    machine_id: str = Field(min_length=1, max_length=100)
    status: str = "idle"
    availability: Literal["idle", "busy", "offline"] | None = None
    current_task_id: int | None = None
    current_job_id: int | None = None
    boss_login_status: Literal["unknown", "logged_in", "logged_out", "expired"] = "unknown"
    last_error: str = ""


class AgentRunOut(BaseModel):
    id: int
    machine_id: str
    owner_user_id: int | None
    status: str
    availability: str
    current_task_id: int | None
    current_job_id: int | None
    boss_login_status: str
    last_error: str
    last_heartbeat: datetime | None = None

    model_config = {"from_attributes": True}
