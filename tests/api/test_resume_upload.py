from resume_api.core import db as db_mod
from resume_api.models import CandidateJob, ResumeJobArchive


def _create_candidate(client, auth_headers, fingerprint: str) -> int:
    response = client.post(
        "/api/candidates",
        headers=auth_headers,
        json={"fingerprint": fingerprint, "name": "上传候选人"},
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_upload_txt_resume(client, auth_headers, tmp_path) -> None:
    candidate_id = _create_candidate(client, auth_headers, "upload-txt")
    file_path = tmp_path / "cv.txt"
    file_path.write_text("熟悉 Python 与招聘系统", encoding="utf-8")
    with file_path.open("rb") as handle:
        response = client.post(
            "/api/resumes/upload",
            headers=auth_headers,
            files={"file": ("cv.txt", handle, "text/plain")},
            data={"candidate_id": str(candidate_id), "source": "upload"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["parse_status"] == "ok"
    assert "Python" in body["parsed_text"]
    assert body["source"] == "upload"
    assert body["version_number"] == 1
    assert body["original_filename"] == "cv.txt"
    assert body["file_hash"]


def test_download_resume_file_requires_auth_and_returns_stored_content(
    client, auth_headers, tmp_path
) -> None:
    candidate_id = _create_candidate(client, auth_headers, "download-resume")
    file_path = tmp_path / "download.pdf"
    content = b"%PDF-1.4\ndownload content\n%%EOF"
    file_path.write_bytes(content)
    with file_path.open("rb") as handle:
        uploaded = client.post(
            "/api/resumes/upload",
            headers=auth_headers,
            files={"file": (file_path.name, handle, "application/pdf")},
            data={"candidate_id": str(candidate_id), "source": "upload"},
        )
    resume_id = uploaded.json()["id"]

    unauthenticated = client.get(f"/api/resumes/{resume_id}/file")
    response = client.get(f"/api/resumes/{resume_id}/file", headers=auth_headers)
    missing = client.get("/api/resumes/999999/file", headers=auth_headers)

    assert unauthenticated.status_code == 401
    assert response.status_code == 200, response.text
    assert response.content == content
    assert response.headers["content-type"].startswith("application/pdf")
    assert "download.pdf" in response.headers["content-disposition"]
    assert missing.status_code == 404


def test_upload_image_skipped(client, auth_headers, tmp_path) -> None:
    candidate_id = _create_candidate(client, auth_headers, "upload-image")
    file_path = tmp_path / "cv.png"
    file_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    with file_path.open("rb") as handle:
        response = client.post(
            "/api/resumes/upload",
            headers=auth_headers,
            files={"file": ("cv.png", handle, "image/png")},
            data={"candidate_id": str(candidate_id), "source": "upload"},
        )
    assert response.status_code == 200
    assert response.json()["parse_status"] == "skipped_image"


def test_upload_resume_assigns_candidate_and_archive_to_selected_job(
    client, auth_headers, tmp_path
) -> None:
    candidate_id = _create_candidate(client, auth_headers, "upload-for-job")
    job = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"name": "数据分析师", "jd_text": "数据分析"},
    ).json()
    file_path = tmp_path / "job-cv.txt"
    file_path.write_text("熟悉 SQL 与数据分析", encoding="utf-8")

    with file_path.open("rb") as handle:
        response = client.post(
            "/api/resumes/upload",
            headers=auth_headers,
            files={"file": ("job-cv.txt", handle, "text/plain")},
            data={
                "candidate_id": str(candidate_id),
                "job_id": str(job["id"]),
                "source": "upload",
            },
        )

    assert response.status_code == 200, response.text
    resume_id = response.json()["id"]
    listed = client.get(
        "/api/resumes", headers=auth_headers, params={"job_id": job["id"]}
    )
    assert [item["id"] for item in listed.json()] == [resume_id]
    db = db_mod.SessionLocal()
    try:
        link = db.query(CandidateJob).filter_by(
            candidate_id=candidate_id, job_id=job["id"]
        ).one()
        archive = db.query(ResumeJobArchive).filter_by(
            resume_id=resume_id, job_id=job["id"]
        ).one()
        assert link.active_resume_id is None
        assert archive.source == "upload"
    finally:
        db.close()


def test_upload_claims_an_unassigned_resume_already_archived_for_the_job(
    client, auth_headers, tmp_path
) -> None:
    from resume_api.models import Resume

    candidate_id = _create_candidate(client, auth_headers, "claim-archived-upload")
    job = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"name": "归档认领岗位", "jd_text": "测试跨入口重复"},
    ).json()
    content = b"%PDF-1.4\nshared resume content\n%%EOF"
    imported = client.post(
        "/api/resumes/batch-import",
        headers=auth_headers,
        data={"job_id": str(job["id"])},
        files={"files": ("shared.pdf", content, "application/pdf")},
    )
    assert imported.status_code == 200, imported.text
    imported_resume_id = imported.json()["items"][0]["resume_id"]

    response = client.post(
        "/api/resumes/upload",
        headers=auth_headers,
        files={"file": ("shared.pdf", content, "application/pdf")},
        data={
            "candidate_id": str(candidate_id),
            "job_id": str(job["id"]),
            "source": "upload",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == imported_resume_id
    assert response.json()["candidate_id"] == candidate_id
    assert response.json()["version_number"] == 1
    db = db_mod.SessionLocal()
    try:
        assert db.query(ResumeJobArchive).filter_by(job_id=job["id"]).count() == 1
        claimed = db.get(Resume, imported_resume_id)
        assert claimed is not None and claimed.candidate_id == candidate_id
        assert claimed.parse_status != "not_parsed"
    finally:
        db.close()
