def test_agent_run_heartbeat(client, auth_headers) -> None:
    created = client.post(
        "/api/agent/runs",
        headers=auth_headers,
        json={"machine_id": "pc-1", "status": "running"},
    )
    assert created.status_code == 200
    assert created.json()["machine_id"] == "pc-1"

    patched = client.patch(
        "/api/agent/runs/pc-1",
        headers=auth_headers,
        json={"machine_id": "pc-1", "status": "paused", "last_error": "captcha"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "paused"
    assert patched.json()["last_error"] == "captcha"
