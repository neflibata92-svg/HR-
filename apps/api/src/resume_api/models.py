"""ORM 模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from resume_api.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), default="default")
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobPosting(Base):
    __tablename__ = "job_postings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    score_threshold: Mapped[int] = mapped_column(Integer, default=80)
    greet_template: Mapped[str] = mapped_column(Text, default="您好，看了您的经历很匹配，方便发一下附件简历吗？")
    boss_entry_url: Mapped[str] = mapped_column(String(500), default="")
    hourly_greet_limit: Mapped[int] = mapped_column(Integer, default=20)
    min_action_delay_ms: Mapped[int] = mapped_column(Integer, default=1500)
    max_action_delay_ms: Mapped[int] = mapped_column(Integer, default=4000)
    default_requested_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    critical_fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    critical_fields_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    boss_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    phone_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    email_normalized: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    years_of_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    job_segments_json: Mapped[str] = mapped_column(Text, default="[]")
    source: Mapped[str] = mapped_column(String(50), default="boss")
    merged_into_candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidates.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CandidateJob(Base):
    __tablename__ = "candidate_jobs"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_candidate_job"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="discovered")
    active_resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id"), nullable=True)
    latest_score_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("score_events.id"), nullable=True
    )
    review_reason_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (
        CheckConstraint(
            "candidate_id IS NULL OR version_number IS NOT NULL",
            name="ck_resume_claimed_has_version",
        ),
        UniqueConstraint("candidate_id", "version_number", name="uq_resume_candidate_version"),
        UniqueConstraint("candidate_id", "file_hash", name="uq_resume_candidate_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id"), nullable=True, index=True)
    version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_filename: Mapped[str] = mapped_column(String(500), default="")
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parsed_text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    parse_status: Mapped[str] = mapped_column(String(50), default="ok")
    assignment_status: Mapped[str] = mapped_column(String(50), nullable=False, default="assigned")
    contact_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("outreach_events.id"), nullable=True, index=True
    )
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    supersedes_resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResumeJobArchive(Base):
    __tablename__ = "resume_job_archives"
    __table_args__ = (
        UniqueConstraint("resume_id", "job_id", name="uq_resume_job_archive"),
        UniqueConstraint("job_id", "file_hash", name="uq_resume_job_file_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScoreEvent(Base):
    __tablename__ = "score_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False)
    candidate_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_jobs.id"), nullable=True, index=True
    )
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id"), nullable=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("screening_tasks.id"), nullable=True)
    hard_filter_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    hard_filter_reasons: Mapped[str] = mapped_column(Text, default="[]")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    missing_fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    estimated_fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    critical_fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision: Mapped[str] = mapped_column(String(30), nullable=False, default="error")
    model: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutreachEvent(Base):
    __tablename__ = "outreach_events"
    __table_args__ = (Index("ix_outreach_candidate_status", "candidate_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)
    screening_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("screening_records.id"), nullable=True, index=True
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("screening_tasks.id"), nullable=True)
    message_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="confirmed")
    failure_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    manual_override_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    greeted: Mapped[bool] = mapped_column(Boolean, default=True)
    attachment_received: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScreeningTask(Base):
    __tablename__ = "screening_tasks"
    __table_args__ = (
        CheckConstraint(
            "requested_count >= 1 AND requested_count <= 50",
            name="ck_screening_task_requested_count",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False, index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    machine_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assigned_agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=True, index=True
    )
    active_job_guard: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    control_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    requested_count: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    critical_fields_source_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    job_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    jd_text_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    score_threshold_snapshot: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    greet_template_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    boss_entry_url_snapshot: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    pause_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    eligible_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contacted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScreeningRecord(Base):
    __tablename__ = "screening_records"
    __table_args__ = (
        UniqueConstraint("task_id", "identity_key", name="uq_screening_record_task_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("screening_tasks.id"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False, index=True)
    boss_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    identity_key: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    source_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="discovered")
    score_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)
    outreach_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("outreach_events.id"), nullable=True
    )
    position_index: Mapped[int] = mapped_column(Integer, nullable=False)
    migration_review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ScreeningTaskItem(Base):
    __tablename__ = "screening_task_items"
    __table_args__ = (
        UniqueConstraint("task_id", "candidate_id", name="uq_task_candidate"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("screening_tasks.id"), nullable=False, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    candidate_job_id: Mapped[int] = mapped_column(ForeignKey("candidate_jobs.id"), nullable=False)
    position_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="discovered")
    score_event_id: Mapped[int | None] = mapped_column(ForeignKey("score_events.id"), nullable=True)
    outreach_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("outreach_events.id"), nullable=True
    )
    failure_code: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    failure_detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CandidateMerge(Base):
    __tablename__ = "candidate_merges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    target_candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    field_choices_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    performed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reverted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")


class CandidateMergeSuggestion(Base):
    __tablename__ = "candidate_merge_suggestions"
    __table_args__ = (
        UniqueConstraint(
            "source_candidate_id",
            "target_candidate_id",
            name="uq_merge_suggestion_pair",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    target_candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    suggested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    match_reason_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutreachOverride(Base):
    __tablename__ = "outreach_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False)
    authorized_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="available")
    consumed_by_outreach_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("outreach_events.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExchangeEvent(Base):
    __tablename__ = "exchange_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    operator: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="idle")
    availability: Mapped[str] = mapped_column(String(20), nullable=False, default="idle")
    current_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("screening_tasks.id"), nullable=True
    )
    current_job_id: Mapped[int | None] = mapped_column(ForeignKey("job_postings.id"), nullable=True)
    boss_login_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
