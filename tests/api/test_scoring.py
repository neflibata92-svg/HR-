from __future__ import annotations

from unittest.mock import Mock, patch

from resume_api.services.llm import LlmNotConfiguredError, LlmUpstreamError
from resume_domain.llm_schema import LlmScoreResult


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
    tokens = changed.json()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


def test_requires_authentication_and_rejects_blank_input(client) -> None:
    assert client.post("/api/scoring/evaluate", json={"jd": "JD", "summary": "candidate"}).status_code == 401

    _, headers = _register(client, "admin")
    for payload in (
        {"jd": "", "summary": "candidate"},
        {"jd": "   ", "summary": "candidate"},
        {"jd": "JD", "summary": "   "},
        {"jd": "JD", "summary": "candidate", "api_key": "forbidden"},
    ):
        assert client.post("/api/scoring/evaluate", headers=headers, json=payload).status_code == 422


def test_personal_api_key_scores_and_response_has_only_public_fields(client) -> None:
    _, headers = _register(client, "admin")
    key = client.post("/auth/api-keys", headers=headers, json={"name": "agent"}).json()["api_key"]
    score = LlmScoreResult(
        score=88,
        reason="匹配",
        evidence=["Python"],
        missing_fields=["portfolio"],
        estimated_fields=["team_size"],
        critical_fields=[],
        confidence=0.9,
        decision="eligible",
        model="provider-model",
    )

    with patch("resume_api.routers.scoring.llm_service.score_candidate", return_value=score) as mocked:
        response = client.post(
            "/api/scoring/evaluate",
            headers={"X-Api-Key": key},
            json={"jd": "Python JD", "summary": "candidate"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "score": 88,
        "reason": "匹配",
        "evidence": ["Python"],
        "missing_fields": ["portfolio"],
        "estimated_fields": ["team_size"],
        "critical_fields": [],
        "confidence": 0.9,
        "decision": "eligible",
        "model": "provider-model",
    }
    assert set(response.json()) == {
        "score", "reason", "evidence", "missing_fields", "estimated_fields",
        "critical_fields", "confidence", "decision", "model",
    }
    assert mocked.call_args.args[1:] == ("Python JD", "candidate")
    assert mocked.call_args.kwargs == {}


def test_server_ignores_legacy_critical_fields_and_uses_score_threshold(
    client,
) -> None:
    _, headers = _register(client, "decision-admin")
    score = LlmScoreResult(
        score=95,
        reason="高分匹配",
        evidence=["Python"],
        missing_fields=["degree"],
        estimated_fields=[],
        critical_fields=[
            {
                "key": "degree",
                "label": "学历",
                "present": False,
                "evidence": "",
            }
        ],
        confidence=0.9,
        decision="below_threshold",
        model="provider-model",
    )
    with patch("resume_api.routers.scoring.llm_service.score_candidate", return_value=score):
        response = client.post(
            "/api/scoring/evaluate",
            headers=headers,
            json={
                "jd": "Python JD",
                "summary": "candidate",
                "critical_fields": [{"key": "degree", "label": "学历"}],
                "threshold": 80,
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "eligible"
    assert response.json()["critical_fields"] == []


def test_server_accepts_score_when_legacy_critical_field_is_omitted(client) -> None:
    _, headers = _register(client, "missing-key-admin")
    score = LlmScoreResult(
        score=95,
        reason="按 JD 匹配",
        evidence=["Python"],
        missing_fields=[],
        estimated_fields=[],
        critical_fields=[],
        confidence=0.9,
        decision="eligible",
        model="provider-model",
    )
    with patch("resume_api.routers.scoring.llm_service.score_candidate", return_value=score):
        response = client.post(
            "/api/scoring/evaluate",
            headers=headers,
            json={
                "jd": "Python JD",
                "summary": "candidate",
                "critical_fields": [{"key": "degree", "label": "学历"}],
                "threshold": 80,
            },
        )
    assert response.status_code == 200
    assert response.json()["decision"] == "eligible"


def test_account_and_key_status_are_enforced(client) -> None:
    _, admin_headers = _register(client, "admin")
    _, member_headers = _create_ready_member(client, admin_headers)
    member = client.get("/auth/me", headers=member_headers).json()
    key_response = client.post("/auth/api-keys", headers=member_headers, json={"name": "agent"})
    key_id = key_response.json()["id"]
    key_headers = {"X-Api-Key": key_response.json()["api_key"]}

    client.patch(
        f"/auth/users/{member['id']}/status",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert client.post("/api/scoring/evaluate", headers=key_headers, json={"jd": "JD", "summary": "x"}).status_code == 401

    client.patch(
        f"/auth/users/{member['id']}/status",
        headers=admin_headers,
        json={"is_active": True},
    )
    client.delete(f"/auth/api-keys/{key_id}", headers=member_headers)
    assert client.post("/api/scoring/evaluate", headers=key_headers, json={"jd": "JD", "summary": "x"}).status_code == 401


def test_temporary_password_is_forbidden(client) -> None:
    _, admin_headers = _register(client, "admin")
    created = client.post(
        "/auth/users",
        headers=admin_headers,
        json={"username": "temporary", "temporary_password": "tempPass8"},
    ).json()
    login = client.post("/auth/login", json={"username": created["username"], "password": "tempPass8"}).json()

    response = client.post(
        "/api/scoring/evaluate",
        headers={"Authorization": f"Bearer {login['access_token']}"},
        json={"jd": "JD", "summary": "candidate"},
    )
    assert response.status_code == 403


def test_maps_provider_errors_without_leaking_provider_key(client) -> None:
    _, headers = _register(client, "admin")
    for error, status_code in (
        (LlmUpstreamError("provider-secret-key failed"), 502),
        (LlmNotConfiguredError("provider-secret-key missing"), 503),
    ):
        with patch("resume_api.routers.scoring.llm_service.score_candidate", side_effect=error):
            response = client.post(
                "/api/scoring/evaluate",
                headers=headers,
                json={"jd": "JD", "summary": "candidate"},
            )
        assert response.status_code == status_code
        assert "provider-secret-key" not in response.text
