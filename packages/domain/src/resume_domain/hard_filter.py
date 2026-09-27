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
    """硬筛结果：reasons 仅保存明确拒绝项，unknown_fields 保存资料缺失项。"""

    passed: bool
    reasons: list[str]
    unknown_fields: list[str]


def apply_hard_filter(
    snap: CandidateSnapshot,
    *,
    exchanged_within_30_days: bool,
) -> HardFilterResult:
    """按年龄/年限/平均在职/交换冷却做硬筛；未知字段不直接拒绝。"""

    reasons: list[str] = []
    unknown_fields: list[str] = []

    if snap.age is None:
        unknown_fields.append("age")
    elif snap.age > 38:
        reasons.append("age")

    if snap.years_of_experience is None:
        unknown_fields.append("years_of_experience")
    elif not (3 <= snap.years_of_experience <= 5):
        reasons.append("years")

    if (
        snap.job_segment_count is None
        or snap.total_work_years is None
        or snap.job_segment_count <= 0
    ):
        unknown_fields.append("avg_tenure")
    else:
        avg = snap.total_work_years / snap.job_segment_count
        if not (avg > 1.0):
            reasons.append("avg_tenure")

    if exchanged_within_30_days:
        reasons.append("exchange_cooldown")

    return HardFilterResult(
        passed=len(reasons) == 0,
        reasons=reasons,
        unknown_fields=unknown_fields,
    )
