from __future__ import annotations


def _task(client, headers):
    job = client.post(
        "/api/jobs", headers=headers, json={"name": "测试岗位", "jd_text": "Python"}
    ).json()
    response = client.post(
        "/api/screening-tasks",
        headers=headers,
        json={
            "job_id": job["id"],
            "requested_count": 2,
            "critical_fields": [{"key": "degree", "label": "学历"}],
            "critical_fields_source": {"confirmed": True, "source": "manual"},
        },
    )
    assert response.status_code == 201
    return response.json(), job


def _candidate(client, headers, suffix):
    return client.post(
        "/api/candidates",
        headers=headers,
        json={"fingerprint": f"task-item-{suffix}", "name": f"候选人{suffix}"},
    ).json()


def test_task_item_creation_is_idempotent_and_belongs_to_claimed_task(client, auth_headers):
    task, job = _task(client, auth_headers)
    client.post("/api/screening-tasks/claim", headers=auth_headers, json={"machine_id": "mac-a"})
    candidate = _candidate(client, auth_headers, "a")
    payload = {"machine_id": "mac-a", "candidate_id": candidate["id"], "position_index": 1}

    first = client.post(f"/api/screening-tasks/{task['id']}/items", headers=auth_headers, json=payload)
    second = client.post(f"/api/screening-tasks/{task['id']}/items", headers=auth_headers, json=payload)
    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    assert first.json()["job_id"] == job["id"]

    wrong_machine = dict(payload, machine_id="mac-b")
    assert client.post(f"/api/screening-tasks/{task['id']}/items", headers=auth_headers, json=wrong_machine).status_code == 409


def test_item_completion_recalculates_summary_from_database(client, auth_headers):
    task, _ = _task(client, auth_headers)
    client.post("/api/screening-tasks/claim", headers=auth_headers, json={"machine_id": "mac-a"})
    first_candidate = _candidate(client, auth_headers, "b")
    second_candidate = _candidate(client, auth_headers, "c")

    first = client.post(
        f"/api/screening-tasks/{task['id']}/items", headers=auth_headers,
        json={"machine_id": "mac-a", "candidate_id": first_candidate["id"], "position_index": 1},
    ).json()
    second = client.post(
        f"/api/screening-tasks/{task['id']}/items", headers=auth_headers,
        json={"machine_id": "mac-a", "candidate_id": second_candidate["id"], "position_index": 2},
    ).json()

    outreach = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={
            "candidate_id": first_candidate["id"],
            "job_id": task["job_id"],
            "task_id": task["id"],
            "message": "您好",
        },
    ).json()
    client.post(f"/api/outreach/{outreach['id']}/confirm", headers=auth_headers)
    contacted = client.post(
        f"/api/screening-tasks/{task['id']}/items/{first['id']}/complete",
        headers=auth_headers,
        json={
            "machine_id": "mac-a",
            "status": "contacted",
            "outreach_event_id": outreach["id"],
        },
    )
    reviewed = client.post(
        f"/api/screening-tasks/{task['id']}/items/{second['id']}/complete",
        headers=auth_headers, json={"machine_id": "mac-a", "status": "needs_review"},
    )
    assert contacted.status_code == 200, contacted.text
    assert reviewed.status_code == 200, reviewed.text

    fetched = client.get(f"/api/screening-tasks/{task['id']}", headers=auth_headers).json()
    assert fetched["processed_count"] == 2
    assert fetched["eligible_count"] == 1
    assert fetched["contacted_count"] == 1
    assert fetched["review_count"] == 1
    assert fetched["skipped_count"] == 0
    assert fetched["failed_count"] == 0
    assert fetched["status"] == "completed"
    assert fetched["finished_at"] is not None


def test_task_rejects_more_unique_candidates_than_requested_count(client, auth_headers):
    task, _ = _task(client, auth_headers)
    client.post("/api/screening-tasks/claim", headers=auth_headers, json={"machine_id": "mac-a"})
    candidates = [_candidate(client, auth_headers, suffix) for suffix in ("limit-a", "limit-b", "limit-c")]
    for index, candidate in enumerate(candidates[:2], start=1):
        response = client.post(
            f"/api/screening-tasks/{task['id']}/items",
            headers=auth_headers,
            json={"machine_id": "mac-a", "candidate_id": candidate["id"], "position_index": index},
        )
        assert response.status_code == 201

    overflow = client.post(
        f"/api/screening-tasks/{task['id']}/items",
        headers=auth_headers,
        json={"machine_id": "mac-a", "candidate_id": candidates[2]["id"], "position_index": 1},
    )
    assert overflow.status_code == 409
    assert overflow.json()["detail"] == "task requested count exceeded"


def test_contacted_item_requires_confirmed_outreach_from_same_task(client, auth_headers):
    task, job = _task(client, auth_headers)
    client.post("/api/screening-tasks/claim", headers=auth_headers, json={"machine_id": "mac-a"})
    candidate = _candidate(client, auth_headers, "confirmed-outreach")
    item = client.post(
        f"/api/screening-tasks/{task['id']}/items",
        headers=auth_headers,
        json={"machine_id": "mac-a", "candidate_id": candidate["id"], "position_index": 1},
    ).json()

    missing = client.post(
        f"/api/screening-tasks/{task['id']}/items/{item['id']}/complete",
        headers=auth_headers,
        json={"machine_id": "mac-a", "status": "contacted"},
    )
    assert missing.status_code == 409
    assert missing.json()["detail"] == "contacted item requires confirmed outreach event"

    sending = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={
            "candidate_id": candidate["id"],
            "job_id": job["id"],
            "task_id": task["id"],
            "message": "您好",
        },
    ).json()
    unconfirmed = client.post(
        f"/api/screening-tasks/{task['id']}/items/{item['id']}/complete",
        headers=auth_headers,
        json={
            "machine_id": "mac-a",
            "status": "contacted",
            "outreach_event_id": sending["id"],
        },
    )
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["detail"] == "contacted item requires confirmed outreach event"



def test_task_item_rejects_score_event_from_other_candidate(client, auth_headers):
    task, job = _task(client, auth_headers)
    client.post("/api/screening-tasks/claim", headers=auth_headers, json={"machine_id": "mac-a"})
    candidate = _candidate(client, auth_headers, "owner-a")
    other = _candidate(client, auth_headers, "owner-b")
    item = client.post(
        f"/api/screening-tasks/{task['id']}/items",
        headers=auth_headers,
        json={"machine_id": "mac-a", "candidate_id": candidate["id"], "position_index": 1},
    ).json()
    score = client.post(
        "/api/events/scores",
        headers=auth_headers,
        json={
            "candidate_id": other["id"],
            "job_id": job["id"],
            "hard_filter_passed": True,
            "score": 90,
            "decision": "eligible",
        },
    ).json()

    response = client.post(
        f"/api/screening-tasks/{task['id']}/items/{item['id']}/complete",
        headers=auth_headers,
        json={
            "machine_id": "mac-a",
            "status": "contacted",
            "score_event_id": score["id"],
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "score event does not belong to task item"
