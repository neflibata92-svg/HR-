from datetime import datetime, timedelta, timezone

from resume_api.core import db as db_mod
from resume_api.models import ExchangeEvent
from resume_api.services.events import is_exchange_blocked


def _create_candidate(client, auth_headers) -> int:
    response = client.post(
        "/api/candidates",
        headers=auth_headers,
        json={
            "fingerprint": "abc",
            "boss_id": "b1",
            "name": "张三",
            "age": 30,
            "years_of_experience": 4,
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_exchange_cooldown_api(client, auth_headers) -> None:
    candidate_id = _create_candidate(client, auth_headers)
    blocked = client.get(
        f"/api/candidates/{candidate_id}/exchange-blocked",
        headers=auth_headers,
    )
    assert blocked.json()["blocked"] is False

    marked = client.post(
        f"/api/candidates/{candidate_id}/exchanges",
        headers=auth_headers,
        json={"operator": "hr1", "type": "exchange"},
    )
    assert marked.status_code == 200
    blocked2 = client.get(
        f"/api/candidates/{candidate_id}/exchange-blocked",
        headers=auth_headers,
    )
    assert blocked2.json()["blocked"] is True


def test_exchange_boundary_days(client, auth_headers) -> None:
    candidate_id = _create_candidate(client, auth_headers)
    db = db_mod.SessionLocal()
    try:
        now = datetime(2026, 9, 16, tzinfo=timezone.utc)
        old = ExchangeEvent(
            candidate_id=candidate_id,
            operator="hr",
            type="forward",
            created_at=now - timedelta(days=30, seconds=1),
        )
        recent = ExchangeEvent(
            candidate_id=candidate_id,
            operator="hr",
            type="exchange",
            created_at=now - timedelta(days=29),
        )
        db.add(old)
        db.commit()
        assert is_exchange_blocked(db, candidate_id, days=30, now=now) is False
        db.add(recent)
        db.commit()
        assert is_exchange_blocked(db, candidate_id, days=30, now=now) is True
    finally:
        db.close()
