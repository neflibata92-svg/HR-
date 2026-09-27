from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select


def _job(client, headers, name):
    return client.post("/api/jobs", headers=headers, json={"name": name, "jd_text": "Python"}).json()


def _candidate(client, headers, suffix="global"):
    return client.post(
        "/api/candidates", headers=headers,
        json={"fingerprint": f"outreach-{suffix}", "name": "候选人"},
    ).json()


def _register_admin(client):
    response = client.post("/auth/register", json={"username": "admin", "password": "secret12"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _member(client, admin):
    client.post("/auth/users", headers=admin, json={"username": "member", "temporary_password": "tempPass8"})
    login = client.post("/auth/login", json={"username": "member", "password": "tempPass8"}).json()
    changed = client.post(
        "/auth/change-password", headers={"Authorization": f"Bearer {login['access_token']}"},
        json={"current_password": "tempPass8", "new_password": "newPass88"},
    ).json()
    return {"Authorization": f"Bearer {changed['access_token']}"}


def test_confirmed_contact_blocks_other_jobs_globally(client, auth_headers):
    candidate = _candidate(client, auth_headers)
    first_job = _job(client, auth_headers, "岗位 A")
    second_job = _job(client, auth_headers, "岗位 B")

    first = client.post(
        "/api/outreach/reservations", headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": first_job["id"], "message": "您好"},
    )
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "sending"
    confirmed = client.post(f"/api/outreach/{first.json()['id']}/confirm", headers=auth_headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    duplicate = client.post(
        "/api/outreach/reservations", headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": second_job["id"], "message": "您好"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "candidate already contacted"


def test_failed_send_can_retry_but_stale_sending_requires_manual_verification(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import OutreachEvent

    candidate = _candidate(client, auth_headers, "stale")
    job = _job(client, auth_headers, "岗位")
    reserved = client.post(
        "/api/outreach/reservations", headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": job["id"], "message": "您好"},
    ).json()
    failed = client.post(
        f"/api/outreach/{reserved['id']}/fail", headers=auth_headers,
        json={"reason": "页面失败"},
    )
    assert failed.status_code == 200
    retry = client.post(
        "/api/outreach/reservations", headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": job["id"], "message": "重试"},
    )
    assert retry.status_code == 201

    with db_mod.SessionLocal() as db:
        event = db.scalar(select(OutreachEvent).where(OutreachEvent.id == retry.json()["id"]))
        event.created_at = datetime.now(timezone.utc) - timedelta(minutes=31)
        db.commit()
    stale = client.post(
        "/api/outreach/reservations", headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": job["id"], "message": "不可自动重试"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == "outreach verification required"


def test_reservation_rejects_task_from_other_job(client, auth_headers):
    candidate = _candidate(client, auth_headers, "task-scope")
    task_job = _job(client, auth_headers, "任务岗位")
    other_job = _job(client, auth_headers, "联系岗位")
    task = client.post(
        "/api/screening-tasks",
        headers=auth_headers,
        json={
            "job_id": task_job["id"],
            "requested_count": 1,
            "critical_fields": [{"key": "degree", "label": "学历"}],
            "critical_fields_source": {"confirmed": True, "source": "manual"},
        },
    ).json()

    response = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={
            "candidate_id": candidate["id"],
            "job_id": other_job["id"],
            "task_id": task["id"],
            "message": "您好",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "task does not match outreach"


def test_override_is_privileged_scoped_and_consumed_once(client):
    admin = _register_admin(client)
    member = _member(client, admin)
    candidate = _candidate(client, admin, "override")
    first_job = _job(client, admin, "岗位 A")
    second_job = _job(client, admin, "岗位 B")
    legacy = client.post(
        "/api/events/outreach", headers=admin,
        json={"candidate_id": candidate["id"], "job_id": first_job["id"]},
    )
    assert legacy.status_code == 200

    payload = {"candidate_id": candidate["id"], "job_id": second_job["id"], "reason": "候选人同意再次沟通"}
    assert client.post("/api/outreach/overrides", headers=member, json=payload).status_code == 403
    override = client.post("/api/outreach/overrides", headers=admin, json=payload)
    assert override.status_code == 201, override.text

    first = client.post(
        "/api/outreach/reservations", headers=admin,
        json={"candidate_id": candidate["id"], "job_id": second_job["id"], "message": "授权联系"},
    )
    assert first.status_code == 201, first.text
    assert first.json()["manual_override_by_user_id"] is not None
    client.post(f"/api/outreach/{first.json()['id']}/confirm", headers=admin)
    second = client.post(
        "/api/outreach/reservations", headers=admin,
        json={"candidate_id": candidate["id"], "job_id": second_job["id"], "message": "再次联系"},
    )
    assert second.status_code == 409
