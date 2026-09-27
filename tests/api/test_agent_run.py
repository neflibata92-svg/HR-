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


def test_agent_heartbeat_preserves_assignment_when_task_fields_are_omitted(
    client, auth_headers
) -> None:
    created = client.post(
        "/api/agent/runs",
        headers=auth_headers,
        json={
            "machine_id": "resident-mac",
            "status": "assigned",
            "availability": "busy",
            "current_task_id": 7,
            "current_job_id": 9,
            "boss_login_status": "logged_in",
        },
    )
    assert created.status_code == 200, created.text

    heartbeat = client.post(
        "/api/agent/runs",
        headers=auth_headers,
        json={
            "machine_id": "resident-mac",
            "status": "idle",
            "boss_login_status": "logged_in",
        },
    )

    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["current_task_id"] == 7
    assert heartbeat.json()["current_job_id"] == 9
    assert heartbeat.json()["availability"] == "busy"


def test_agent_heartbeat_clears_assignment_when_task_fields_are_explicit_null(
    client, auth_headers
) -> None:
    created = client.post(
        "/api/agent/runs",
        headers=auth_headers,
        json={
            "machine_id": "finished-mac",
            "status": "running",
            "availability": "busy",
            "current_task_id": 7,
            "current_job_id": 9,
            "boss_login_status": "logged_in",
        },
    )
    assert created.status_code == 200, created.text

    heartbeat = client.post(
        "/api/agent/runs",
        headers=auth_headers,
        json={
            "machine_id": "finished-mac",
            "status": "idle",
            "availability": "idle",
            "current_task_id": None,
            "current_job_id": None,
            "boss_login_status": "logged_in",
        },
    )

    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["current_task_id"] is None
    assert heartbeat.json()["current_job_id"] is None
    assert heartbeat.json()["availability"] == "idle"
