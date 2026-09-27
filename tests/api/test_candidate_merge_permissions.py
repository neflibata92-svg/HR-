from __future__ import annotations


def _register_admin(client):
    response = client.post("/auth/register", json={"username": "admin", "password": "secret12"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _ready_user(client, admin_headers, username: str, role: str):
    temporary = "tempPass8"
    created = client.post(
        "/auth/users", headers=admin_headers,
        json={"username": username, "temporary_password": temporary, "role": role},
    )
    assert created.status_code == 201
    login = client.post("/auth/login", json={"username": username, "password": temporary}).json()
    changed = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {login['access_token']}"},
        json={"current_password": temporary, "new_password": "newPass88"},
    )
    return {"Authorization": f"Bearer {changed.json()['access_token']}"}


def _candidates(client, headers):
    rows = []
    for suffix in ("a", "b"):
        response = client.post(
            "/api/candidates", headers=headers,
            json={"fingerprint": f"permission-{suffix}", "boss_id": f"permission-{suffix}", "name": suffix},
        )
        assert response.status_code == 200
        rows.append(response.json())
    return rows


def test_member_can_suggest_but_cannot_preview_execute_or_revert(client) -> None:
    admin = _register_admin(client)
    member = _ready_user(client, admin, "member", "member")
    source, target = _candidates(client, admin)
    payload = {"source_candidate_id": source["id"], "target_candidate_id": target["id"], "field_choices": {}}

    suggestion = client.post(
        "/api/candidate-merges/suggestions", headers=member,
        json={"source_candidate_id": source["id"], "target_candidate_id": target["id"], "reasons": ["人工判断"]},
    )
    assert suggestion.status_code == 201, suggestion.text
    assert client.post("/api/candidate-merges/preview", headers=member, json=payload).status_code == 403
    assert client.post("/api/candidate-merges", headers=member, json=payload).status_code == 403
    assert client.post("/api/candidate-merges/999/revert", headers=member).status_code == 403


def test_lead_and_admin_can_preview_execute_and_revert(client) -> None:
    admin = _register_admin(client)
    lead = _ready_user(client, admin, "lead", "lead")
    source, target = _candidates(client, admin)
    payload = {"source_candidate_id": source["id"], "target_candidate_id": target["id"], "field_choices": {}}

    preview = client.post("/api/candidate-merges/preview", headers=lead, json=payload)
    assert preview.status_code == 200, preview.text
    merged = client.post("/api/candidate-merges", headers=admin, json=payload)
    assert merged.status_code == 201, merged.text
    reverted = client.post(f"/api/candidate-merges/{merged.json()['id']}/revert", headers=lead)
    assert reverted.status_code == 200, reverted.text
