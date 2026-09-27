from __future__ import annotations

from resume_api.core import db as db_mod
from resume_api.models import (
    CandidateJob,
    ExchangeEvent,
    JobPosting,
    OutreachEvent,
    OutreachOverride,
    Resume,
    ScoreEvent,
    ScreeningTask,
    ScreeningTaskItem,
)


def _candidate(client, headers, suffix: str, **overrides):
    payload = {
        "fingerprint": f"fp-{suffix}",
        "boss_id": f"boss-{suffix}",
        "name": suffix,
        "phone": f"1380000{suffix[-4:].zfill(4)}",
        "email": f"{suffix}@example.com",
        "age": 20,
        "years_of_experience": 2,
        "source": "boss",
    }
    payload.update(overrides)
    response = client.post("/api/candidates", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_field_merge_preserves_all_history_and_deduplicates_jobs(client, auth_headers) -> None:
    source = _candidate(client, auth_headers, "1001", name="来源姓名", age=28, source="import")
    target = _candidate(client, auth_headers, "2002", name="目标姓名", age=35, source="boss")
    db = db_mod.SessionLocal()
    try:
        job = JobPosting(name="后端", jd_text="Python")
        db.add(job)
        db.flush()
        source_resume = Resume(
            candidate_id=source["id"], version_number=1, original_filename="s.txt",
            file_path="/tmp/s.txt", file_hash="source-hash", source="upload",
        )
        target_resume = Resume(
            candidate_id=target["id"], version_number=1, original_filename="t.txt",
            file_path="/tmp/t.txt", file_hash="target-hash", source="upload",
        )
        db.add_all([source_resume, target_resume])
        db.flush()
        source_job = CandidateJob(
            candidate_id=source["id"], job_id=job.id, status="resume_received",
            active_resume_id=source_resume.id,
        )
        target_job = CandidateJob(
            candidate_id=target["id"], job_id=job.id, status="contacted",
            active_resume_id=target_resume.id,
        )
        db.add_all([source_job, target_job])
        db.flush()
        score = ScoreEvent(
            candidate_id=source["id"], job_id=job.id, candidate_job_id=source_job.id,
            resume_id=source_resume.id, score=88, decision="eligible",
        )
        outreach = OutreachEvent(candidate_id=source["id"], job_id=job.id, status="confirmed")
        exchange = ExchangeEvent(candidate_id=source["id"], operator="HR", type="exchange")
        override = OutreachOverride(
            candidate_id=source["id"], job_id=job.id, authorized_by_user_id=1,
            reason="主管批准",
        )
        task = ScreeningTask(
            job_id=job.id, created_by_user_id=1, requested_count=1,
            job_name_snapshot="后端", jd_text_snapshot="Python",
        )
        db.add_all([score, outreach, exchange, override, task])
        db.flush()
        item = ScreeningTaskItem(
            task_id=task.id, candidate_id=source["id"], candidate_job_id=source_job.id,
            position_index=1,
        )
        db.add(item)
        db.commit()
        ids = {
            "source_resume": source_resume.id,
            "target_resume": target_resume.id,
            "source_job": source_job.id,
            "target_job": target_job.id,
            "score": score.id,
            "outreach": outreach.id,
            "exchange": exchange.id,
            "override": override.id,
            "item": item.id,
        }
    finally:
        db.close()

    payload = {
        "source_candidate_id": source["id"],
        "target_candidate_id": target["id"],
        "field_choices": {
            "name": "source", "phone_normalized": "source",
            "email_normalized": "target", "age": "source",
            "years_of_experience": "target", "source": "source",
        },
    }
    preview = client.post("/api/candidate-merges/preview", headers=auth_headers, json=payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["conflicts"] == []
    assert preview.json()["merged_fields"]["name"] == "来源姓名"

    merged = client.post("/api/candidate-merges", headers=auth_headers, json=payload)
    assert merged.status_code == 201, merged.text
    assert merged.json()["status"] == "active"

    db = db_mod.SessionLocal()
    try:
        source_row = db.get(__import__("resume_api.models", fromlist=["Candidate"]).Candidate, source["id"])
        target_row = db.get(__import__("resume_api.models", fromlist=["Candidate"]).Candidate, target["id"])
        assert source_row.merged_into_candidate_id == target["id"]
        assert target_row.name == "来源姓名"
        assert target_row.age == 28
        assert target_row.email_normalized == target["email_normalized"]
        resumes = db.query(Resume).filter_by(candidate_id=target["id"]).order_by(Resume.version_number).all()
        assert [row.id for row in resumes] == [ids["source_resume"], ids["target_resume"]]
        assert [row.version_number for row in resumes] == [1, 2]
        jobs = db.query(CandidateJob).filter_by(candidate_id=target["id"]).all()
        assert len(jobs) == 1
        assert jobs[0].id == ids["target_job"]
        assert jobs[0].status == "resume_received"
        score_row = db.get(ScoreEvent, ids["score"])
        assert score_row.candidate_id == target["id"]
        assert score_row.candidate_job_id == ids["target_job"]
        assert score_row.resume_id == ids["source_resume"]
        assert db.get(ScreeningTaskItem, ids["item"]).candidate_id == target["id"]
        assert db.get(ScreeningTaskItem, ids["item"]).candidate_job_id == ids["target_job"]
        assert db.get(OutreachEvent, ids["outreach"]).candidate_id == target["id"]
        assert db.get(OutreachOverride, ids["override"]).candidate_id == target["id"]
        assert db.get(ExchangeEvent, ids["exchange"]).candidate_id == target["id"]
    finally:
        db.close()


def test_merge_rejects_same_candidate_and_already_merged_source(client, auth_headers) -> None:
    source = _candidate(client, auth_headers, "3003")
    target = _candidate(client, auth_headers, "4004")
    same = {"source_candidate_id": source["id"], "target_candidate_id": source["id"], "field_choices": {}}
    assert client.post("/api/candidate-merges", headers=auth_headers, json=same).status_code == 422
    db = db_mod.SessionLocal()
    try:
        from resume_api.models import AuditEvent

        attempt = db.query(AuditEvent).filter_by(action="candidate_merge.execute").one()
        assert '"result": "validation_failed"' in attempt.details_json
        assert "snapshot" not in attempt.details_json
    finally:
        db.close()

    payload = {"source_candidate_id": source["id"], "target_candidate_id": target["id"], "field_choices": {}}
    first = client.post("/api/candidate-merges", headers=auth_headers, json=payload)
    assert first.status_code == 201
    repeated = client.post("/api/candidate-merges", headers=auth_headers, json=payload)
    assert repeated.status_code == 200
    assert repeated.json()["id"] == first.json()["id"]

    reverse = {"source_candidate_id": target["id"], "target_candidate_id": source["id"], "field_choices": {}}
    assert client.post("/api/candidate-merges", headers=auth_headers, json=reverse).status_code == 409

    third = _candidate(client, auth_headers, "5005")
    chained = {"source_candidate_id": target["id"], "target_candidate_id": third["id"], "field_choices": {}}
    assert client.post("/api/candidate-merges", headers=auth_headers, json=chained).status_code == 409
