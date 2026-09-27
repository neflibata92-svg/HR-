from __future__ import annotations

from sqlalchemy import func, select


def _job(client, headers, name: str) -> dict:
    response = client.post(
        "/api/jobs", headers=headers, json={"name": name, "jd_text": "人工判断"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _pdf(name: str, content: bytes) -> tuple[str, bytes, str]:
    return name, b"%PDF-1.4\n" + content + b"\n%%EOF", "application/pdf"


def test_manual_pdf_is_archived_directly_without_candidate_or_parsing(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import Candidate, Resume, ResumeJobArchive, ScoreEvent

    job = _job(client, auth_headers, "后端工程师")
    response = client.post(
        "/api/resumes/batch-import",
        headers=auth_headers,
        data={"job_id": str(job["id"])},
        files=[("files", _pdf("张三简历.pdf", b"private resume body"))],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] == job["id"]
    assert body["summary"] == {"imported": 1, "duplicate": 0, "failed": 0}
    assert body["items"][0]["status"] == "imported"
    assert body["items"][0]["original_filename"] == "张三简历.pdf"

    with db_mod.SessionLocal() as db:
        assert db.scalar(select(func.count(Candidate.id))) == 0
        assert db.scalar(select(func.count(ScoreEvent.id))) == 0
        resume = db.scalar(select(Resume))
        archive = db.scalar(select(ResumeJobArchive))
        assert resume is not None and resume.candidate_id is None
        assert resume.original_filename == "张三简历.pdf"
        assert resume.parsed_text == ""
        assert resume.parse_status == "not_parsed"
        assert resume.source == "manual_upload"
        assert archive is not None and archive.resume_id == resume.id
        assert archive.job_id == job["id"]

    listed = client.get("/api/resumes", headers=auth_headers, params={"job_id": job["id"]})
    assert listed.status_code == 200, listed.text
    assert [item["original_filename"] for item in listed.json()] == ["张三简历.pdf"]


def test_same_hash_is_skipped_within_job_but_allowed_across_jobs(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import Resume, ResumeJobArchive

    first_job = _job(client, auth_headers, "岗位一")
    second_job = _job(client, auth_headers, "岗位二")
    pdf = _pdf("同一份.pdf", b"same-content")

    first = client.post(
        "/api/resumes/batch-import",
        headers=auth_headers,
        data={"job_id": str(first_job["id"])},
        files=[("files", pdf)],
    )
    duplicate = client.post(
        "/api/resumes/batch-import",
        headers=auth_headers,
        data={"job_id": str(first_job["id"])},
        files=[("files", pdf)],
    )
    cross_job = client.post(
        "/api/resumes/batch-import",
        headers=auth_headers,
        data={"job_id": str(second_job["id"])},
        files=[("files", pdf)],
    )

    assert first.json()["items"][0]["status"] == "imported"
    assert duplicate.json()["items"][0]["status"] == "duplicate"
    assert cross_job.json()["items"][0]["status"] == "imported"
    with db_mod.SessionLocal() as db:
        assert db.scalar(select(func.count(Resume.id))) == 2
        assert db.scalar(select(func.count(ResumeJobArchive.id))) == 2


def test_job_resume_list_only_returns_resumes_archived_to_that_job(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import Candidate, CandidateJob, Resume, ResumeJobArchive

    first_job = _job(client, auth_headers, "严格归档岗位一")
    second_job = _job(client, auth_headers, "严格归档岗位二")
    with db_mod.SessionLocal() as db:
        candidate = Candidate(name="跨岗位候选人", fingerprint="strict-job-archive")
        db.add(candidate)
        db.flush()
        db.add_all([
            CandidateJob(candidate_id=candidate.id, job_id=first_job["id"]),
            CandidateJob(candidate_id=candidate.id, job_id=second_job["id"]),
        ])
        resume = Resume(
            candidate_id=candidate.id,
            version_number=1,
            original_filename="only-first-job.pdf",
            file_path="/tmp/only-first-job.pdf",
            file_hash="strict-first-job-hash",
            parsed_text="测试",
            source="upload",
            parse_status="parsed",
        )
        db.add(resume)
        db.flush()
        db.add(ResumeJobArchive(
            resume_id=resume.id,
            job_id=first_job["id"],
            source="upload",
            file_hash="strict-first-job-hash",
        ))
        db.commit()

    first = client.get("/api/resumes", headers=auth_headers, params={"job_id": first_job["id"]})
    second = client.get("/api/resumes", headers=auth_headers, params={"job_id": second_job["id"]})

    assert [item["original_filename"] for item in first.json()] == ["only-first-job.pdf"]
    assert second.json() == []
