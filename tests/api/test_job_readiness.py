from __future__ import annotations


def _job(client, headers, **overrides):
    payload = {
        "name": "后端工程师",
        "jd_text": "Python 与 SQL",
        "score_threshold": 82,
        "greet_template": "您好 {{candidate_name}}，这里是 {{job_name}} 岗位",
        "boss_entry_url": "https://www.zhipin.com/web/geek/job",
        "hourly_greet_limit": 20,
        "min_action_delay_ms": 1500,
        "max_action_delay_ms": 4000,
        "default_requested_count": 10,
        "critical_fields": [{"key": "portfolio", "label": "作品集"}],
        "critical_fields_confirmed": True,
        "enabled": True,
    }
    payload.update(overrides)
    response = client.post("/api/jobs", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _agent(client, headers, machine_id="job-readiness-mac"):
    response = client.post(
        "/api/agent/runs",
        headers=headers,
        json={
            "machine_id": machine_id,
            "status": "idle",
            "availability": "idle",
            "boss_login_status": "logged_in",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_job_readiness_lists_missing_configuration(client, auth_headers):
    job = _job(
        client,
        auth_headers,
        boss_entry_url="",
        default_requested_count=None,
        critical_fields=[],
        critical_fields_confirmed=False,
    )

    assert job["readiness"] == {
        "ready": False,
        "missing": ["boss_entry_url", "default_requested_count"],
    }
    response = client.get(f"/api/jobs/{job['id']}/readiness", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json() == job["readiness"]


def test_task_uses_saved_job_defaults_and_keeps_snapshot(client, auth_headers):
    job = _job(client, auth_headers, default_requested_count=7)
    agent = _agent(client, auth_headers)

    created = client.post(
        "/api/screening-tasks",
        headers=auth_headers,
        json={"job_id": job["id"], "assigned_agent_run_id": agent["id"]},
    )

    assert created.status_code == 201, created.text
    task = created.json()
    assert task["requested_count"] == 7
    assert task["critical_fields"] == []
    assert task["critical_fields_source"] == {"source": "jd"}
    assert task["job_name_snapshot"] == "后端工程师"
    assert task["jd_text_snapshot"] == "Python 与 SQL"
    assert task["score_threshold_snapshot"] == 82
    assert task["greet_template_snapshot"] == "您好 {{candidate_name}}，这里是 {{job_name}} 岗位"

    changed = client.patch(
        f"/api/jobs/{job['id']}",
        headers=auth_headers,
        json={
            "default_requested_count": 30,
            "critical_fields": [{"key": "degree", "label": "学历"}],
            "critical_fields_confirmed": True,
        },
    )
    assert changed.status_code == 200, changed.text
    fetched = client.get(f"/api/screening-tasks/{task['id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["requested_count"] == 7
    assert fetched.json()["critical_fields"] == []


def test_unconfirmed_critical_fields_do_not_block_but_disabled_job_cannot_start_task(client, auth_headers):
    unconfirmed = _job(client, auth_headers, critical_fields_confirmed=False)
    disabled = _job(client, auth_headers, name="停用岗位", enabled=False)
    agent = _agent(client, auth_headers)

    unconfirmed_response = client.post(
        "/api/screening-tasks",
        headers=auth_headers,
        json={"job_id": unconfirmed["id"], "assigned_agent_run_id": agent["id"]},
    )
    disabled_response = client.post(
        "/api/screening-tasks", headers=auth_headers, json={"job_id": disabled["id"]}
    )

    assert unconfirmed_response.status_code == 201
    assert disabled_response.status_code == 409
