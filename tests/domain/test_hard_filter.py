from resume_domain.hard_filter import CandidateSnapshot, apply_hard_filter


def test_passes_when_all_rules_ok() -> None:
    snap = CandidateSnapshot(
        age=30,
        years_of_experience=4,
        job_segment_count=3,
        total_work_years=4.0,
    )
    result = apply_hard_filter(snap, exchanged_within_30_days=False)
    assert result.passed is True
    assert result.reasons == []


def test_rejects_age_over_38() -> None:
    snap = CandidateSnapshot(
        age=39,
        years_of_experience=4,
        job_segment_count=2,
        total_work_years=4.0,
    )
    result = apply_hard_filter(snap, exchanged_within_30_days=False)
    assert result.passed is False
    assert "age" in result.reasons


def test_rejects_years_outside_3_to_5() -> None:
    snap = CandidateSnapshot(
        age=30,
        years_of_experience=2,
        job_segment_count=1,
        total_work_years=2.0,
    )
    assert apply_hard_filter(snap, exchanged_within_30_days=False).passed is False


def test_rejects_avg_tenure_not_gt_1() -> None:
    snap = CandidateSnapshot(
        age=30,
        years_of_experience=4,
        job_segment_count=4,
        total_work_years=4.0,
    )
    result = apply_hard_filter(snap, exchanged_within_30_days=False)
    assert result.passed is False
    assert "avg_tenure" in result.reasons


def test_skips_when_segments_unknown() -> None:
    snap = CandidateSnapshot(
        age=30,
        years_of_experience=4,
        job_segment_count=None,
        total_work_years=4.0,
    )
    result = apply_hard_filter(snap, exchanged_within_30_days=False)
    assert result.passed is False
    assert "avg_tenure_unknown" in result.reasons


def test_rejects_recent_exchange() -> None:
    snap = CandidateSnapshot(
        age=30,
        years_of_experience=4,
        job_segment_count=2,
        total_work_years=4.0,
    )
    result = apply_hard_filter(snap, exchanged_within_30_days=True)
    assert result.passed is False
    assert "exchange_cooldown" in result.reasons
