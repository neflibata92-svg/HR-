from __future__ import annotations


def _register(client, username: str, password: str = "secret12") -> dict[str, str]:
    response = client.post("/auth/register", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_ready_member(
    client,
    admin_headers: dict[str, str],
    username: str = "member",
) -> dict[str, str]:
    temporary_password = "tempPass8"
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
        json={"current_password": temporary_password, "new_password": "newPass88"},
    )
    assert changed.status_code == 200
    return {"Authorization": f"Bearer {changed.json()['access_token']}"}


def test_admin_lists_and_creates_member_with_temporary_password(client) -> None:
    admin_headers = _register(client, "admin")

    created = client.post(
        "/auth/users",
        headers=admin_headers,
        json={"username": "  LiSi  ", "temporary_password": "tempPass8"},
    )

    assert created.status_code == 201
    assert created.json()["username"] == "lisi"
    assert created.json()["role"] == "member"
    assert created.json()["is_active"] is True
    assert created.json()["must_change_password"] is True
    assert created.json()["created_at"]

    listed = client.get("/auth/users", headers=admin_headers)
    assert listed.status_code == 200
    assert [user["username"] for user in listed.json()] == ["admin", "lisi"]


def test_admin_create_rejects_role_blank_and_normalized_duplicate(client) -> None:
    admin_headers = _register(client, "admin")

    role_injection = client.post(
        "/auth/users",
        headers=admin_headers,
        json={
            "username": "other-admin",
            "temporary_password": "tempPass8",
            "role": "admin",
        },
    )
    assert role_injection.status_code == 422

    blank = client.post(
        "/auth/users",
        headers=admin_headers,
        json={"username": "   ", "temporary_password": "tempPass8"},
    )
    assert blank.status_code == 422

    first = client.post(
        "/auth/users",
        headers=admin_headers,
        json={"username": "LiSi", "temporary_password": "tempPass8"},
    )
    duplicate = client.post(
        "/auth/users",
        headers=admin_headers,
        json={"username": " lisi ", "temporary_password": "tempPass9"},
    )
    assert first.status_code == 201
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"] == "username taken"


def test_member_cannot_use_account_management_endpoints(client) -> None:
    admin_headers = _register(client, "admin")
    member_headers = _create_ready_member(client, admin_headers)
    admin_id = client.get("/auth/me", headers=admin_headers).json()["id"]

    responses = [
        client.get("/auth/users", headers=member_headers),
        client.post(
            "/auth/users",
            headers=member_headers,
            json={"username": "blocked", "temporary_password": "tempPass8"},
        ),
        client.patch(
            f"/auth/users/{admin_id}/status",
            headers=member_headers,
            json={"is_active": False},
        ),
        client.post(
            f"/auth/users/{admin_id}/reset-password",
            headers=member_headers,
            json={"temporary_password": "resetPass8"},
        ),
    ]

    assert [response.status_code for response in responses] == [403, 403, 403, 403]


def test_admin_status_and_password_reset_rules(client) -> None:
    admin_headers = _register(client, "admin")
    created = client.post(
        "/auth/users",
        headers=admin_headers,
        json={"username": "managed", "temporary_password": "tempPass8"},
    ).json()
    user_id = created["id"]
    admin_id = client.get("/auth/me", headers=admin_headers).json()["id"]

    disabled = client.patch(
        f"/auth/users/{user_id}/status",
        headers=admin_headers,
        json={"is_active": False},
    )
    disabled_again = client.patch(
        f"/auth/users/{user_id}/status",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    assert disabled_again.status_code == 200
    assert disabled_again.json()["is_active"] is False

    reset = client.post(
        f"/auth/users/{user_id}/reset-password",
        headers=admin_headers,
        json={"temporary_password": "resetPass8"},
    )
    assert reset.status_code == 200
    assert reset.json()["must_change_password"] is True

    missing = client.patch(
        "/auth/users/999999/status",
        headers=admin_headers,
        json={"is_active": False},
    )
    admin_status = client.patch(
        f"/auth/users/{admin_id}/status",
        headers=admin_headers,
        json={"is_active": False},
    )
    admin_reset = client.post(
        f"/auth/users/{admin_id}/reset-password",
        headers=admin_headers,
        json={"temporary_password": "resetPass8"},
    )
    assert missing.status_code == 404
    assert admin_status.status_code == 403
    assert admin_reset.status_code == 403
