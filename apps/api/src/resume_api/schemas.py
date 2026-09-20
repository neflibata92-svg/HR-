"""Pydantic schemas。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class JobCreate(BaseModel):
    name: str
    jd_text: str
    score_threshold: int = 80
    greet_template: str = "您好，看了您的经历很匹配，方便发一下附件简历吗？"
    boss_entry_url: str = ""
    hourly_greet_limit: int = 20
    min_action_delay_ms: int = 1500
    max_action_delay_ms: int = 4000
    enabled: bool = True


class JobUpdate(BaseModel):
    name: str | None = None
    jd_text: str | None = None
    score_threshold: int | None = None
    greet_template: str | None = None
    boss_entry_url: str | None = None
    hourly_greet_limit: int | None = None
    min_action_delay_ms: int | None = None
    max_action_delay_ms: int | None = None
    enabled: bool | None = None


class JobOut(JobCreate):
    id: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class CandidateUpsert(BaseModel):
    boss_id: str | None = None
    fingerprint: str
    name: str = ""
    age: int | None = None
    years_of_experience: float | None = None
    job_segments_json: str = "[]"
    source: str = "boss"


class CandidateOut(CandidateUpsert):
    id: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ExchangeCreate(BaseModel):
    operator: str
    type: str = Field(pattern="^(exchange|forward)$")


class ExchangeBlockedOut(BaseModel):
    blocked: bool


class ScoreEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jd: str = Field(min_length=1)
    summary: str = Field(min_length=1)

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
    model: str


class ScoreEventCreate(BaseModel):
    candidate_id: int
    job_id: int
    hard_filter_passed: bool
    hard_filter_reasons: list[str] = Field(default_factory=list)
    score: int | None = None
    reason: str = ""
    model: str = ""


class ScoreEventOut(BaseModel):
    id: int
    candidate_id: int
    job_id: int
    hard_filter_passed: bool
    hard_filter_reasons: str
    score: int | None
    reason: str
    model: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


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
    created_at: datetime | None = None
    idempotent_hit: bool = False

    model_config = {"from_attributes": True}


class ResumeOut(BaseModel):
    id: int
    candidate_id: int | None
    file_path: str
    parsed_text: str
    source: str
    parse_status: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentRunUpsert(BaseModel):
    machine_id: str
    status: str = "idle"
    last_error: str = ""


class AgentRunOut(BaseModel):
    id: int
    machine_id: str
    status: str
    last_error: str
    last_heartbeat: datetime | None = None

    model_config = {"from_attributes": True}
