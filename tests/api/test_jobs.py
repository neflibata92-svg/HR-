def test_jobs_require_token(client) -> None:
    response = client.get("/api/jobs")
    assert response.status_code == 401


def test_create_and_list_job(client, auth_headers) -> None:
    payload = {
        "name": "后端工程师",
        "jd_text": "需要 Python 与 FastAPI",
        "score_threshold": 80,
    }
    created = client.post("/api/jobs", json=payload, headers=auth_headers)
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "后端工程师"
    assert body["score_threshold"] == 80

    listed = client.get("/api/jobs", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    enabled = client.get("/api/jobs/enabled", headers=auth_headers)
    assert enabled.status_code == 200
    assert len(enabled.json()) == 1
