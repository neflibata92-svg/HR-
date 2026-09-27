from __future__ import annotations


def _register_admin(client):
    response = client.post("/auth/register", json={"username": "admin", "password": "secret12"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _ready_member(client, admin_headers, username: str):
    temporary = "tempPass8"
    created = client.post(
        "/auth/users",
        headers=admin_headers,
        json={"username": username, "temporary_password": temporary, "role": "member"},
    )
    assert created.status_code == 201
    login = client.post("/auth/login", json={"username": username, "password": temporary})
    assert login.status_code == 200
    changed = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"current_password": temporary, "new_password": "newPass88"},
    )
    assert changed.status_code == 200
    return {"Authorization": f"Bearer {changed.json()['access_token']}"}


def _task(client, owner_headers):
    job = client.post(
        "/api/jobs",
        headers=owner_headers,
        json={"name": "权限岗位", "jd_text": "Python", "enabled": True},
    )
    assert job.status_code == 201
    task = client.post(
        "/api/screening-tasks",
        headers=owner_headers,
        json={
            "job_id": job.json()["id"],
            "requested_count": 1,
            "critical_fields": [{"key": "degree", "label": "学历"}],
            "critical_fields_source": {"confirmed": True, "source": "manual"},
        },
    )
    assert task.status_code == 201
    return job.json(), task.json()


def test_member_cannot_read_claim_or_cancel_another_members_task(client) -> None:
    admin = _register_admin(client)
    owner = _ready_member(client, admin, "owner")
    attacker = _ready_member(client, admin, "attacker")
    _, task = _task(client, owner)

    assert client.get(f"/api/screening-tasks/{task['id']}", headers=attacker).status_code == 404
    assert client.post(
        f"/api/screening-tasks/{task['id']}/claim",
        headers=attacker,
        json={"machine_id": "shared-machine"},
    ).status_code == 404
    assert client.post(
        f"/api/screening-tasks/{task['id']}/cancel", headers=attacker
    ).status_code == 404

    claimed = client.post(
        f"/api/screening-tasks/{task['id']}/claim",
        headers=owner,
        json={"machine_id": "shared-machine"},
    )
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "running"


def test_member_cannot_reserve_or_confirm_another_members_task_outreach(client) -> None:
    admin = _register_admin(client)
    owner = _ready_member(client, admin, "outreach-owner")
    attacker = _ready_member(client, admin, "outreach-attacker")
    job, task = _task(client, owner)
    candidate = client.post(
        "/api/candidates",
        headers=owner,
        json={"fingerprint": "permission-candidate", "name": "候选人"},
    )
    assert candidate.status_code == 200

    denied = client.post(
        "/api/outreach/reservations",
        headers=attacker,
        json={
            "candidate_id": candidate.json()["id"],
            "job_id": job["id"],
            "task_id": task["id"],
            "message": "您好",
        },
    )
    assert denied.status_code == 404

    reserved = client.post(
        "/api/outreach/reservations",
        headers=owner,
        json={
            "candidate_id": candidate.json()["id"],
            "job_id": job["id"],
            "task_id": task["id"],
            "message": "您好",
        },
    )
    assert reserved.status_code == 201
    event_id = reserved.json()["id"]
    assert client.post(f"/api/outreach/{event_id}/confirm", headers=attacker).status_code == 404
    confirmed = client.post(f"/api/outreach/{event_id}/confirm", headers=owner)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"


def test_member_cannot_create_or_operate_taskless_outreach(client) -> None:
    admin = _register_admin(client)
    member = _ready_member(client, admin, "taskless-member")
    job = client.post(
        "/api/jobs",
        headers=admin,
        json={"name": "共享岗位", "jd_text": "Python", "enabled": True},
    ).json()
    candidate = client.post(
        "/api/candidates",
        headers=admin,
        json={"fingerprint": "taskless-candidate", "name": "候选人"},
    ).json()

    denied = client.post(
        "/api/outreach/reservations",
        headers=member,
        json={"candidate_id": candidate["id"], "job_id": job["id"], "message": "您好"},
    )
    assert denied.status_code == 403
    legacy = client.post(
        "/api/events/outreach",
        headers=member,
        json={"candidate_id": candidate["id"], "job_id": job["id"]},
    )
    assert legacy.status_code == 403

    admin_event = client.post(
        "/api/outreach/reservations",
        headers=admin,
        json={"candidate_id": candidate["id"], "job_id": job["id"], "message": "管理员人工联系"},
    )
    assert admin_event.status_code == 201
    assert client.post(
        f"/api/outreach/{admin_event.json()['id']}/confirm", headers=member
    ).status_code == 404



def test_admin_can_manage_another_users_task(client) -> None:
    admin = _register_admin(client)
    owner = _ready_member(client, admin, "admin-visible-owner")
    _, task = _task(client, owner)

    fetched = client.get(f"/api/screening-tasks/{task['id']}", headers=admin)
    assert fetched.status_code == 200
    cancelled = client.post(f"/api/screening-tasks/{task['id']}/cancel", headers=admin)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
