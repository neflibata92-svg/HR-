from __future__ import annotations


def _create_task(client, headers):
    job = client.post(
        "/api/jobs", headers=headers, json={"name": "状态机岗位", "jd_text": "Python"}
    ).json()
    response = client.post(
        "/api/screening-tasks", headers=headers,
        json={
            "job_id": job["id"], "requested_count": 1,
            "critical_fields": [{"key": "degree", "label": "学历"}],
            "critical_fields_source": {"confirmed": True, "source": "manual"},
        },
    )
    assert response.status_code == 201
    return response.json()


def test_claim_is_atomic_and_second_machine_cannot_take_running_task(client, auth_headers):
    task = _create_task(client, auth_headers)
    first = client.post(
        "/api/screening-tasks/claim", headers=auth_headers, json={"machine_id": "mac-a"}
    )
    second = client.post(
        f"/api/screening-tasks/{task['id']}/claim",
        headers=auth_headers, json={"machine_id": "mac-b"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "running"
    assert second.status_code == 409


def test_task_state_machine_accepts_only_legal_transitions(client, auth_headers):
    task = _create_task(client, auth_headers)
    assert client.post(f"/api/screening-tasks/{task['id']}/pause", headers=auth_headers, json={"reason": "检查页面"}).status_code == 409
    assert client.post(f"/api/screening-tasks/{task['id']}/claim", headers=auth_headers, json={"machine_id": "mac-a"}).status_code == 200

    pausing = client.post(
        f"/api/screening-tasks/{task['id']}/pause",
        headers=auth_headers,
        json={"reason": "检查页面"},
    )
    assert pausing.status_code == 200
    assert pausing.json()["status"] == "pausing"
    blocked_record = client.post(
        f"/api/screening-tasks/{task['id']}/records",
        headers=auth_headers,
        json={
            "machine_id": "mac-a",
            "fingerprint": "blocked-after-pause",
            "display_name": "不应继续",
            "position_index": 1,
        },
    )
    assert blocked_record.status_code == 409

    paused = client.post(
        f"/api/screening-tasks/{task['id']}/control/ack",
        headers=auth_headers,
        json={"machine_id": "mac-a"},
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert client.post(f"/api/screening-tasks/{task['id']}/resume", headers=auth_headers).status_code == 200

    cancelling = client.post(f"/api/screening-tasks/{task['id']}/cancel", headers=auth_headers)
    assert cancelling.status_code == 200
    assert cancelling.json()["status"] == "cancelling"
    cancelled = client.post(
        f"/api/screening-tasks/{task['id']}/control/ack",
        headers=auth_headers,
        json={"machine_id": "mac-a"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["active_job_guard"] is None
    assert client.post(f"/api/screening-tasks/{task['id']}/resume", headers=auth_headers).status_code == 409
    assert client.post(f"/api/screening-tasks/{task['id']}/cancel", headers=auth_headers).status_code == 409


def test_owner_can_complete_task_when_page_has_fewer_candidates(client, auth_headers):
    task = _create_task(client, auth_headers)
    claimed = client.post(
        f"/api/screening-tasks/{task['id']}/claim",
        headers=auth_headers,
        json={"machine_id": "mac-a"},
    )
    assert claimed.status_code == 200

    wrong_machine = client.post(
        f"/api/screening-tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"machine_id": "mac-b"},
    )
    assert wrong_machine.status_code == 409

    completed = client.post(
        f"/api/screening-tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"machine_id": "mac-a"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["processed_count"] == 0
    assert completed.json()["finished_at"] is not None

    repeated = client.post(
        f"/api/screening-tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"machine_id": "mac-a"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "completed"


def test_same_machine_can_reclaim_running_task_after_restart(client, auth_headers):
    task = _create_task(client, auth_headers)
    first = client.post(
        f"/api/screening-tasks/{task['id']}/claim",
        headers=auth_headers,
        json={"machine_id": "mac-a"},
    )
    assert first.status_code == 200

    recovered = client.post(
        "/api/screening-tasks/claim",
        headers=auth_headers,
        json={"machine_id": "mac-a"},
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["id"] == task["id"]
    assert recovered.json()["status"] == "running"

    other_machine = client.post(
        f"/api/screening-tasks/{task['id']}/claim",
        headers=auth_headers,
        json={"machine_id": "mac-b"},
    )
    assert other_machine.status_code == 409
