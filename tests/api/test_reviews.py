from __future__ import annotations

import json
from unittest.mock import ANY, patch

from resume_api.core import db as db_mod
from resume_api.models import (
    AuditEvent,
    Candidate,
    CandidateJob,
    JobPosting,
    OutreachEvent,
    Resume,
    ScoreEvent,
)
from resume_domain.llm_schema import CriticalFieldResult, LlmScoreResult


def _fixture(client, headers, *, fingerprint: str, job_name: str, score: int = 90):
    candidate = client.post(
        "/api/candidates",
        headers=headers,
        json={"fingerprint": fingerprint, "name": f"候选人-{fingerprint}"},
    ).json()
    job = client.post(
        "/api/jobs",
        headers=headers,
        json={"name": job_name, "jd_text": "Python FastAPI", "score_threshold": 80},
    ).json()
    db = db_mod.SessionLocal()
    try:
        resume = Resume(
            candidate_id=candidate["id"],
            version_number=1,
            original_filename="resume.txt",
            file_path=f"/tmp/{fingerprint}.txt",
            file_hash=f"hash-{fingerprint}",
            parsed_text="Python FastAPI 项目经验",
            source="upload",
        )
        db.add(resume)
        db.flush()
        link = CandidateJob(
            candidate_id=candidate["id"],
            job_id=job["id"],
            status="needs_review",
            active_resume_id=resume.id,
            review_reason_json='["degree"]',
        )
        db.add(link)
        db.flush()
        event = ScoreEvent(
            candidate_id=candidate["id"],
            job_id=job["id"],
            candidate_job_id=link.id,
            resume_id=resume.id,
            hard_filter_passed=True,
            score=score,
            reason="经验匹配",
            evidence_json='["Python"]',
            missing_fields_json='["degree"]',
            estimated_fields_json='["team_size"]',
            critical_fields_json='[{"key":"degree","label":"学历","present":false,"evidence":""}]',
            confidence=0.7,
            decision="needs_review",
            model="old-model",
        )
        db.add(event)
        db.flush()
        link.latest_score_event_id = event.id
        db.commit()
        return candidate, job, resume.id, link.id, event.id
    finally:
        db.close()


def test_reviews_are_job_scoped_and_use_latest_score(client, auth_headers) -> None:
    first = _fixture(client, auth_headers, fingerprint="review-a", job_name="后端")
    _fixture(client, auth_headers, fingerprint="review-b", job_name="前端", score=81)

    response = client.get(
        "/api/reviews", headers=auth_headers, params={"job_id": first[1]["id"]}
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    item = response.json()[0]
    assert item["candidate_job_id"] == first[3]
    assert item["candidate"]["id"] == first[0]["id"]
    assert item["job"]["id"] == first[1]["id"]
    assert item["score"] == 90
    assert item["reason"] == "经验匹配"
    assert item["threshold"] == 80
    assert item["confidence"] == 0.7
    assert item["missing_critical_fields"] == ["degree"]
    assert item["estimated_fields"] == ["team_size"]
    assert item["evidence"] == ["Python"]
    assert item["model"] == "old-model"


def test_review_keep_pending_and_archive_are_audited(client, auth_headers) -> None:
    candidate, job, _resume_id, link_id, _event_id = _fixture(
        client, auth_headers, fingerprint="review-actions", job_name="数据"
    )
    kept = client.patch(
        f"/api/reviews/{link_id}", headers=auth_headers, json={"action": "keep_pending"}
    )
    archived = client.patch(
        f"/api/reviews/{link_id}", headers=auth_headers, json={"action": "archive"}
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["status"] == "needs_review"
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"
    invalid = client.patch(
        f"/api/reviews/{link_id}", headers=auth_headers, json={"action": "keep_pending"}
    )
    assert invalid.status_code == 409

    db = db_mod.SessionLocal()
    try:
        actions = [row.action for row in db.query(AuditEvent).order_by(AuditEvent.id).all()]
        assert "candidate_job.review_kept_pending" in actions
        assert "candidate_job.review_archived" in actions
        assert db.query(ScoreEvent).count() == 1
    finally:
        db.close()


def test_manual_re_evaluate_appends_history_without_contacting(client, auth_headers) -> None:
    candidate, job, resume_id, link_id, old_event_id = _fixture(
        client, auth_headers, fingerprint="reevaluate", job_name="平台"
    )
    result = LlmScoreResult(
        score=92,
        reason="资料完整",
        evidence=["Python", "FastAPI"],
        missing_fields=[],
        estimated_fields=[],
        critical_fields=[],
        confidence=0.95,
        decision="eligible",
        model="provider-model",
    )
    with patch("resume_api.services.reviews.llm_service.score_candidate", return_value=result) as score:
        response = client.post(
            f"/api/candidates/{candidate['id']}/jobs/{job['id']}/re-evaluate",
            headers=auth_headers,
            json={"resume_id": resume_id},
        )
    score.assert_called_once_with(
        ANY,
        "Python FastAPI",
        "Python FastAPI 项目经验",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] != old_event_id
    assert body["decision"] == "eligible"
    assert body["evidence"] == ["Python", "FastAPI"]

    db = db_mod.SessionLocal()
    try:
        events = db.query(ScoreEvent).order_by(ScoreEvent.id).all()
        assert len(events) == 2
        assert events[0].id == old_event_id
        assert events[0].model == "old-model"
        link = db.get(CandidateJob, link_id)
        assert link.latest_score_event_id == events[1].id
        assert link.active_resume_id == resume_id
        assert link.status == "scored"
        assert json.loads(link.review_reason_json) == []
        assert db.query(OutreachEvent).count() == 0
        audit = db.query(AuditEvent).filter_by(action="candidate_job.re_evaluated").one()
        assert audit.entity_id == str(link_id)
    finally:
        db.close()


def test_re_evaluate_decision_only_uses_jd_score_threshold(client, auth_headers) -> None:
    candidate, job, resume_id, link_id, _ = _fixture(
        client, auth_headers, fingerprint="legacy-critical", job_name="算法"
    )
    result = LlmScoreResult(
        score=95,
        reason="能力匹配",
        evidence=["算法项目"],
        missing_fields=["degree"],
        estimated_fields=[],
        critical_fields=[],
        confidence=0.8,
        decision="eligible",
        model="provider-model",
    )
    with patch("resume_api.services.reviews.llm_service.score_candidate", return_value=result):
        response = client.post(
            f"/api/candidates/{candidate['id']}/jobs/{job['id']}/re-evaluate",
            headers=auth_headers,
            json={"resume_id": resume_id},
        )
    assert response.status_code == 201, response.text
    assert response.json()["decision"] == "eligible"
    db = db_mod.SessionLocal()
    try:
        link = db.get(CandidateJob, link_id)
        assert link.status == "scored"
        assert json.loads(link.review_reason_json) == []
    finally:
        db.close()


def test_re_evaluate_rejects_resume_owned_by_another_candidate(client, auth_headers) -> None:
    first = _fixture(client, auth_headers, fingerprint="owner-a", job_name="安全")
    second = _fixture(client, auth_headers, fingerprint="owner-b", job_name="运维")
    response = client.post(
        f"/api/candidates/{first[0]['id']}/jobs/{first[1]['id']}/re-evaluate",
        headers=auth_headers,
        json={"resume_id": second[2], "critical_fields": []},
    )
    assert response.status_code == 422
