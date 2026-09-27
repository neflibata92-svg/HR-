from __future__ import annotations

from sqlalchemy import func, select


def _running_task(client, headers):
    job = client.post(
        "/api/jobs", headers=headers, json={"name": "候选人提升岗位", "jd_text": "Python"}
    ).json()
    task = client.post(
        "/api/screening-tasks",
        headers=headers,
        json={
            "job_id": job["id"],
            "requested_count": 2,
            "critical_fields": [{"key": "degree", "label": "学历"}],
            "critical_fields_source": {"confirmed": True, "source": "manual"},
        },
    ).json()
    client.post(
        f"/api/screening-tasks/{task['id']}/claim",
        headers=headers,
        json={"machine_id": "promotion-agent"},
    )
    return task, job


def _record(client, headers, task):
    response = client.post(
        f"/api/screening-tasks/{task['id']}/records",
        headers=headers,
        json={
            "machine_id": "promotion-agent",
            "boss_id": "boss-promoted",
            "fingerprint": "promoted-fingerprint",
            "display_name": "联系成功人员",
            "source_payload": {"phone": "138 0013 8000", "email": "USER@example.com"},
            "position_index": 1,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_confirmed_outreach_promotes_record_once_and_sets_waiting_resume(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import Candidate, CandidateJob, OutreachEvent, ScreeningRecord

    task, job = _running_task(client, auth_headers)
    record = _record(client, auth_headers, task)
    reserved = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={
            "screening_record_id": record["id"],
            "job_id": job["id"],
            "task_id": task["id"],
            "message": "您好",
        },
    )
    assert reserved.status_code == 201, reserved.text
    assert reserved.json()["candidate_id"] is None

    first = client.post(f"/api/outreach/{reserved.json()['id']}/confirm", headers=auth_headers)
    second = client.post(f"/api/outreach/{reserved.json()['id']}/confirm", headers=auth_headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["candidate_id"] == second.json()["candidate_id"]
    assert first.json()["candidate_id"] is not None

    with db_mod.SessionLocal() as db:
        assert db.scalar(select(func.count(Candidate.id))) == 1
        assert db.scalar(select(func.count(CandidateJob.id))) == 1
        link = db.scalar(select(CandidateJob))
        promoted = db.scalar(select(Candidate))
        saved_record = db.get(ScreeningRecord, record["id"])
        event = db.get(OutreachEvent, reserved.json()["id"])
        assert link is not None and link.status == "waiting_resume"
        assert promoted is not None and promoted.phone_normalized == "13800138000"
        assert promoted.email_normalized == "user@example.com"
        assert saved_record is not None and saved_record.candidate_id == promoted.id
        assert saved_record.status == "contacted"
        assert event is not None and event.candidate_id == promoted.id


def test_failed_outreach_does_not_promote_record(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import Candidate

    task, job = _running_task(client, auth_headers)
    record = _record(client, auth_headers, task)
    reserved = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={
            "screening_record_id": record["id"],
            "job_id": job["id"],
            "task_id": task["id"],
            "message": "您好",
        },
    ).json()
    failed = client.post(
        f"/api/outreach/{reserved['id']}/fail",
        headers=auth_headers,
        json={"reason": "发送失败"},
    )
    assert failed.status_code == 200, failed.text
    with db_mod.SessionLocal() as db:
        assert db.scalar(select(func.count(Candidate.id))) == 0


def test_candidate_list_only_shows_confirmed_contacts(client, auth_headers):
    direct = client.post(
        "/api/candidates",
        headers=auth_headers,
        json={"fingerprint": "unconfirmed-direct", "name": "未确认人员"},
    )
    assert direct.status_code == 200

    task, job = _running_task(client, auth_headers)
    record = _record(client, auth_headers, task)
    reserved = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={
            "screening_record_id": record["id"],
            "job_id": job["id"],
            "task_id": task["id"],
            "message": "您好",
        },
    ).json()
    client.post(f"/api/outreach/{reserved['id']}/confirm", headers=auth_headers)

    rows = client.get("/api/candidates", headers=auth_headers)
    assert rows.status_code == 200
    assert [row["name"] for row in rows.json()] == ["联系成功人员"]
