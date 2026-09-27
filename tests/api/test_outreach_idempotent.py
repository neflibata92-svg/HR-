def test_failed_legacy_outreach_is_not_recorded_as_confirmed(client, auth_headers) -> None:
    job = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"name": "后端", "jd_text": "Python"},
    ).json()
    candidate = client.post(
        "/api/candidates",
        headers=auth_headers,
        json={"fingerprint": "fp-failed", "name": "王五"},
    ).json()

    response = client.post(
        "/api/events/outreach",
        headers=auth_headers,
        json={
            "candidate_id": candidate["id"],
            "job_id": job["id"],
            "greeted": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["confirmed_at"] is None


def test_outreach_idempotent(client, auth_headers) -> None:
    job = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"name": "前端", "jd_text": "Vue"},
    ).json()
    candidate = client.post(
        "/api/candidates",
        headers=auth_headers,
        json={"fingerprint": "fp1", "name": "李四"},
    ).json()

    first = client.post(
        "/api/events/outreach",
        headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": job["id"]},
    )
    assert first.status_code == 200
    assert first.json()["idempotent_hit"] is False
    assert first.json()["status"] == "confirmed"

    second = client.post(
        "/api/events/outreach",
        headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": job["id"]},
    )
    assert second.status_code == 200
    assert second.json()["idempotent_hit"] is True
    assert second.json()["id"] == first.json()["id"]


def test_legacy_outreach_endpoint_cannot_bypass_global_dedup(client, auth_headers) -> None:
    first_job = client.post(
        "/api/jobs", headers=auth_headers, json={"name": "岗位 A", "jd_text": "Python"}
    ).json()
    second_job = client.post(
        "/api/jobs", headers=auth_headers, json={"name": "岗位 B", "jd_text": "Go"}
    ).json()
    candidate = client.post(
        "/api/candidates",
        headers=auth_headers,
        json={"fingerprint": "legacy-global", "name": "赵六"},
    ).json()

    first = client.post(
        "/api/events/outreach",
        headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": first_job["id"]},
    )
    duplicate = client.post(
        "/api/events/outreach",
        headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": second_job["id"]},
    )

    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "candidate already contacted"
