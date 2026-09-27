from __future__ import annotations


def _job(client, headers) -> dict:
    response = client.post(
        "/api/jobs", headers=headers, json={"name": "批量导入岗位", "jd_text": "人工判断"}
    )
    assert response.status_code == 201
    return response.json()


def test_batch_import_reports_each_file_without_aborting_valid_files(client, auth_headers):
    job = _job(client, auth_headers)
    response = client.post(
        "/api/resumes/batch-import",
        headers=auth_headers,
        data={"job_id": str(job["id"])},
        files=[
            ("files", ("有效.pdf", b"%PDF-1.4\nvalid\n%%EOF", "application/pdf")),
            ("files", ("空文件.pdf", b"", "application/pdf")),
            ("files", ("伪装.pdf", b"plain text", "application/pdf")),
            ("files", ("图片.png", b"%PDF-1.4\nwrong extension", "image/png")),
        ],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"] == {"imported": 1, "duplicate": 0, "failed": 3}
    assert [(item["original_filename"], item["status"]) for item in body["items"]] == [
        ("有效.pdf", "imported"),
        ("空文件.pdf", "failed"),
        ("伪装.pdf", "failed"),
        ("图片.png", "failed"),
    ]
    assert all(item["error"] for item in body["items"][1:])


def test_batch_import_rejects_file_over_20_mb(client, auth_headers):
    job = _job(client, auth_headers)
    oversized = b"%PDF-1.4\n" + (b"x" * (20 * 1024 * 1024))
    response = client.post(
        "/api/resumes/batch-import",
        headers=auth_headers,
        data={"job_id": str(job["id"])},
        files=[("files", ("超大.pdf", oversized, "application/pdf"))],
    )

    assert response.status_code == 200, response.text
    assert response.json()["summary"] == {"imported": 0, "duplicate": 0, "failed": 1}
    assert "20 MB" in response.json()["items"][0]["error"]


def test_batch_import_requires_existing_job(client, auth_headers):
    response = client.post(
        "/api/resumes/batch-import",
        headers=auth_headers,
        data={"job_id": "999999"},
        files=[("files", ("有效.pdf", b"%PDF-1.4\nvalid", "application/pdf"))],
    )
    assert response.status_code == 404
