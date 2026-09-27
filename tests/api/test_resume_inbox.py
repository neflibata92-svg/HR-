from __future__ import annotations

from resume_api.core.security import create_access_token, hash_password
from resume_api.models import Candidate, CandidateJob, JobPosting, OutreachEvent, ScreeningTask, User


def _headers_for(user_id: int) -> dict[str, str]:
    from resume_api.core.config import get_settings

    token = create_access_token(get_settings(), user_id)
    return {"Authorization": f"Bearer {token}"}


def _waiting_candidate(*, owner_name: str, candidate_name: str, job_names: list[str]):
    from resume_api.core import db as db_mod

    with db_mod.SessionLocal() as db:
        owner = User(
            username=owner_name,
            password_hash=hash_password("password-123"),
            role="member",
            is_active=True,
            must_change_password=False,
        )
        candidate = Candidate(
            boss_id=f"boss-{owner_name}",
            fingerprint=f"fingerprint-{owner_name}",
            name=candidate_name,
            source="boss",
        )
        jobs = [JobPosting(name=name, jd_text="人工判断") for name in job_names]
        db.add_all([owner, candidate, *jobs])
        db.flush()
        events = []
        for index, job in enumerate(jobs, start=1):
            task = ScreeningTask(
                job_id=job.id,
                created_by_user_id=owner.id,
                machine_id=f"agent-{owner_name}",
                requested_count=10,
                status="completed",
            )
            db.add(task)
            db.flush()
            event = OutreachEvent(
                candidate_id=candidate.id,
                job_id=job.id,
                task_id=task.id,
                message_snapshot="您好",
                status="confirmed",
                greeted=True,
            )
            db.add_all(
                [
                    event,
                    CandidateJob(
                        candidate_id=candidate.id,
                        job_id=job.id,
                        status="waiting_resume",
                    ),
                ]
            )
            events.append(event)
        db.commit()
        return {
            "owner_id": owner.id,
            "candidate_id": candidate.id,
            "job_ids": [job.id for job in jobs],
            "event_ids": [event.id for event in events],
        }


def test_resume_inbox_is_scoped_to_current_hr_across_tasks(client):
    first = _waiting_candidate(
        owner_name="first-hr", candidate_name="第一位候选人", job_names=["岗位一", "岗位二"]
    )
    second = _waiting_candidate(
        owner_name="second-hr", candidate_name="第二位候选人", job_names=["岗位三"]
    )

    first_response = client.get(
        "/api/candidates/resume-inbox", headers=_headers_for(first["owner_id"])
    )
    second_response = client.get(
        "/api/candidates/resume-inbox", headers=_headers_for(second["owner_id"])
    )

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    assert [item["candidate_id"] for item in first_response.json()] == [first["candidate_id"]]
    assert first_response.json()[0]["boss_id"] == "boss-first-hr"
    assert [job["job_id"] for job in first_response.json()[0]["waiting_jobs"]] == first["job_ids"]
    assert [item["candidate_id"] for item in second_response.json()] == [second["candidate_id"]]


def test_single_waiting_job_upload_archives_and_updates_candidate(client):
    from resume_api.core import db as db_mod
    from resume_api.models import CandidateJob, OutreachEvent, Resume, ResumeJobArchive

    fixture = _waiting_candidate(
        owner_name="single-hr", candidate_name="单岗位候选人", job_names=["单岗位"]
    )
    pdf = b"%PDF-1.4\nsingle candidate resume\n%%EOF"
    response = client.post(
        "/api/resumes/agent-upload",
        headers=_headers_for(fixture["owner_id"]),
        data={
            "candidate_id": str(fixture["candidate_id"]),
            "contact_event_id": str(fixture["event_ids"][0]),
        },
        files={"file": ("候选人.pdf", pdf, "application/pdf")},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["assignment_status"] == "assigned"
    assert body["job_ids"] == fixture["job_ids"]
    with db_mod.SessionLocal() as db:
        resume = db.get(Resume, body["resume_id"])
        link = db.query(CandidateJob).filter_by(
            candidate_id=fixture["candidate_id"], job_id=fixture["job_ids"][0]
        ).one()
        archive = db.query(ResumeJobArchive).filter_by(resume_id=resume.id).one()
        event = db.get(OutreachEvent, fixture["event_ids"][0])
        assert resume.candidate_id == fixture["candidate_id"]
        assert resume.parsed_text == "" and resume.parse_status == "not_parsed"
        assert link.status == "resume_received" and link.active_resume_id == resume.id
        assert archive.job_id == fixture["job_ids"][0]
        assert event is not None and event.attachment_received is True


def test_retrying_same_agent_upload_is_idempotent(client):
    fixture = _waiting_candidate(
        owner_name="retry-hr", candidate_name="重试候选人", job_names=["重试岗位"]
    )
    request = {
        "headers": _headers_for(fixture["owner_id"]),
        "data": {
            "candidate_id": str(fixture["candidate_id"]),
            "contact_event_id": str(fixture["event_ids"][0]),
        },
        "files": {"file": ("候选人.pdf", b"%PDF-1.4\nsame resume\n%%EOF", "application/pdf")},
    }
    first = client.post("/api/resumes/agent-upload", **request)
    second = client.post("/api/resumes/agent-upload", **request)

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert second.json()["idempotent_hit"] is True
    assert second.json()["resume_id"] == first.json()["resume_id"]
