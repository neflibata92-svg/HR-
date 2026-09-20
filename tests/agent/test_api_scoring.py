from __future__ import annotations

from unittest.mock import Mock, patch

import httpx
import pytest

from resume_agent.api_client import ApiClient
from resume_agent.config import AgentSettings
from resume_agent.parse_page import RawCandidate
from resume_agent.pipeline import process_candidate


def _client() -> ApiClient:
    return ApiClient(
        AgentSettings(
            api_base_url="https://backend.example",
            api_key="personal-system-key",
        )
    )


def test_agent_requires_personal_system_key() -> None:
    with pytest.raises(ValueError, match="API_KEY"):
        ApiClient(AgentSettings(api_base_url="https://backend.example", api_key=""))


def test_agent_scores_only_through_backend_with_personal_system_key() -> None:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "score": 86,
        "reason": "匹配",
        "evidence": ["Python"],
        "model": "server-model",
    }
    http_client = Mock()
    http_client.__enter__ = Mock(return_value=http_client)
    http_client.__exit__ = Mock(return_value=False)
    http_client.post.return_value = response

    with patch("resume_agent.api_client.httpx.Client", return_value=http_client):
        result = _client().score_candidate("JD", "candidate summary")

    assert result.model == "server-model"
    call = http_client.post.call_args
    assert call.args[0] == "https://backend.example/api/scoring/evaluate"
    assert call.kwargs["headers"] == {"X-Api-Key": "personal-system-key"}
    assert call.kwargs["json"] == {"jd": "JD", "summary": "candidate summary"}


@pytest.mark.parametrize("status_code", [401, 502])
def test_backend_errors_become_score_error(status_code: int) -> None:
    request = httpx.Request("POST", "https://backend.example/api/scoring/evaluate")
    response = httpx.Response(status_code, request=request)
    http_client = Mock()
    http_client.__enter__ = Mock(return_value=http_client)
    http_client.__exit__ = Mock(return_value=False)
    http_client.post.return_value = response

    with patch("resume_agent.api_client.httpx.Client", return_value=http_client):
        result = process_candidate(
            RawCandidate("1", "王", "公司", 30, 4, 2, 4),
            jd_text="JD",
            threshold=80,
            greet_template="hi",
            exchanged_within_30_days=False,
            already_greeted=False,
            scorer=_client(),
        )

    assert result.action == "score_error"


def test_timeout_becomes_score_error_and_hard_filter_reject_skips_backend() -> None:
    request = httpx.Request("POST", "https://backend.example/api/scoring/evaluate")
    http_client = Mock()
    http_client.__enter__ = Mock(return_value=http_client)
    http_client.__exit__ = Mock(return_value=False)
    http_client.post.side_effect = httpx.ReadTimeout("timeout", request=request)

    with patch("resume_agent.api_client.httpx.Client", return_value=http_client):
        timeout_result = process_candidate(
            RawCandidate("1", "王", "公司", 30, 4, 2, 4),
            jd_text="JD",
            threshold=80,
            greet_template="hi",
            exchanged_within_30_days=False,
            already_greeted=False,
            scorer=_client(),
        )
    assert timeout_result.action == "score_error"

    http_client.post.reset_mock()
    with patch("resume_agent.api_client.httpx.Client", return_value=http_client):
        rejected = process_candidate(
            RawCandidate("2", "赵", "公司", 40, 4, 2, 4),
            jd_text="JD",
            threshold=80,
            greet_template="hi",
            exchanged_within_30_days=False,
            already_greeted=False,
            scorer=_client(),
        )
    assert rejected.action == "hard_filter_reject"
    http_client.post.assert_not_called()
