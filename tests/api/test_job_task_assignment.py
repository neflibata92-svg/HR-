from __future__ import annotations

from datetime import datetime, timedelta, timezone

from resume_api.core.security import create_access_token, hash_password
from resume_api.models import AgentRun, User


def _headers(user_id: int) -> dict[str, str]:
    from resume_api.core.config import get_settings

    return {"Authorization": f"Bearer {create_access_token(get_settings(), user_id)}"}


def _user(username: str) -> int:
    from resume_api.core import db as db_mod

    with db_mod.SessionLocal() as db:
        user = User(
            username=username,
            password_hash=hash_password("password-123"),
            role="member",
            is_active=True,
            must_change_password=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def _ready_job(client, headers, name="指定 Agent 岗位"):
    response = client.post(
        "/api/jobs",
        headers=headers,
        json={
            "name": name,
            "jd_text": "Python",
            "boss_entry_url": "https://www.zhipin.com/web/geek/job",
            "default_requested_count": 3,
            "critical_fields": [{"key": "degree", "label": "学历"}],
            "critical_fields_confirmed": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _online_agent(client, headers, machine_id: str):
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


def test_task_requires_current_hr_online_idle_agent(client):
    owner_id = _user("owner-agent-hr")
    outsider_id = _user("outsider-agent-hr")
    owner_headers = _headers(owner_id)
    outsider_headers = _headers(outsider_id)
    job = _ready_job(client, owner_headers)
    outsider_agent = _online_agent(client, outsider_headers, "outsider-mac")
    busy_agent = _online_agent(client, owner_headers, "busy-mac")
    client.patch(
        "/api/agent/runs/busy-mac",
        headers=owner_headers,
        json={"machine_id": "busy-mac", "status": "running", "availability": "busy"},
    )

    missing = client.post(
        "/api/screening-tasks", headers=owner_headers, json={"job_id": job["id"]}
    )
    foreign = client.post(
        "/api/screening-tasks",
        headers=owner_headers,
        json={"job_id": job["id"], "assigned_agent_run_id": outsider_agent["id"]},
    )
    busy = client.post(
        "/api/screening-tasks",
        headers=owner_headers,
        json={"job_id": job["id"], "assigned_agent_run_id": busy_agent["id"]},
    )

    assert missing.status_code == 422
    assert foreign.status_code == 409
    assert busy.status_code == 409

    idle_agent = _online_agent(client, owner_headers, "idle-mac")
    created = client.post(
        "/api/screening-tasks",
        headers=owner_headers,
        json={"job_id": job["id"], "assigned_agent_run_id": idle_agent["id"]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["assigned_agent_run_id"] == idle_agent["id"]
    assert created.json()["machine_id"] == "idle-mac"

    stale_job = _ready_job(client, owner_headers, "过期心跳岗位")
    stale_agent = _online_agent(client, owner_headers, "stale-mac")
    from resume_api.core import db as db_mod

    with db_mod.SessionLocal() as db:
        stored_agent = db.get(AgentRun, stale_agent["id"])
        stored_agent.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=46)
        db.commit()
    stale = client.post(
        "/api/screening-tasks",
        headers=owner_headers,
        json={"job_id": stale_job["id"], "assigned_agent_run_id": stale_agent["id"]},
    )
    assert stale.status_code == 409
    assert "offline" in stale.json()["detail"]

    wrong_claim = client.post(
        f"/api/screening-tasks/{created.json()['id']}/claim",
        headers=owner_headers,
        json={"machine_id": "other-mac"},
    )
    right_claim = client.post(
        f"/api/screening-tasks/{created.json()['id']}/claim",
        headers=owner_headers,
        json={"machine_id": "idle-mac"},
    )
    assert wrong_claim.status_code == 409
    assert right_claim.status_code == 200


def test_same_job_has_one_active_task_until_terminal(client, auth_headers):
    job = _ready_job(client, auth_headers, "唯一活动任务")
    agent = _online_agent(client, auth_headers, "guard-mac")
    payload = {"job_id": job["id"], "assigned_agent_run_id": agent["id"]}

    first = client.post("/api/screening-tasks", headers=auth_headers, json=payload)
    second = client.post("/api/screening-tasks", headers=auth_headers, json=payload)
    assert first.status_code == 201, first.text
    assert second.status_code == 409

    claimed = client.post(
        f"/api/screening-tasks/{first.json()['id']}/claim",
        headers=auth_headers,
        json={"machine_id": "guard-mac"},
    )
    assert claimed.status_code == 200
    completed = client.post(
        f"/api/screening-tasks/{first.json()['id']}/complete",
        headers=auth_headers,
        json={"machine_id": "guard-mac"},
    )
    assert completed.status_code == 200
    assert completed.json()["active_job_guard"] is None

    restarted = client.post("/api/screening-tasks", headers=auth_headers, json=payload)
    assert restarted.status_code == 201, restarted.text


def test_agent_list_is_scoped_to_current_hr(client):
    first_id = _user("agent-list-first")
    second_id = _user("agent-list-second")
    first_headers = _headers(first_id)
    second_headers = _headers(second_id)
    _online_agent(client, first_headers, "first-mac")
    _online_agent(client, second_headers, "second-mac")

    first = client.get("/api/agent/runs", headers=first_headers)
    second = client.get("/api/agent/runs", headers=second_headers)
    assert [item["machine_id"] for item in first.json()] == ["first-mac"]
    assert [item["machine_id"] for item in second.json()] == ["second-mac"]


def test_task_list_restores_jobs_and_respects_user_scope(client):
    owner_id = _user("task-list-owner")
    other_id = _user("task-list-other")
    admin_id = _user("task-list-admin")
    from resume_api.core import db as db_mod

    with db_mod.SessionLocal() as db:
        admin = db.get(User, admin_id)
        admin.role = "admin"
        db.commit()

    owner_headers = _headers(owner_id)
    other_headers = _headers(other_id)
    admin_headers = _headers(admin_id)
    owner_job = _ready_job(client, owner_headers, "恢复岗位 A")
    other_job = _ready_job(client, other_headers, "恢复岗位 B")
    owner_agent = _online_agent(client, owner_headers, "restore-owner-mac")
    other_agent = _online_agent(client, other_headers, "restore-other-mac")
    owner_task = client.post(
        "/api/screening-tasks",
        headers=owner_headers,
        json={
            "job_id": owner_job["id"],
            "assigned_agent_run_id": owner_agent["id"],
        },
    ).json()
    other_task = client.post(
        "/api/screening-tasks",
        headers=other_headers,
        json={
            "job_id": other_job["id"],
            "assigned_agent_run_id": other_agent["id"],
        },
    ).json()

    owner_list = client.get("/api/screening-tasks", headers=owner_headers)
    owner_filtered = client.get(
        f"/api/screening-tasks?job_id={owner_job['id']}", headers=owner_headers
    )
    owner_other_job = client.get(
        f"/api/screening-tasks?job_id={other_job['id']}", headers=owner_headers
    )
    admin_list = client.get("/api/screening-tasks", headers=admin_headers)

    assert owner_list.status_code == 200, owner_list.text
    assert [task["id"] for task in owner_list.json()] == [owner_task["id"]]
    assert [task["id"] for task in owner_filtered.json()] == [owner_task["id"]]
    assert owner_other_job.json() == []
    assert {task["id"] for task in admin_list.json()} >= {
        owner_task["id"],
        other_task["id"],
    }
