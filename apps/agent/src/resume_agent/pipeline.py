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
    def score_candidate(self, jd: str, summary: str) -> LlmScoreResult: ...


class Greeter(Protocol):
    def greet(self, candidate: RawCandidate, message: str) -> bool: ...


@dataclass(frozen=True)
class ProcessResult:
    action: str
    reasons: list[str]
    score: int | None = None


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
        scored = scorer.score_candidate(jd_text, summary)
    except Exception as exc:  # noqa: BLE001 - 流水线需降级
        return ProcessResult(action="score_error", reasons=[str(exc)])

    if not should_greet(scored.score, threshold):
        return ProcessResult(
            action="below_threshold",
            reasons=[scored.reason],
            score=scored.score,
        )

    if greeter is not None:
        greeter.greet(candidate, greet_template)
    return ProcessResult(action="greeted", reasons=[scored.reason], score=scored.score)
