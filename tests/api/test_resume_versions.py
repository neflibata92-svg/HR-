from __future__ import annotations

from pathlib import Path

from resume_api.core import db as db_mod
from resume_api.models import CandidateJob, ScoreEvent


def _create_candidate(client, headers, fingerprint: str = "resume-owner") -> dict:
    response = client.post(
        "/api/candidates",
        headers=headers,
        json={"fingerprint": fingerprint, "name": "简历候选人"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _upload(client, headers, candidate_id: int, path: Path, job_id: int | None = None):
    data = {"candidate_id": str(candidate_id), "source": "upload"}
    if job_id is not None:
        data["job_id"] = str(job_id)
    with path.open("rb") as handle:
        return client.post(
            "/api/resumes/upload",
            headers=headers,
            files={"file": (path.name, handle, "text/plain")},
            data=data,
        )


def test_resume_versions_increment_and_same_hash_is_idempotent(
    client, auth_headers, tmp_path
) -> None:
    candidate = _create_candidate(client, auth_headers)
    first_path = tmp_path / "first.txt"
    second_path = tmp_path / "second.txt"
    duplicate_path = tmp_path / "duplicate.txt"
    first_path.write_text("第一版 Python", encoding="utf-8")
    second_path.write_text("第二版 Python FastAPI", encoding="utf-8")
    duplicate_path.write_text("第一版 Python", encoding="utf-8")

    first = _upload(client, auth_headers, candidate["id"], first_path)
    second = _upload(client, auth_headers, candidate["id"], second_path)
    duplicate = _upload(client, auth_headers, candidate["id"], duplicate_path)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert duplicate.status_code == 200, duplicate.text
    assert first.json()["version_number"] == 1
    assert second.json()["version_number"] == 2
    assert duplicate.json()["id"] == first.json()["id"]
    assert duplicate.json()["version_number"] == 1
    assert first.json()["file_hash"] == duplicate.json()["file_hash"]
    assert first.json()["original_filename"] == "first.txt"
    assert Path(first.json()["file_path"]).is_file()

    listed = client.get(
        "/api/resumes", headers=auth_headers, params={"candidate_id": candidate["id"]}
    )
    assert listed.status_code == 200, listed.text
    assert [item["version_number"] for item in listed.json()] == [2, 1]


def test_new_resume_does_not_switch_job_version_or_trigger_scoring(
    client, auth_headers, tmp_path
) -> None:
    candidate = _create_candidate(client, auth_headers, "no-auto-switch")
    job = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"name": "后端", "jd_text": "Python"},
    ).json()
    first_path = tmp_path / "active.txt"
    first_path.write_text("当前版本", encoding="utf-8")
    first = _upload(client, auth_headers, candidate["id"], first_path, job["id"]).json()

    db = db_mod.SessionLocal()
    try:
        link = db.query(CandidateJob).filter_by(
            candidate_id=candidate["id"], job_id=job["id"]
        ).one()
        link.status = "scored"
        link.active_resume_id = first["id"]
        db.commit()
    finally:
        db.close()

    second_path = tmp_path / "new.txt"
    second_path.write_text("新版本", encoding="utf-8")
    second = _upload(client, auth_headers, candidate["id"], second_path, job["id"])
    assert second.status_code == 200, second.text

    db = db_mod.SessionLocal()
    try:
        link = db.query(CandidateJob).filter_by(
            candidate_id=candidate["id"], job_id=job["id"]
        ).one()
        assert link.active_resume_id == first["id"]
        assert db.query(ScoreEvent).count() == 0
    finally:
        db.close()

    by_job = client.get(
        "/api/resumes", headers=auth_headers, params={"job_id": job["id"]}
    )
    assert by_job.status_code == 200, by_job.text
    assert [item["id"] for item in by_job.json()] == [second.json()["id"], first["id"]]


def test_web_upload_requires_candidate(client, auth_headers, tmp_path) -> None:
    path = tmp_path / "unowned.txt"
    path.write_text("必须选择候选人", encoding="utf-8")
    with path.open("rb") as handle:
        response = client.post(
            "/api/resumes/upload",
            headers=auth_headers,
            files={"file": (path.name, handle, "text/plain")},
        )

    assert response.status_code == 422
