from __future__ import annotations

from resume_api.core import db as db_mod
from resume_api.models import Candidate, CandidateMergeSuggestion


def _create_candidate(client, headers, **overrides):
    payload = {
        "fingerprint": "fingerprint-default",
        "boss_id": None,
        "name": "候选人",
    }
    payload.update(overrides)
    response = client.post("/api/candidates", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_normalizes_phone_and_email(client, auth_headers) -> None:
    candidate = _create_candidate(
        client,
        auth_headers,
        fingerprint="identity-1",
        boss_id="  ",
        phone=" +86 138-0013-8000 ",
        email="  USER@Example.COM ",
    )

    assert candidate["boss_id"] is None
    assert candidate["phone_normalized"] == "13800138000"
    assert candidate["email_normalized"] == "user@example.com"


def test_matching_contact_creates_suggestion_without_silent_merge(client, auth_headers) -> None:
    first = _create_candidate(
        client,
        auth_headers,
        fingerprint="identity-first",
        boss_id="boss-first",
        name="甲",
        phone="13800138000",
    )
    second = _create_candidate(
        client,
        auth_headers,
        fingerprint="identity-second",
        boss_id="boss-second",
        name="乙",
        phone="+86 138 0013 8000",
    )

    assert first["id"] != second["id"]
    db = db_mod.SessionLocal()
    try:
        suggestions = db.query(CandidateMergeSuggestion).all()
        assert len(suggestions) == 1
        assert {suggestions[0].source_candidate_id, suggestions[0].target_candidate_id} == {
            first["id"],
            second["id"],
        }
        assert "phone" in suggestions[0].match_reason_json
    finally:
        db.close()


def test_blank_boss_id_does_not_create_a_stable_identity(client, auth_headers) -> None:
    first = _create_candidate(
        client,
        auth_headers,
        fingerprint="blank-boss-first",
        boss_id="",
        name="同名候选人",
    )
    second = _create_candidate(
        client,
        auth_headers,
        fingerprint="blank-boss-second",
        boss_id="   ",
        name="同名候选人",
    )

    assert first["id"] != second["id"]
    assert first["boss_id"] is None
    assert second["boss_id"] is None


def test_same_weak_fingerprint_with_different_boss_ids_stays_separate(
    client, auth_headers
) -> None:
    first = _create_candidate(
        client,
        auth_headers,
        fingerprint="same-name-company",
        boss_id="boss-one",
        name="同名甲",
    )
    second = _create_candidate(
        client,
        auth_headers,
        fingerprint="same-name-company",
        boss_id="boss-two",
        name="同名乙",
    )

    assert first["id"] != second["id"]
    assert first["boss_id"] == "boss-one"
    assert second["boss_id"] == "boss-two"



def test_upsert_through_merged_source_returns_target(client, auth_headers) -> None:
    source = _create_candidate(
        client,
        auth_headers,
        fingerprint="merged-source",
        boss_id="boss-source",
        name="来源",
    )
    target = _create_candidate(
        client,
        auth_headers,
        fingerprint="merged-target",
        boss_id="boss-target",
        name="目标",
    )
    db = db_mod.SessionLocal()
    try:
        source_row = db.get(Candidate, source["id"])
        source_row.merged_into_candidate_id = target["id"]
        db.commit()
    finally:
        db.close()

    updated = _create_candidate(
        client,
        auth_headers,
        fingerprint="merged-source",
        boss_id="boss-source",
        name="更新后的目标",
    )

    assert updated["id"] == target["id"]
    assert updated["name"] == "更新后的目标"
    assert updated["boss_id"] == "boss-target"
    assert updated["fingerprint"] == "merged-target"

    original_target = _create_candidate(
        client,
        auth_headers,
        fingerprint="merged-target",
        boss_id="boss-target",
        name="仍是同一目标",
    )
    assert original_target["id"] == target["id"]
