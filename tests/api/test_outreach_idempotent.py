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

    second = client.post(
        "/api/events/outreach",
        headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": job["id"]},
    )
    assert second.status_code == 200
    assert second.json()["idempotent_hit"] is True
    assert second.json()["id"] == first.json()["id"]
