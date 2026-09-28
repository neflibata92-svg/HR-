from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from resume_api.migrations.runner import run_migrations


def test_quota_migration_preserves_unattributable_task_history_and_stops(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'unattributable.db'}")
    with engine.begin() as connection:
        for ddl in (
            "CREATE TABLE schema_migrations (version VARCHAR(100) PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE)",
            "CREATE TABLE screening_tasks (id INTEGER PRIMARY KEY, created_by_user_id INTEGER NOT NULL)",
            "CREATE TABLE screening_task_items (id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL)",
            "CREATE TABLE outreach_events (id INTEGER PRIMARY KEY, task_id INTEGER)",
        ):
            connection.execute(text(ddl))
        connection.execute(
            text(
                "INSERT INTO schema_migrations (version) VALUES "
                "('0001_add_must_change_password'), ('0002_talent_records'), "
                "('0003_job_task_resume_archives'), ('0004_candidate_history'), "
                "('0005_task_entry_url_snapshot')"
            )
        )
        connection.execute(text("INSERT INTO users VALUES (1, 'hr-one')"))
        connection.execute(text("INSERT INTO outreach_events VALUES (30, 999)"))

    with pytest.raises(RuntimeError, match="Cannot attribute task-linked outreach events"):
        run_migrations(engine)

    assert not inspect(engine).has_table("outreach_quota_ledgers")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id, task_id FROM outreach_events")).all() == [(30, 999)]


def test_quota_migration_initializes_each_user_at_zero_and_adds_constraints(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'quota.db'}")
    event.listen(
        engine,
        "connect",
        lambda connection, _record: connection.execute("PRAGMA foreign_keys=ON"),
    )
    with engine.begin() as connection:
        for ddl in (
            "CREATE TABLE schema_migrations (version VARCHAR(100) PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE)",
            "CREATE TABLE screening_tasks (id INTEGER PRIMARY KEY, created_by_user_id INTEGER NOT NULL REFERENCES users(id))",
            "CREATE TABLE screening_task_items (id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES screening_tasks(id))",
            "CREATE TABLE outreach_events (id INTEGER PRIMARY KEY, task_id INTEGER REFERENCES screening_tasks(id))",
        ):
            connection.execute(text(ddl))
        connection.execute(
            text(
                "INSERT INTO schema_migrations (version) VALUES "
                "('0001_add_must_change_password'), ('0002_talent_records'), "
                "('0003_job_task_resume_archives'), ('0004_candidate_history'), "
                "('0005_task_entry_url_snapshot')"
            )
        )
        connection.execute(text("INSERT INTO users VALUES (1, 'hr-one'), (2, 'hr-two')"))
        connection.execute(text("INSERT INTO screening_tasks VALUES (10, 1), (11, 2)"))
        connection.execute(text("INSERT INTO screening_task_items VALUES (20, 10)"))
        connection.execute(
            text("INSERT INTO outreach_events (id, task_id) VALUES (30, 10), (31, NULL), (32, NULL), (33, NULL), (34, NULL), (35, NULL)")
        )

    run_migrations(engine)
    run_migrations(engine)

    inspector = inspect(engine)
    assert inspector.has_table("outreach_quota_ledgers")
    assert inspector.has_table("outreach_quota_reservations")
    assert {key["name"] for key in inspector.get_unique_constraints("outreach_quota_ledgers")} == {
        "uq_outreach_quota_ledger_user"
    }
    reservation_uniques = {
        key["name"] for key in inspector.get_unique_constraints("outreach_quota_reservations")
    }
    assert {"uq_outreach_quota_reservation_task_item", "uq_outreach_quota_reservation_event"} <= reservation_uniques
    reservation_fks = {
        (
            key["referred_table"],
            tuple(key["constrained_columns"]),
            tuple(key["referred_columns"]),
        )
        for key in inspector.get_foreign_keys("outreach_quota_reservations")
    }
    ledger_fks = {
        (key["referred_table"], tuple(key["constrained_columns"]))
        for key in inspector.get_foreign_keys("outreach_quota_ledgers")
    }
    assert ("users", ("user_id",)) in ledger_fks
    assert ("outreach_quota_ledgers", ("user_id",), ("user_id",)) in reservation_fks
    assert ("screening_tasks", ("task_id", "user_id"), ("id", "created_by_user_id")) in reservation_fks
    assert ("screening_task_items", ("task_item_id", "task_id"), ("id", "task_id")) in reservation_fks
    assert ("outreach_events", ("outreach_event_id", "user_id"), ("id", "quota_owner_user_id")) in reservation_fks

    with engine.connect() as connection:
        ledger_rows = connection.execute(
            text(
                "SELECT user_id, hard_limit, confirmed_count, reserved_count "
                "FROM outreach_quota_ledgers ORDER BY user_id"
            )
        ).all()
        assert [tuple(row) for row in ledger_rows] == [(1, 200, 0, 0), (2, 200, 0, 0)]
        assert connection.execute(text("SELECT COUNT(*) FROM outreach_quota_reservations")).scalar_one() == 0
        assert connection.execute(
            text("SELECT quota_owner_user_id FROM outreach_events WHERE id = 30")
        ).scalar_one() == 1
        assert connection.execute(
            text("SELECT quota_owner_user_id FROM outreach_events WHERE id = 31")
        ).scalar_one() is None

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE outreach_events SET task_id = 10, quota_owner_user_id = 1 WHERE id = 30"
            )
        )
        connection.execute(
            text("UPDATE outreach_events SET quota_owner_user_id = 2 WHERE id = 31")
        )
        connection.execute(
            text(
                "UPDATE outreach_events SET task_id = 10, quota_owner_user_id = 1 WHERE id = 34"
            )
        )
        connection.execute(
            text(
                "INSERT INTO outreach_quota_reservations "
                "(user_id, task_id, task_item_id, outreach_event_id, status) "
                "VALUES (1, 10, 20, 30, 'reserved')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO outreach_quota_reservations "
                "(user_id, outreach_event_id, status) VALUES (2, 31, 'unknown')"
            )
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE outreach_events SET quota_owner_user_id = 2 WHERE id = 34")
            )

    invalid_reservations = (
        ("user_id, status", "2, 'reserved'"),
        ("user_id, outreach_event_id, status", "1, 32, 'pending'"),
        ("user_id, task_id, outreach_event_id, status", "2, 10, 33, 'reserved'"),
        ("user_id, task_id, task_item_id, outreach_event_id, status", "1, 11, 20, 34, 'reserved'"),
        ("user_id, outreach_event_id, status", "2, 34, 'reserved'"),
    )
    for columns, values in invalid_reservations:
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO outreach_quota_reservations (" + columns + ") VALUES (" + values + ")"
                    )
                )


def _job(client, headers):
    response = client.post("/api/jobs", headers=headers, json={"name": "工程师", "jd_text": "Python"})
    assert response.status_code == 201, response.text
    return response.json()


def _candidate(client, headers, fingerprint="quota-candidate"):
    response = client.post(
        "/api/candidates",
        headers=headers,
        json={"fingerprint": fingerprint, "name": "候选人"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_task_outreach_derives_quota_owner_and_settles_confirmed_usage(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import OutreachEvent, OutreachQuotaLedger, OutreachQuotaReservation

    job = _job(client, auth_headers)
    candidate = _candidate(client, auth_headers)
    task_response = client.post(
        "/api/screening-tasks",
        headers=auth_headers,
        json={"job_id": job["id"], "requested_count": 1},
    )
    assert task_response.status_code == 201, task_response.text
    task = task_response.json()

    created = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={
            "candidate_id": candidate["id"],
            "job_id": job["id"],
            "task_id": task["id"],
            "message": "您好",
        },
    )
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]

    with db_mod.SessionLocal() as db:
        event = db.get(OutreachEvent, event_id)
        assert event.quota_owner_user_id == task["created_by_user_id"]
        reservation = db.scalar(
            select(OutreachQuotaReservation).where(
                OutreachQuotaReservation.outreach_event_id == event_id
            )
        )
        assert reservation is not None and reservation.user_id == task["created_by_user_id"]
        ledger = db.scalar(
            select(OutreachQuotaLedger).where(
                OutreachQuotaLedger.user_id == task["created_by_user_id"]
            )
        )
        assert (ledger.confirmed_count, ledger.reserved_count) == (0, 1)

    confirmed = client.post(f"/api/outreach/{event_id}/confirm", headers=auth_headers)
    assert confirmed.status_code == 200, confirmed.text
    with db_mod.SessionLocal() as db:
        ledger = db.scalar(select(OutreachQuotaLedger))
        reservation = db.scalar(select(OutreachQuotaReservation))
        assert (ledger.confirmed_count, ledger.reserved_count) == (1, 0)
        assert reservation.status == "confirmed"


def test_taskless_authorized_outreach_uses_authenticated_hr_and_failed_send_releases(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import OutreachEvent, OutreachQuotaLedger, OutreachQuotaReservation

    job = _job(client, auth_headers)
    candidate = _candidate(client, auth_headers, "quota-manual")
    created = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": job["id"], "message": "您好"},
    )
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]

    with db_mod.SessionLocal() as db:
        event = db.get(OutreachEvent, event_id)
        assert event.quota_owner_user_id is not None
        reservation = db.scalar(select(OutreachQuotaReservation))
        assert reservation.user_id == event.quota_owner_user_id
        ledger = db.scalar(select(OutreachQuotaLedger))
        assert (ledger.confirmed_count, ledger.reserved_count) == (0, 1)

    spoofed = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={
            "candidate_id": _candidate(client, auth_headers, "quota-spoof")["id"],
            "job_id": job["id"],
            "message": "您好",
            "quota_owner_user_id": 999,
        },
    )
    assert spoofed.status_code == 422

    failed = client.post(
        f"/api/outreach/{event_id}/fail", headers=auth_headers, json={"reason": "发送前页面异常"}
    )
    assert failed.status_code == 200, failed.text
    with db_mod.SessionLocal() as db:
        ledger = db.scalar(select(OutreachQuotaLedger))
        reservation = db.scalar(select(OutreachQuotaReservation))
        assert (ledger.confirmed_count, ledger.reserved_count) == (0, 0)
        assert reservation.status == "released"


def test_current_user_quota_endpoint_does_not_accept_other_user_id(client, auth_headers):
    response = client.get("/api/quotas/me", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"limit": 200, "confirmed": 0, "reserved": 0, "remaining": 200}
    other = client.get("/api/quotas/me?user_id=999", headers=auth_headers)
    assert other.status_code == 422


def test_unknown_send_result_keeps_quota_reserved_and_can_be_confirmed(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import OutreachQuotaLedger, OutreachQuotaReservation

    job = _job(client, auth_headers)
    candidate = _candidate(client, auth_headers, "quota-unknown")
    created = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": job["id"], "message": "您好"},
    )
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]

    unknown = client.post(
        f"/api/outreach/{event_id}/unknown",
        headers=auth_headers,
        json={"reason": "页面未能确认发送结果"},
    )
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["status"] == "unknown"
    retry_unknown = client.post(
        f"/api/outreach/{event_id}/unknown",
        headers=auth_headers,
        json={"reason": "重复核实"},
    )
    assert retry_unknown.status_code == 200
    assert retry_unknown.json()["status"] == "unknown"
    with db_mod.SessionLocal() as db:
        ledger = db.scalar(select(OutreachQuotaLedger))
        reservation = db.scalar(select(OutreachQuotaReservation))
        assert (ledger.confirmed_count, ledger.reserved_count) == (0, 1)
        assert reservation.status == "unknown"

    released = client.post(
        f"/api/outreach/{event_id}/fail",
        headers=auth_headers,
        json={"reason": "不应将未知结果当成失败"},
    )
    assert released.status_code == 409
    confirmed = client.post(f"/api/outreach/{event_id}/confirm", headers=auth_headers)
    assert confirmed.status_code == 200, confirmed.text
    with db_mod.SessionLocal() as db:
        ledger = db.scalar(select(OutreachQuotaLedger))
        reservation = db.scalar(select(OutreachQuotaReservation))
        assert (ledger.confirmed_count, ledger.reserved_count) == (1, 0)
        assert reservation.status == "confirmed"


def test_admin_can_release_unknown_quota_after_confirming_not_sent(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import AuditEvent, OutreachEvent, OutreachQuotaLedger, OutreachQuotaReservation

    job = _job(client, auth_headers)
    candidate = _candidate(client, auth_headers, "admin-release-unknown")
    created = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": job["id"], "message": "您好"},
    )
    event_id = created.json()["id"]
    marked = client.post(
        f"/api/outreach/{event_id}/unknown",
        headers=auth_headers,
        json={"reason": "页面无法确认"},
    )
    assert marked.status_code == 200

    pending = client.get("/api/outreach/unknown", headers=auth_headers)
    assert pending.status_code == 200
    assert any(
        item["id"] == event_id
        and item["candidate_name"] == candidate["name"]
        and item["quota_owner_username"] == "dev"
        for item in pending.json()
    )

    missing_confirmation = client.post(
        f"/api/outreach/{event_id}/release-unknown",
        headers=auth_headers,
        json={"reason": "后台核实未发送"},
    )
    assert missing_confirmation.status_code == 422
    released = client.post(
        f"/api/outreach/{event_id}/release-unknown",
        headers=auth_headers,
        json={"reason": "已核对平台记录，确认没有发出消息", "confirmed_not_sent": True},
    )
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "failed"

    with db_mod.SessionLocal() as db:
        ledger = db.scalar(select(OutreachQuotaLedger))
        reservation = db.scalar(select(OutreachQuotaReservation))
        event = db.get(OutreachEvent, event_id)
        audit = db.scalar(
            select(AuditEvent).where(AuditEvent.action == "outreach.unknown_resolved_not_sent")
        )
        assert (ledger.confirmed_count, ledger.reserved_count) == (0, 0)
        assert reservation.status == "released"
        assert event.status == "failed"
        assert audit.actor_user_id == 1
        assert audit.entity_id == str(event_id)

    retried = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={"candidate_id": candidate["id"], "job_id": job["id"], "message": "再次联系"},
    )
    assert retried.status_code == 201, retried.text


def test_only_admin_can_list_or_release_unknown_outreach(client, auth_headers):
    from resume_api.models import OutreachEvent
    from resume_api.core import db as db_mod

    created_user = client.post(
        "/auth/users",
        headers=auth_headers,
        json={"username": "quota-member", "temporary_password": "TempPass123"},
    )
    assert created_user.status_code == 201, created_user.text
    login = client.post(
        "/auth/login", json={"username": "quota-member", "password": "TempPass123"}
    ).json()
    changed = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {login['access_token']}"},
        json={"current_password": "TempPass123", "new_password": "SecurePass1234"},
    ).json()
    member_headers = {"Authorization": f"Bearer {changed['access_token']}"}

    with db_mod.SessionLocal() as db:
        event = db.scalar(select(OutreachEvent).where(OutreachEvent.status == "unknown"))
        event_id = event.id if event else None
    if event_id is None:
        job = _job(client, auth_headers)
        candidate = _candidate(client, auth_headers, "member-denied-unknown")
        created = client.post(
            "/api/outreach/reservations",
            headers=auth_headers,
            json={"candidate_id": candidate["id"], "job_id": job["id"], "message": "您好"},
        )
        event_id = created.json()["id"]
        client.post(
            f"/api/outreach/{event_id}/unknown",
            headers=auth_headers,
            json={"reason": "页面无法确认"},
        )

    assert client.get("/api/outreach/unknown", headers=member_headers).status_code == 403
    denied = client.post(
        f"/api/outreach/{event_id}/release-unknown",
        headers=member_headers,
        json={"reason": "确认没有发送", "confirmed_not_sent": True},
    )
    assert denied.status_code == 403


def test_outreach_reservation_rejects_ambiguous_task_item_and_record(client, auth_headers):
    response = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={
            "task_item_id": 1,
            "screening_record_id": 1,
            "job_id": 1,
            "message": "您好",
        },
    )
    assert response.status_code == 422


def test_batch_cannot_exceed_current_users_remaining_quota(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import OutreachQuotaLedger

    job = _job(client, auth_headers)
    assert client.get("/api/quotas/me", headers=auth_headers).status_code == 200
    with db_mod.SessionLocal() as db:
        ledger = db.scalar(select(OutreachQuotaLedger))
        ledger.confirmed_count = 199
        db.commit()

    task_response = client.post(
        "/api/screening-tasks",
        headers=auth_headers,
        json={"job_id": job["id"], "requested_count": 2},
    )
    assert task_response.status_code == 409
    assert task_response.json()["detail"] == "outreach quota is insufficient for this batch"

    usage = client.get("/api/quotas/me", headers=auth_headers)
    assert usage.json() == {"limit": 200, "confirmed": 199, "reserved": 0, "remaining": 1}


def test_concurrent_style_reservations_cannot_cross_lifetime_limit(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import OutreachQuotaLedger

    job = _job(client, auth_headers)
    assert client.get("/api/quotas/me", headers=auth_headers).status_code == 200
    with db_mod.SessionLocal() as db:
        ledger = db.scalar(select(OutreachQuotaLedger))
        ledger.confirmed_count = 199
        db.commit()

    first_candidate = _candidate(client, auth_headers, "quota-boundary-one")
    second_candidate = _candidate(client, auth_headers, "quota-boundary-two")
    first = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={"candidate_id": first_candidate["id"], "job_id": job["id"], "message": "您好"},
    )
    assert first.status_code == 201, first.text
    confirmed = client.post(f"/api/outreach/{first.json()['id']}/confirm", headers=auth_headers)
    assert confirmed.status_code == 200, confirmed.text
    second = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={"candidate_id": second_candidate["id"], "job_id": job["id"], "message": "您好"},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "outreach quota exhausted"
    usage = client.get("/api/quotas/me", headers=auth_headers)
    assert usage.json() == {"limit": 200, "confirmed": 200, "reserved": 0, "remaining": 0}


def test_task_linked_screening_record_omitted_task_id_charges_task_owner(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import OutreachEvent, OutreachQuotaReservation, ScreeningRecord

    job = _job(client, auth_headers)
    candidate = _candidate(client, auth_headers, "quota-record-task")
    task_response = client.post(
        "/api/screening-tasks",
        headers=auth_headers,
        json={"job_id": job["id"], "requested_count": 1},
    )
    assert task_response.status_code == 201, task_response.text
    task = task_response.json()
    with db_mod.SessionLocal() as db:
        record = ScreeningRecord(
            task_id=task["id"],
            job_id=job["id"],
            fingerprint="quota-record-task",
            identity_key="quota-record-task",
            display_name="候选人",
            candidate_id=candidate["id"],
            position_index=1,
        )
        db.add(record)
        db.commit()
        record_id = record.id

    created = client.post(
        "/api/outreach/reservations",
        headers=auth_headers,
        json={"screening_record_id": record_id, "job_id": job["id"], "message": "您好"},
    )
    assert created.status_code == 201, created.text
    with db_mod.SessionLocal() as db:
        outreach = db.get(OutreachEvent, created.json()["id"])
        reservation = db.scalar(select(OutreachQuotaReservation))
        assert outreach.task_id == task["id"]
        assert outreach.quota_owner_user_id == task["created_by_user_id"]
        assert reservation.user_id == task["created_by_user_id"]


def test_same_task_item_reservation_is_idempotent(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import CandidateJob, OutreachQuotaLedger, OutreachQuotaReservation, ScreeningTaskItem
    from resume_api.services.outreach_quota import reserve

    job = _job(client, auth_headers)
    candidate = _candidate(client, auth_headers, "quota-task-item")
    task_response = client.post(
        "/api/screening-tasks",
        headers=auth_headers,
        json={"job_id": job["id"], "requested_count": 2},
    )
    assert task_response.status_code == 201, task_response.text
    task = task_response.json()
    with db_mod.SessionLocal() as db:
        link = CandidateJob(candidate_id=candidate["id"], job_id=job["id"])
        db.add(link)
        db.flush()
        item = ScreeningTaskItem(
            task_id=task["id"],
            candidate_id=candidate["id"],
            candidate_job_id=link.id,
            position_index=1,
            status="eligible",
        )
        db.add(item)
        db.commit()
        item_id = item.id

    with db_mod.SessionLocal() as db:
        first = reserve(db, user_id=task["created_by_user_id"], task_id=task["id"], task_item_id=item_id, outreach_event_id=None)
        db.commit()
        first_id = first.id
    with db_mod.SessionLocal() as db:
        retry = reserve(db, user_id=task["created_by_user_id"], task_id=task["id"], task_item_id=item_id, outreach_event_id=None)
        db.commit()
        assert retry.id == first_id
        ledger = db.scalar(select(OutreachQuotaLedger))
        assert (ledger.confirmed_count, ledger.reserved_count) == (0, 1)
        assert len(db.scalars(select(OutreachQuotaReservation)).all()) == 1


def test_public_outreach_retry_for_task_item_returns_same_event(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import (
        CandidateJob,
        OutreachEvent,
        OutreachQuotaLedger,
        OutreachQuotaReservation,
        ScreeningTaskItem,
    )

    job = _job(client, auth_headers)
    candidate = _candidate(client, auth_headers, "public-task-item-idempotent")
    task = client.post(
        "/api/screening-tasks",
        headers=auth_headers,
        json={"job_id": job["id"], "requested_count": 1},
    ).json()
    with db_mod.SessionLocal() as db:
        link = CandidateJob(candidate_id=candidate["id"], job_id=job["id"])
        db.add(link)
        db.flush()
        item = ScreeningTaskItem(
            task_id=task["id"],
            candidate_id=candidate["id"],
            candidate_job_id=link.id,
            position_index=1,
            status="eligible",
        )
        db.add(item)
        db.commit()
        item_id = item.id

    payload = {
        "task_item_id": item_id,
        "job_id": job["id"],
        "message": "您好",
    }
    first = client.post("/api/outreach/reservations", headers=auth_headers, json=payload)
    retry = client.post("/api/outreach/reservations", headers=auth_headers, json=payload)

    assert first.status_code == retry.status_code == 201
    assert first.json()["idempotent_hit"] is False
    assert retry.json()["idempotent_hit"] is True
    assert retry.json()["id"] == first.json()["id"]
    with db_mod.SessionLocal() as db:
        assert len(db.scalars(select(OutreachEvent)).all()) == 1
        assert len(db.scalars(select(OutreachQuotaReservation)).all()) == 1
        ledger = db.scalar(select(OutreachQuotaLedger))
        assert (ledger.confirmed_count, ledger.reserved_count) == (0, 1)


def test_task_admission_accounts_for_uncontacted_nonterminal_batches(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import OutreachQuotaLedger

    first_job = _job(client, auth_headers)
    second_job = _job(client, auth_headers)
    accepted = client.post(
        "/api/screening-tasks",
        headers=auth_headers,
        json={"job_id": first_job["id"], "requested_count": 10},
    )
    assert accepted.status_code == 201, accepted.text
    with db_mod.SessionLocal() as db:
        ledger = db.scalar(select(OutreachQuotaLedger))
        ledger.confirmed_count = 185
        db.commit()
        assert (ledger.confirmed_count, ledger.reserved_count) == (185, 0)

    rejected = client.post(
        "/api/screening-tasks",
        headers=auth_headers,
        json={"job_id": second_job["id"], "requested_count": 10},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "outreach quota is insufficient for this batch"


def test_concurrent_reservations_contend_for_one_final_slot(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from resume_api.core.db import Base
    from resume_api.models import (
        Candidate,
        CandidateJob,
        JobPosting,
        OutreachQuotaLedger,
        ScreeningTask,
        ScreeningTaskItem,
        User,
    )
    from resume_api.services.outreach_quota import OutreachQuotaError, reserve

    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent-quota.db'}", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", lambda connection, _record: connection.execute("PRAGMA busy_timeout=5000"))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with sessions() as db:
        user = User(username="quota-owner", password_hash="hash", role="member")
        job = JobPosting(name="工程师", jd_text="Python")
        candidate1 = Candidate(fingerprint="concurrent-one", name="一")
        candidate2 = Candidate(fingerprint="concurrent-two", name="二")
        db.add_all([user, job, candidate1, candidate2])
        db.flush()
        task = ScreeningTask(
            job_id=job.id,
            created_by_user_id=user.id,
            requested_count=2,
            job_name_snapshot=job.name,
            jd_text_snapshot=job.jd_text,
            score_threshold_snapshot=80,
            greet_template_snapshot="您好",
            boss_entry_url_snapshot="",
        )
        db.add(task)
        db.flush()
        items = []
        for index, candidate in enumerate((candidate1, candidate2), start=1):
            link = CandidateJob(candidate_id=candidate.id, job_id=job.id)
            db.add(link)
            db.flush()
            item = ScreeningTaskItem(
                task_id=task.id,
                candidate_id=candidate.id,
                candidate_job_id=link.id,
                position_index=index,
                status="eligible",
            )
            db.add(item)
            items.append(item)
        db.add(OutreachQuotaLedger(user_id=user.id, hard_limit=200, confirmed_count=199, reserved_count=0))
        db.commit()
        user_id, task_id, item_ids = user.id, task.id, [item.id for item in items]

    barrier = Barrier(2)

    def attempt(item_id):
        with sessions() as db:
            barrier.wait()
            try:
                result = reserve(
                    db,
                    user_id=user_id,
                    task_id=task_id,
                    task_item_id=item_id,
                    outreach_event_id=None,
                )
                db.commit()
                return result.status
            except OutreachQuotaError:
                db.rollback()
                return "exhausted"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, item_ids))
    assert sorted(results) == ["exhausted", "reserved"]
    with sessions() as db:
        ledger = db.scalar(select(OutreachQuotaLedger).where(OutreachQuotaLedger.user_id == user_id))
        assert (ledger.confirmed_count, ledger.reserved_count) == (199, 1)
    engine.dispose()


def test_concurrent_task_admission_serializes_remaining_capacity(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from resume_api.core.db import Base
    from resume_api.models import JobPosting, OutreachQuotaLedger, User
    from resume_api.schemas import ScreeningTaskCreate
    from resume_api.services.screening_tasks import ScreeningTaskError, create_task

    engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrent-task-admission.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    event.listen(engine, "connect", lambda connection, _record: connection.execute("PRAGMA busy_timeout=5000"))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with sessions() as db:
        user = User(username="admission-owner", password_hash="hash", role="member")
        jobs = [
            JobPosting(name="岗位一", jd_text="Python"),
            JobPosting(name="岗位二", jd_text="Python"),
        ]
        db.add_all([user, *jobs])
        db.flush()
        db.add(OutreachQuotaLedger(user_id=user.id, hard_limit=200, confirmed_count=190, reserved_count=0))
        db.commit()
        user_id, job_ids = user.id, [job.id for job in jobs]

    barrier = Barrier(2)

    def attempt(job_id):
        with sessions() as db:
            barrier.wait()
            try:
                task = create_task(
                    db,
                    ScreeningTaskCreate(job_id=job_id, requested_count=10),
                    user_id=user_id,
                )
                return task.id
            except ScreeningTaskError as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, job_ids))
    assert sum(isinstance(result, int) and result not in {409} for result in results) == 1
    assert results.count(409) == 1
    with sessions() as db:
        tasks = db.query(__import__("resume_api.models", fromlist=["ScreeningTask"]).ScreeningTask).all()
        assert len(tasks) == 1
    engine.dispose()


def test_task_admission_does_not_double_count_processed_unknown_item(tmp_path):
    from resume_api.core.db import Base
    from resume_api.models import (
        Candidate,
        CandidateJob,
        JobPosting,
        OutreachQuotaLedger,
        OutreachQuotaReservation,
        ScreeningTask,
        ScreeningTaskItem,
        User,
    )
    from resume_api.services.outreach_quota import remaining_for_task_admission

    engine = create_engine(f"sqlite:///{tmp_path / 'unknown-task-capacity.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with sessions() as db:
        user = User(username="unknown-owner", password_hash="hash", role="member")
        job = JobPosting(name="工程师", jd_text="Python")
        candidate = Candidate(fingerprint="unknown-capacity", name="候选人")
        db.add_all([user, job, candidate])
        db.flush()
        task = ScreeningTask(
            job_id=job.id,
            created_by_user_id=user.id,
            requested_count=10,
            processed_count=1,
            status="running",
            job_name_snapshot=job.name,
            jd_text_snapshot=job.jd_text,
            score_threshold_snapshot=80,
            greet_template_snapshot="您好",
            boss_entry_url_snapshot="",
        )
        link = CandidateJob(candidate_id=candidate.id, job_id=job.id)
        db.add_all([task, link])
        db.flush()
        item = ScreeningTaskItem(
            task_id=task.id,
            candidate_id=candidate.id,
            candidate_job_id=link.id,
            position_index=1,
            status="needs_review",
        )
        db.add_all([
            item,
            OutreachQuotaLedger(
                user_id=user.id, hard_limit=200, confirmed_count=0, reserved_count=1
            ),
        ])
        db.flush()
        db.add(OutreachQuotaReservation(
            user_id=user.id,
            task_id=task.id,
            task_item_id=item.id,
            status="unknown",
        ))
        db.commit()

        # 200 - 1 reserved - 9 future batch seats = 190.
        # The unknown item is already included in processed_count and must not
        # consume a second seat when its reservation is also counted.
        assert remaining_for_task_admission(db, user.id) == 190
    engine.dispose()
