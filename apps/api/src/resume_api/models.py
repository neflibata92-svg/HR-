"""ORM 模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from resume_api.core.db import Base


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
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    boss_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    years_of_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    job_segments_json: Mapped[str] = mapped_column(Text, default="[]")
    source: Mapped[str] = mapped_column(String(50), default="boss")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    parsed_text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    parse_status: Mapped[str] = mapped_column(String(50), default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScoreEvent(Base):
    __tablename__ = "score_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False)
    hard_filter_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    hard_filter_reasons: Mapped[str] = mapped_column(Text, default="[]")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutreachEvent(Base):
    __tablename__ = "outreach_events"
    __table_args__ = (UniqueConstraint("candidate_id", "job_id", name="uq_outreach_candidate_job"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False)
    greeted: Mapped[bool] = mapped_column(Boolean, default=True)
    attachment_received: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExchangeEvent(Base):
    __tablename__ = "exchange_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    operator: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="idle")
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
