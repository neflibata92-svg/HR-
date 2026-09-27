from __future__ import annotations

from sqlalchemy import func, select


def _task(client, headers):
    job = client.post(
        "/api/jobs", headers=headers, json={"name": "筛选记录岗位", "jd_text": "Python"}
    ).json()
    task = client.post(
        "/api/screening-tasks",
        headers=headers,
        json={
            "job_id": job["id"],
            "requested_count": 5,
            "critical_fields": [{"key": "degree", "label": "学历"}],
            "critical_fields_source": {"confirmed": True, "source": "manual"},
        },
    ).json()
    client.post(
        f"/api/screening-tasks/{task['id']}/claim",
        headers=headers,
        json={"machine_id": "record-agent"},
    )
    return task, job


def test_screening_record_does_not_create_candidate_and_is_idempotent(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import Candidate, ScreeningRecord

    task, job = _task(client, auth_headers)
    payload = {
        "machine_id": "record-agent",
        "boss_id": "boss-record-1",
        "fingerprint": "fingerprint-record-1",
        "display_name": "未联系人员",
        "source_payload": {
            "age": 28,
            "years_of_experience": 5,
            "job_segments": [{"company": "示例公司"}],
        },
        "position_index": 1,
    }
    first = client.post(
        f"/api/screening-tasks/{task['id']}/records", headers=auth_headers, json=payload
    )
    second = client.post(
        f"/api/screening-tasks/{task['id']}/records", headers=auth_headers, json=payload
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    assert first.json()["candidate_id"] is None
    assert first.json()["job_id"] == job["id"]

    with db_mod.SessionLocal() as db:
        assert db.scalar(select(func.count(Candidate.id))) == 0
        record = db.get(ScreeningRecord, first.json()["id"])
        assert record is not None
        assert record.status == "discovered"


def test_non_contact_results_remain_screening_records_only(client, auth_headers):
    from resume_api.core import db as db_mod
    from resume_api.models import Candidate, ScreeningRecord

    task, _ = _task(client, auth_headers)
    statuses = ("below_threshold", "needs_review", "failed", "duplicate_contact")
    for index, record_status in enumerate(statuses, start=1):
        created = client.post(
            f"/api/screening-tasks/{task['id']}/records",
            headers=auth_headers,
            json={
                "machine_id": "record-agent",
                "fingerprint": f"record-{index}",
                "display_name": f"人员{index}",
                "source_payload": {},
                "position_index": index,
            },
        ).json()
        response = client.post(
            f"/api/screening-tasks/{task['id']}/records/{created['id']}/complete",
            headers=auth_headers,
            json={"machine_id": "record-agent", "status": record_status},
        )
        assert response.status_code == 200, response.text

    with db_mod.SessionLocal() as db:
        assert db.scalar(select(func.count(Candidate.id))) == 0
        assert db.scalar(select(func.count(ScreeningRecord.id))) == len(statuses)
