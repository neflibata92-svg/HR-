from __future__ import annotations


def _register(client, username: str, password: str = "secret12") -> tuple[dict, dict[str, str]]:
    response = client.post("/auth/register", json={"username": username, "password": password})
    assert response.status_code == 200
    tokens = response.json()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


def _create_ready_member(
    client,
    admin_headers: dict[str, str],
    username: str = "member",
) -> tuple[dict, dict[str, str]]:
    temporary_password = "tempPass8"
    new_password = "newPass88"
    created = client.post(
        "/auth/users",
        headers=admin_headers,
        json={"username": username, "temporary_password": temporary_password},
    )
    assert created.status_code == 201
    login = client.post(
        "/auth/login",
        json={"username": username, "password": temporary_password},
    )
    temporary_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    changed = client.post(
        "/auth/change-password",
        headers=temporary_headers,
        json={"current_password": temporary_password, "new_password": new_password},
    )
    assert changed.status_code == 200
    tokens = changed.json()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


def test_temporary_password_blocks_business_until_changed(client) -> None:
    _, admin_headers = _register(client, "admin")
    created = client.post(
        "/auth/users",
        headers=admin_headers,
        json={"username": "new.hr", "temporary_password": "tempPass8"},
    )
    assert created.status_code == 201

    login = client.post(
        "/auth/login",
        json={"username": "new.hr", "password": "tempPass8"},
    )
    assert login.status_code == 200
    temporary_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/auth/me", headers=temporary_headers).status_code == 200

    blocked = client.get("/api/jobs", headers=temporary_headers)
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "password change required"

    wrong_current = client.post(
        "/auth/change-password",
        headers=temporary_headers,
        json={"current_password": "wrongPass8", "new_password": "newPass88"},
    )
    same_password = client.post(
        "/auth/change-password",
        headers=temporary_headers,
        json={"current_password": "tempPass8", "new_password": "tempPass8"},
    )
    assert wrong_current.status_code == 400
    assert same_password.status_code == 400

    changed = client.post(
        "/auth/change-password",
        headers=temporary_headers,
        json={"current_password": "tempPass8", "new_password": "newPass88"},
    )
    assert changed.status_code == 200
    new_headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert client.get("/api/jobs", headers=new_headers).status_code == 200
    assert client.get("/auth/me", headers=new_headers).json()["must_change_password"] is False


def test_admin_reset_blocks_old_jwt_and_api_key_cannot_change_password(client) -> None:
    _, admin_headers = _register(client, "admin")
    _, member_headers = _create_ready_member(client, admin_headers)
    member = client.get("/auth/me", headers=member_headers).json()
    created_key = client.post("/auth/api-keys", headers=member_headers, json={"name": "agent"})
    assert created_key.status_code == 200
    key_headers = {"X-Api-Key": created_key.json()["api_key"]}

    reset = client.post(
        f"/auth/users/{member['id']}/reset-password",
        headers=admin_headers,
        json={"temporary_password": "resetPass8"},
    )
    assert reset.status_code == 200
    assert client.get("/api/jobs", headers=member_headers).status_code == 403
    assert client.get("/api/jobs", headers=key_headers).status_code == 403

    change_with_key = client.post(
        "/auth/change-password",
        headers=key_headers,
        json={"current_password": "resetPass8", "new_password": "newPass88"},
    )
    assert change_with_key.status_code == 403


def test_disable_invalidates_and_reenable_restores_existing_credentials(client) -> None:
    _, admin_headers = _register(client, "admin")
    tokens, member_headers = _create_ready_member(client, admin_headers)
    member = client.get("/auth/me", headers=member_headers).json()
    key_response = client.post("/auth/api-keys", headers=member_headers, json={"name": "agent"})
    key_headers = {"X-Api-Key": key_response.json()["api_key"]}

    disabled = client.patch(
        f"/auth/users/{member['id']}/status",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    assert client.get("/api/jobs", headers=member_headers).status_code == 401
    assert client.get("/api/jobs", headers=key_headers).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401

    enabled = client.patch(
        f"/auth/users/{member['id']}/status",
        headers=admin_headers,
        json={"is_active": True},
    )
    assert enabled.status_code == 200
    assert client.get("/api/jobs", headers=member_headers).status_code == 200
    assert client.get("/api/jobs", headers=key_headers).status_code == 200
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 200
