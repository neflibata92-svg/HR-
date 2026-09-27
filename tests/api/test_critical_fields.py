from __future__ import annotations

from unittest.mock import patch

import pytest

from resume_api.services.llm import LlmNotConfiguredError, LlmUpstreamError
from resume_domain.llm_schema import CriticalFieldSuggestion, CriticalFieldSuggestionResult


@pytest.mark.parametrize("threshold", [0, 100])
def test_job_score_threshold_boundaries_are_accepted(client, auth_headers, threshold: int) -> None:
    response = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"name": f"岗位{threshold}", "jd_text": "Python", "score_threshold": threshold},
    )
    assert response.status_code == 201, response.text


@pytest.mark.parametrize("threshold", [-1, 101])
def test_job_score_threshold_outside_range_is_rejected(client, auth_headers, threshold: int) -> None:
    response = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"name": "岗位", "jd_text": "Python", "score_threshold": threshold},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "template",
    [
        "您好 {{candidate_name}}，这是 {{job_name}} 岗位",
        "不使用变量的固定文本",
    ],
)
def test_greet_template_accepts_only_supported_variables(client, auth_headers, template: str) -> None:
    response = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"name": "岗位", "jd_text": "Python", "greet_template": template},
    )
    assert response.status_code == 201, response.text


@pytest.mark.parametrize("template", ["您好 {{email}}", "您好 {{candidate}}", "您好 {{candidate_name}"])
def test_greet_template_rejects_unknown_or_unclosed_variables(client, auth_headers, template: str) -> None:
    response = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"name": "岗位", "jd_text": "Python", "greet_template": template},
    )
    assert response.status_code == 422


def test_critical_field_suggestions_come_from_llm_without_fake_fallback(client, auth_headers) -> None:
    job = client.post(
        "/api/jobs", headers=auth_headers, json={"name": "后端", "jd_text": "Python FastAPI"}
    ).json()
    suggestion = CriticalFieldSuggestionResult(
        suggestions=[
            CriticalFieldSuggestion(
                key="python_experience", label="Python经验", reason="岗位明确要求"
            )
        ],
        model="provider-model",
    )
    with patch(
        "resume_api.routers.jobs.llm_service.suggest_critical_fields",
        return_value=suggestion,
    ):
        response = client.post(
            f"/api/jobs/{job['id']}/critical-fields/suggest", headers=auth_headers
        )
    assert response.status_code == 200, response.text
    assert response.json() == suggestion.model_dump()

    for error, expected in (
        (LlmNotConfiguredError("secret"), 503),
        (LlmUpstreamError("secret"), 502),
    ):
        with patch(
            "resume_api.routers.jobs.llm_service.suggest_critical_fields",
            side_effect=error,
        ):
            failed = client.post(
                f"/api/jobs/{job['id']}/critical-fields/suggest", headers=auth_headers
            )
        assert failed.status_code == expected
        assert "secret" not in failed.text
        assert "suggestions" not in failed.text
