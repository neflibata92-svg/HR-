from __future__ import annotations

import pytest


def _job(client, headers, *, enabled: bool = True):
    response = client.post(
        "/api/jobs",
        headers=headers,
        json={
            "name": "后端工程师",
            "jd_text": "Python 与 SQL",
            "score_threshold": 82,
            "greet_template": "您好 {{candidate_name}}，这里是 {{job_name}} 岗位",
            "enabled": enabled,
        },
    )
    assert response.status_code == 201
    return response.json()


def _payload(job_id: int, count: int = 10):
    return {
        "job_id": job_id,
        "requested_count": count,
        "critical_fields": [{"key": "portfolio", "label": "作品集"}],
        "critical_fields_source": {"confirmed": True, "source": "ai_edited"},
    }


@pytest.mark.parametrize("count, expected", [(0, 422), (1, 201), (50, 201), (51, 422)])
def test_requested_count_is_limited_to_one_through_fifty(client, auth_headers, count, expected):
    job = _job(client, auth_headers)
    response = client.post(
        "/api/screening-tasks", headers=auth_headers, json=_payload(job["id"], count)
    )
    assert response.status_code == expected, response.text


def test_task_requires_enabled_job_but_not_critical_fields(client, auth_headers):
    enabled = _job(client, auth_headers)
    disabled = _job(client, auth_headers, enabled=False)

    payload = {
        "job_id": enabled["id"],
        "requested_count": 10,
        "critical_fields": [],
        "critical_fields_source": {},
    }

    assert client.post("/api/screening-tasks", headers=auth_headers, json=_payload(disabled["id"])).status_code == 409
    created = client.post("/api/screening-tasks", headers=auth_headers, json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["critical_fields"] == []


def test_started_task_keeps_job_and_rules_snapshot(client, auth_headers):
    job = _job(client, auth_headers)
    created = client.post(
        "/api/screening-tasks", headers=auth_headers, json=_payload(job["id"], 3)
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["status"] == "ready"

    claimed = client.post(
        "/api/screening-tasks/claim",
        headers=auth_headers,
        json={"machine_id": "mac-a"},
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["id"] == task["id"]

    updated = client.patch(
        f"/api/jobs/{job['id']}",
        headers=auth_headers,
        json={"name": "新岗位", "jd_text": "Go", "score_threshold": 10},
    )
    assert updated.status_code == 200
    fetched = client.get(f"/api/screening-tasks/{task['id']}", headers=auth_headers)
    body = fetched.json()
    assert body["machine_id"] == "mac-a"
    assert body["job_name_snapshot"] == "后端工程师"
    assert body["jd_text_snapshot"] == "Python 与 SQL"
    assert body["score_threshold_snapshot"] == 82
    assert body["requested_count"] == 3
    assert body["critical_fields"] == []
