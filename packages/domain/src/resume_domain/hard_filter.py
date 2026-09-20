"""硬性筛选规则。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateSnapshot:
    """候选人用于硬筛的结构化快照。"""

    age: int | None
    years_of_experience: float | None
    job_segment_count: int | None
    total_work_years: float | None


@dataclass(frozen=True)
class HardFilterResult:
    """硬筛结果。"""

    passed: bool
    reasons: list[str]


def apply_hard_filter(
    snap: CandidateSnapshot,
    *,
    exchanged_within_30_days: bool,
) -> HardFilterResult:
    """按年龄/年限/平均在职/交换冷却做硬筛；不确定字段记入 reasons 并判失败。"""

    reasons: list[str] = []

    if snap.age is None:
        reasons.append("age_unknown")
    elif snap.age > 38:
        reasons.append("age")

    if snap.years_of_experience is None:
        reasons.append("years_unknown")
    elif not (3 <= snap.years_of_experience <= 5):
        reasons.append("years")

    if snap.job_segment_count is None or snap.total_work_years is None:
        reasons.append("avg_tenure_unknown")
    elif snap.job_segment_count <= 0:
        reasons.append("avg_tenure_unknown")
    else:
        avg = snap.total_work_years / snap.job_segment_count
        if not (avg > 1.0):
            reasons.append("avg_tenure")

    if exchanged_within_30_days:
        reasons.append("exchange_cooldown")

    return HardFilterResult(passed=len(reasons) == 0, reasons=reasons)
