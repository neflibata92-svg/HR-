from __future__ import annotations

from resume_api.core import db as db_mod
from resume_api.models import (
    AuditEvent,
    Candidate,
    CandidateJob,
    JobPosting,
    OutreachEvent,
    OutreachOverride,
    Resume,
)


def _create_candidate(client, headers, suffix: str):
    response = client.post(
        "/api/candidates", headers=headers,
        json={"fingerprint": f"revert-{suffix}", "boss_id": f"revert-boss-{suffix}", "name": suffix},
    )
    assert response.status_code == 200
    return response.json()


def _merge_fixture(client, headers):
    source = _create_candidate(client, headers, "source")
    target = _create_candidate(client, headers, "target")
    db = db_mod.SessionLocal()
    try:
        job = JobPosting(name="测试", jd_text="测试")
        db.add(job)
        db.flush()
        resume = Resume(
            candidate_id=source["id"], version_number=1, original_filename="s.txt",
            file_path="/tmp/revert-source.txt", file_hash="revert-source-hash", source="upload",
        )
        db.add(resume)
        db.flush()
        link = CandidateJob(candidate_id=source["id"], job_id=job.id, active_resume_id=resume.id)
        outreach = OutreachEvent(candidate_id=source["id"], job_id=job.id, status="confirmed")
        override = OutreachOverride(
            candidate_id=source["id"], job_id=job.id, authorized_by_user_id=1,
            reason="主管批准",
        )
        db.add_all([link, outreach, override])
        db.commit()
        original = {
            "resume_id": resume.id,
            "link_id": link.id,
            "outreach_id": outreach.id,
            "override_id": override.id,
            "job_id": job.id,
        }
    finally:
        db.close()
    payload = {"source_candidate_id": source["id"], "target_candidate_id": target["id"], "field_choices": {}}
    response = client.post("/api/candidate-merges", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return source, target, response.json(), original


def test_revert_restores_original_ownership_and_is_idempotent(client, auth_headers) -> None:
    source, target, merge, original = _merge_fixture(client, auth_headers)

    reverted = client.post(f"/api/candidate-merges/{merge['id']}/revert", headers=auth_headers)
    assert reverted.status_code == 200, reverted.text
    assert reverted.json()["status"] == "reverted"
    assert reverted.json()["idempotent"] is False

    db = db_mod.SessionLocal()
    try:
        assert db.get(Candidate, source["id"]).merged_into_candidate_id is None
        assert db.get(Resume, original["resume_id"]).candidate_id == source["id"]
        assert db.get(CandidateJob, original["link_id"]).candidate_id == source["id"]
        assert db.get(OutreachEvent, original["outreach_id"]).candidate_id == source["id"]
        assert db.get(OutreachOverride, original["override_id"]).candidate_id == source["id"]
    finally:
        db.close()

    repeated = client.post(f"/api/candidate-merges/{merge['id']}/revert", headers=auth_headers)
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    db = db_mod.SessionLocal()
    try:
        attempts = db.query(AuditEvent).filter_by(action="candidate_merge.revert").all()
        assert len(attempts) == 2
        assert '"result": "idempotent"' in attempts[-1].details_json
    finally:
        db.close()


def test_revert_rejects_modified_original_job_link(client, auth_headers) -> None:
    source, target, merge, original = _merge_fixture(client, auth_headers)
    db = db_mod.SessionLocal()
    try:
        link = db.get(CandidateJob, original["link_id"])
        link.status = "contacted"
        db.commit()
    finally:
        db.close()

    response = client.post(f"/api/candidate-merges/{merge['id']}/revert", headers=auth_headers)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["conflicts"][0]["reason"] == "modified_after_merge"
    db = db_mod.SessionLocal()
    try:
        assert db.get(CandidateJob, original["link_id"]).status == "contacted"
        assert db.get(Candidate, source["id"]).merged_into_candidate_id == target["id"]
    finally:
        db.close()


def test_revert_conflict_rolls_back_entire_operation_and_is_audited(client, auth_headers) -> None:
    source, target, merge, original = _merge_fixture(client, auth_headers)
    db = db_mod.SessionLocal()
    try:
        new_resume = Resume(
            candidate_id=target["id"], version_number=2, original_filename="new.txt",
            file_path="/tmp/revert-new.txt", file_hash="revert-new-hash", source="upload",
        )
        db.add(new_resume)
        db.commit()
        new_resume_id = new_resume.id
    finally:
        db.close()

    response = client.post(f"/api/candidate-merges/{merge['id']}/revert", headers=auth_headers)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["conflicts"][0]["entity_type"] == "resume"

    db = db_mod.SessionLocal()
    try:
        assert db.get(Candidate, source["id"]).merged_into_candidate_id == target["id"]
        assert db.get(Resume, original["resume_id"]).candidate_id == target["id"]
        assert db.get(Resume, new_resume_id).candidate_id == target["id"]
        attempts = db.query(AuditEvent).filter_by(action="candidate_merge.revert").all()
        assert attempts
        assert "snapshot" not in attempts[-1].details_json
    finally:
        db.close()


def test_revert_rejects_reused_deleted_job_link_id(client, auth_headers) -> None:
    source = _create_candidate(client, auth_headers, "dedupe-source")
    target = _create_candidate(client, auth_headers, "dedupe-target")
    db = db_mod.SessionLocal()
    try:
        shared = JobPosting(name="共享岗位", jd_text="共享")
        replacement_job = JobPosting(name="新岗位", jd_text="新")
        db.add_all([shared, replacement_job])
        db.flush()
        source_link = CandidateJob(candidate_id=source["id"], job_id=shared.id)
        target_link = CandidateJob(candidate_id=target["id"], job_id=shared.id)
        db.add_all([source_link, target_link])
        db.commit()
        deleted_link_id = source_link.id
        replacement_job_id = replacement_job.id
    finally:
        db.close()
    payload = {"source_candidate_id": source["id"], "target_candidate_id": target["id"], "field_choices": {}}
    merge = client.post("/api/candidate-merges", headers=auth_headers, json=payload).json()

    db = db_mod.SessionLocal()
    try:
        db.add(CandidateJob(id=deleted_link_id, candidate_id=target["id"], job_id=replacement_job_id))
        db.commit()
    finally:
        db.close()

    response = client.post(f"/api/candidate-merges/{merge['id']}/revert", headers=auth_headers)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["conflicts"][0]["reason"] == "id_reused"
    db = db_mod.SessionLocal()
    try:
        reused = db.get(CandidateJob, deleted_link_id)
        assert reused.candidate_id == target["id"]
        assert reused.job_id == replacement_job_id
    finally:
        db.close()
