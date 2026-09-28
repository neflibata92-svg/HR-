"""候选人处理流水线（可注入 mock）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from resume_domain.decision import should_greet
from resume_domain.fingerprint import candidate_fingerprint
from resume_domain.hard_filter import CandidateSnapshot, apply_hard_filter
from resume_domain.llm_schema import LlmScoreResult
from resume_agent.parse_page import RawCandidate


class Scorer(Protocol):
    def score_candidate(
        self,
        jd: str,
        summary: str,
        *,
        threshold: int,
    ) -> LlmScoreResult: ...


class Greeter(Protocol):
    def greet(self, candidate: RawCandidate, message: str) -> bool | None: ...


class SendOutcomeUnknown(RuntimeError):
    """发送动作已触发，但无法确认平台是否接受。"""


@dataclass(frozen=True)
class ProcessResult:
    action: str
    reasons: list[str]
    score: int | None = None
    model: str = ""
    evidence: list[str] | None = None
    missing_fields: list[str] | None = None
    estimated_fields: list[str] | None = None
    critical_fields: list[dict[str, object]] | None = None
    confidence: float | None = None


def process_candidate(
    candidate: RawCandidate,
    *,
    jd_text: str,
    threshold: int,
    greet_template: str,
    exchanged_within_30_days: bool,
    already_greeted: bool,
    scorer: Scorer,
    greeter: Greeter | None = None,
) -> ProcessResult:
    """硬筛 → LLM → 达阈值打招呼。"""

    if already_greeted:
        return ProcessResult(action="skip_already_greeted", reasons=["idempotent"])

    snap = CandidateSnapshot(
        age=candidate.age,
        years_of_experience=candidate.years,
        job_segment_count=candidate.segments,
        total_work_years=candidate.total_years,
    )
    hard = apply_hard_filter(snap, exchanged_within_30_days=exchanged_within_30_days)
    if not hard.passed:
        return ProcessResult(action="hard_filter_reject", reasons=hard.reasons)

    summary = (
        f"姓名={candidate.name}; 公司={candidate.org}; 年龄={candidate.age}; "
        f"年限={candidate.years}; 段数={candidate.segments}; fingerprint="
        f"{candidate_fingerprint(candidate.name, candidate.org)}"
    )
    try:
        scored = scorer.score_candidate(
            jd_text,
            summary,
            threshold=threshold,
        )
    except Exception as exc:  # noqa: BLE001 - 流水线需降级
        return ProcessResult(action="score_error", reasons=[str(exc)])

    details = {
        "score": scored.score,
        "model": scored.model,
        "evidence": scored.evidence,
        "missing_fields": scored.missing_fields,
        "estimated_fields": scored.estimated_fields,
        "critical_fields": [item.model_dump() for item in scored.critical_fields],
        "confidence": scored.confidence,
    }
    if scored.decision != "eligible":
        return ProcessResult(
            action=scored.decision,
            reasons=[scored.reason],
            **details,
        )

    if not should_greet(scored.score, threshold):
        return ProcessResult(
            action="below_threshold",
            reasons=[scored.reason],
            **details,
        )

    if greeter is None:
        return ProcessResult(
            action="eligible",
            reasons=["eligible_not_sent"],
            **details,
        )
    if not greeter.greet(candidate, greet_template):
        return ProcessResult(
            action="greet_failed",
            reasons=["message_not_verified"],
            **details,
        )
    return ProcessResult(
        action="greeted",
        reasons=[scored.reason],
        **details,
    )
