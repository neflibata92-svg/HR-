from __future__ import annotations

from test_resume_inbox import _headers_for, _waiting_candidate


def test_multiple_waiting_jobs_require_hr_assignment(client):
    from resume_api.core import db as db_mod
    from resume_api.models import CandidateJob, Resume, ResumeJobArchive

    fixture = _waiting_candidate(
        owner_name="multi-hr", candidate_name="多岗位候选人", job_names=["前端", "全栈"]
    )
    uploaded = client.post(
        "/api/resumes/agent-upload",
        headers=_headers_for(fixture["owner_id"]),
        data={
            "candidate_id": str(fixture["candidate_id"]),
            "contact_event_id": str(fixture["event_ids"][0]),
        },
        files={"file": ("多岗位.pdf", b"%PDF-1.4\nmulti job\n%%EOF", "application/pdf")},
    )

    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["assignment_status"] == "pending_job_assignment"
    assert body["job_ids"] == fixture["job_ids"]
    with db_mod.SessionLocal() as db:
        resume = db.get(Resume, body["resume_id"])
        assert resume.assignment_status == "pending_job_assignment"
        assert db.query(ResumeJobArchive).filter_by(resume_id=resume.id).count() == 0
        statuses = {
            link.job_id: link.status
            for link in db.query(CandidateJob).filter_by(candidate_id=fixture["candidate_id"])
        }
        assert statuses == {job_id: "pending_job_assignment" for job_id in fixture["job_ids"]}

    selected_job = fixture["job_ids"][1]
    assigned = client.post(
        f"/api/resumes/{body['resume_id']}/assign-job",
        headers=_headers_for(fixture["owner_id"]),
        json={"job_id": selected_job},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assignment_status"] == "assigned"
    assert assigned.json()["job_ids"] == [selected_job]

    with db_mod.SessionLocal() as db:
        resume = db.get(Resume, body["resume_id"])
        archive = db.query(ResumeJobArchive).filter_by(resume_id=resume.id).one()
        links = {
            link.job_id: (link.status, link.active_resume_id)
            for link in db.query(CandidateJob).filter_by(candidate_id=fixture["candidate_id"])
        }
        assert resume.assignment_status == "assigned"
        assert archive.job_id == selected_job
        assert links[selected_job] == ("resume_received", resume.id)
        other_job = fixture["job_ids"][0]
        assert links[other_job] == ("waiting_resume", None)


def test_other_hr_cannot_upload_or_assign_candidate_resume(client):
    owner = _waiting_candidate(
        owner_name="owner-hr", candidate_name="受保护候选人", job_names=["受保护岗位"]
    )
    outsider = _waiting_candidate(
        owner_name="outsider-hr", candidate_name="其他候选人", job_names=["其他岗位"]
    )
    upload = client.post(
        "/api/resumes/agent-upload",
        headers=_headers_for(outsider["owner_id"]),
        data={
            "candidate_id": str(owner["candidate_id"]),
            "contact_event_id": str(owner["event_ids"][0]),
        },
        files={"file": ("越权.pdf", b"%PDF-1.4\nforbidden", "application/pdf")},
    )
    assert upload.status_code == 404
