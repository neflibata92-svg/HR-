from __future__ import annotations

from resume_api.core import db as db_mod
from resume_api.models import (
    AuditEvent,
    Candidate,
    CandidateJob,
    OutreachEvent,
    Resume,
    ScoreEvent,
)


def _create_candidate(client, headers, fingerprint: str, name: str = "候选人") -> dict:
    response = client.post(
        "/api/candidates",
        headers=headers,
        json={"fingerprint": fingerprint, "name": name},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_job(client, headers, name: str) -> dict:
    response = client.post(
        "/api/jobs",
        headers=headers,
        json={"name": name, "jd_text": f"{name} JD"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_job_link_can_be_created_idempotently_through_api(client, auth_headers) -> None:
    candidate = _create_candidate(client, auth_headers, "api-link")
    job = _create_job(client, auth_headers, "算法")

    first = client.post(
        f"/api/candidates/{candidate['id']}/jobs/{job['id']}", headers=auth_headers
    )
    second = client.post(
        f"/api/candidates/{candidate['id']}/jobs/{job['id']}", headers=auth_headers
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "discovered"



def test_merged_source_job_routes_resolve_to_target(client, auth_headers) -> None:
    source = _create_candidate(client, auth_headers, "job-source")
    target = _create_candidate(client, auth_headers, "job-target")
    job = _create_job(client, auth_headers, "测试")
    link = client.post(
        f"/api/candidates/{target['id']}/jobs/{job['id']}", headers=auth_headers
    ).json()
    db = db_mod.SessionLocal()
    try:
        resume = Resume(
            candidate_id=target["id"], version_number=1, original_filename="target.txt",
            file_path="/tmp/target.txt", file_hash="target-hash", source="upload",
        )
        db.add(resume)
        db.flush()
        resume_id = resume.id
        db.get(Candidate, source["id"]).merged_into_candidate_id = target["id"]
        db.commit()
    finally:
        db.close()

    listed = client.get(
        f"/api/candidates/{source['id']}/jobs", headers=auth_headers
    )
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [link["id"]]

    changed = client.patch(
        f"/api/candidates/{source['id']}/jobs/{job['id']}/active-resume",
        headers=auth_headers,
        json={"resume_id": resume_id},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["active_resume_id"] == resume_id



def test_candidate_jobs_keep_status_and_active_resume_isolated(client, auth_headers) -> None:
    candidate = _create_candidate(client, auth_headers, "multi-job")
    first_job = _create_job(client, auth_headers, "后端")
    second_job = _create_job(client, auth_headers, "前端")
    db = db_mod.SessionLocal()
    try:
        first_resume = Resume(
            candidate_id=candidate["id"], version_number=1, original_filename="one.txt",
            file_path="/tmp/one.txt", file_hash="hash-one", source="upload",
        )
        second_resume = Resume(
            candidate_id=candidate["id"], version_number=2, original_filename="two.txt",
            file_path="/tmp/two.txt", file_hash="hash-two", source="upload",
        )
        db.add_all([first_resume, second_resume])
        db.flush()
        first_resume_id = first_resume.id
        second_resume_id = second_resume.id
        db.add_all([
            CandidateJob(
                candidate_id=candidate["id"], job_id=first_job["id"],
                status="scored", active_resume_id=first_resume_id,
            ),
            CandidateJob(
                candidate_id=candidate["id"], job_id=second_job["id"],
                status="needs_review", active_resume_id=second_resume_id,
                review_reason_json='["missing_portfolio"]',
            ),
        ])
        db.commit()
    finally:
        db.close()

    jobs = client.get(
        f"/api/candidates/{candidate['id']}/jobs", headers=auth_headers
    )
    assert jobs.status_code == 200, jobs.text
    by_job = {item["job_id"]: item for item in jobs.json()}
    assert by_job[first_job["id"]]["status"] == "scored"
    assert by_job[second_job["id"]]["status"] == "needs_review"

    changed = client.patch(
        f"/api/candidates/{candidate['id']}/jobs/{first_job['id']}/active-resume",
        headers=auth_headers,
        json={"resume_id": second_resume_id},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["active_resume_id"] == second_resume_id

    jobs_after = client.get(
        f"/api/candidates/{candidate['id']}/jobs", headers=auth_headers
    ).json()
    by_job_after = {item["job_id"]: item for item in jobs_after}
    assert by_job_after[second_job["id"]]["active_resume_id"] == second_resume_id

    db = db_mod.SessionLocal()
    try:
        assert db.query(ScoreEvent).count() == 0
        audit = db.query(AuditEvent).filter_by(action="candidate_job.active_resume_changed").one()
        assert audit.entity_id == str(by_job[first_job["id"]]["id"])
    finally:
        db.close()


def test_candidate_filters_and_merged_sources_are_hidden_by_default(client, auth_headers) -> None:
    visible = _create_candidate(client, auth_headers, "visible", "可见")
    review = _create_candidate(client, auth_headers, "review", "待复核")
    merged = _create_candidate(client, auth_headers, "merged", "已合并")
    target = _create_candidate(client, auth_headers, "target", "主体")
    first_job = _create_job(client, auth_headers, "数据")
    second_job = _create_job(client, auth_headers, "设计")
    db = db_mod.SessionLocal()
    try:
        visible_link = CandidateJob(
            candidate_id=visible["id"], job_id=first_job["id"], status="scored"
        )
        review_link = CandidateJob(
            candidate_id=review["id"], job_id=first_job["id"],
            status="needs_review", review_reason_json='["missing_degree"]',
        )
        other_link = CandidateJob(
            candidate_id=target["id"], job_id=second_job["id"], status="scored"
        )
        db.add_all([visible_link, review_link, other_link])
        db.flush()
        db.add_all(
            [
                OutreachEvent(
                    candidate_id=visible["id"],
                    job_id=first_job["id"],
                    status="confirmed",
                    greeted=True,
                ),
                OutreachEvent(
                    candidate_id=review["id"],
                    job_id=first_job["id"],
                    status="confirmed",
                    greeted=True,
                ),
                OutreachEvent(
                    candidate_id=merged["id"],
                    job_id=first_job["id"],
                    status="confirmed",
                    greeted=True,
                ),
                OutreachEvent(
                    candidate_id=target["id"],
                    job_id=second_job["id"],
                    status="confirmed",
                    greeted=True,
                ),
            ]
        )
        score = ScoreEvent(
            candidate_id=visible["id"], job_id=first_job["id"],
            candidate_job_id=visible_link.id, hard_filter_passed=True,
            score=88, decision="eligible",
        )
        db.add(score)
        db.flush()
        visible_link.latest_score_event_id = score.id
        merged_row = db.get(Candidate, merged["id"])
        merged_row.merged_into_candidate_id = target["id"]
        db.commit()
    finally:
        db.close()

    default_ids = {
        item["id"] for item in client.get("/api/candidates", headers=auth_headers).json()
    }
    assert merged["id"] not in default_ids

    scored = client.get(
        "/api/candidates",
        headers=auth_headers,
        params={"job_id": first_job["id"], "status": "scored", "min_score": 80},
    )
    assert [item["id"] for item in scored.json()] == [visible["id"]]

    needs_review = client.get(
        "/api/candidates",
        headers=auth_headers,
        params={"job_id": first_job["id"], "needs_review": True},
    )
    assert [item["id"] for item in needs_review.json()] == [review["id"]]

    not_needing_review = client.get(
        "/api/candidates",
        headers=auth_headers,
        params={"job_id": first_job["id"], "needs_review": False},
    )
    assert [item["id"] for item in not_needing_review.json()] == [visible["id"]]
