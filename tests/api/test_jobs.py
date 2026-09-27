def test_jobs_require_token(client) -> None:
    response = client.get("/api/jobs")
    assert response.status_code == 401


def test_create_and_list_job(client, auth_headers) -> None:
    payload = {
        "name": "后端工程师",
        "jd_text": "需要 Python 与 FastAPI",
        "score_threshold": 80,
        "greet_template": "您好 {{candidate_name}}，邀请您了解 {{job_name}}",
        "boss_entry_url": "https://www.zhipin.com/web/geek/job",
        "hourly_greet_limit": 15,
        "min_action_delay_ms": 1800,
        "max_action_delay_ms": 3600,
        "default_requested_count": 12,
        "critical_fields": [{"key": "portfolio", "label": "作品集"}],
        "critical_fields_confirmed": True,
    }
    created = client.post("/api/jobs", json=payload, headers=auth_headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "后端工程师"
    assert body["score_threshold"] == 80
    assert body["default_requested_count"] == 12
    assert body["critical_fields"] == [{"key": "portfolio", "label": "作品集"}]
    assert body["critical_fields_confirmed"] is True
    assert body["readiness"]["ready"] is True
    assert body["readiness"]["missing"] == []

    updated = client.patch(
        f"/api/jobs/{body['id']}",
        headers=auth_headers,
        json={
            "default_requested_count": 20,
            "critical_fields": [{"key": "degree", "label": "学历"}],
            "critical_fields_confirmed": True,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["default_requested_count"] == 20
    assert updated.json()["critical_fields"] == [{"key": "degree", "label": "学历"}]

    listed = client.get("/api/jobs", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["default_requested_count"] == 20

    enabled = client.get("/api/jobs/enabled", headers=auth_headers)
    assert enabled.status_code == 200
    assert len(enabled.json()) == 1
