def test_outreach_exists_endpoint(client, auth_headers) -> None:
    job = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"name": "测", "jd_text": "x"},
    ).json()
    candidate = client.post(
        "/api/candidates",
        headers=auth_headers,
        json={"fingerprint": "fp-out", "name": "测"},
    ).json()
    missing = client.get(
        "/api/events/outreach",
        headers=auth_headers,
        params={"job_id": job["id"], "candidate_id": candidate["id"]},
    )
    assert missing.json()["exists"] is False
    client.post(
        "/api/events/outreach",
        headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": job["id"]},
    )
    found = client.get(
        "/api/events/outreach",
        headers=auth_headers,
        params={"job_id": job["id"], "candidate_id": candidate["id"]},
    )
    assert found.json()["exists"] is True
