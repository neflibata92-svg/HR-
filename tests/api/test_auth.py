def test_register_login_me(client) -> None:
    registered = client.post(
        "/auth/register",
        json={"username": "alice", "password": "secret12"},
    )
    assert registered.status_code == 200
    tokens = registered.json()
    assert tokens["access_token"]
    assert tokens["token_type"] == "bearer"

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == "alice"
    assert me.json()["role"] == "admin"

    login = client.post(
        "/auth/login",
        json={"username": "alice", "password": "secret12"},
    )
    assert login.status_code == 200


def test_api_key_create_and_use(client) -> None:
    tokens = client.post(
        "/auth/register",
        json={"username": "bob", "password": "secret12"},
    ).json()
    bearer = {"Authorization": f"Bearer {tokens['access_token']}"}
    created = client.post("/auth/api-keys", headers=bearer, json={"name": "agent"})
    assert created.status_code == 200
    api_key = created.json()["api_key"]
    assert api_key.startswith("rs_")

    jobs = client.get("/api/jobs", headers={"X-Api-Key": api_key})
    assert jobs.status_code == 200

    key_id = created.json()["id"]
    revoked = client.delete(f"/auth/api-keys/{key_id}", headers=bearer)
    assert revoked.status_code == 200
    denied = client.get("/api/jobs", headers={"X-Api-Key": api_key})
    assert denied.status_code == 401


def test_unauthenticated_jobs(client) -> None:
    assert client.get("/api/jobs").status_code == 401
