from __future__ import annotations

from unittest.mock import Mock, patch

import httpx
import pytest

from resume_api.core.config import Settings
from resume_api.services.llm import (
    LlmNotConfiguredError,
    LlmUpstreamError,
    score_candidate,
)


def _settings(**overrides) -> Settings:
    values = {
        "llm_base_url": "https://llm.example/v1",
        "llm_api_key": "provider-secret-key",
        "llm_model": "provider-model",
        "llm_timeout_seconds": 12.0,
        "llm_max_attempts": 3,
    }
    values.update(overrides)
    return Settings(**values)


def _response(content: str) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"message": {"content": content}}],
    }
    return response


def test_uses_server_provider_config_and_parses_valid_json() -> None:
    client = Mock()
    client.post.return_value = _response(
        '{"score":91,"reason":"经验匹配","evidence":["Python"],'
        '"missing_fields":[],"estimated_fields":[],"critical_fields":[],'
        '"confidence":0.9,"decision":"eligible"}'
    )

    result = score_candidate(_settings(), "Python JD", "候选人摘要", client=client)

    assert result.score == 91
    assert result.reason == "经验匹配"
    assert result.evidence == ["Python"]
    assert result.model == "provider-model"
    url = client.post.call_args.args[0]
    kwargs = client.post.call_args.kwargs
    assert url == "https://llm.example/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer provider-secret-key"
    assert kwargs["json"]["model"] == "provider-model"
    assert kwargs["timeout"] == 12.0
    messages = kwargs["json"]["messages"]
    assert "关键资料" not in messages[0]["content"]
    assert "关键资料" not in messages[1]["content"]
    assert "Python JD" in messages[1]["content"]
    assert "候选人摘要" in messages[1]["content"]


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        '{"score":101,"reason":"invalid","evidence":[],"missing_fields":[],'
        '"estimated_fields":[],"critical_fields":[],"confidence":0.5,'
        '"decision":"eligible"}',
    ],
)
def test_invalid_provider_payload_retries_and_becomes_safe_upstream_error(content: str) -> None:
    client = Mock()
    client.post.return_value = _response(content)

    with pytest.raises(LlmUpstreamError) as caught:
        score_candidate(_settings(), "JD", "summary", client=client)

    assert client.post.call_count == 3
    assert "provider-secret-key" not in str(caught.value)


def test_http_failure_attempts_at_most_three_times_without_leaking_key() -> None:
    request = httpx.Request("POST", "https://llm.example/v1/chat/completions")
    client = Mock()
    client.post.side_effect = httpx.ConnectError("provider-secret-key failed", request=request)

    with pytest.raises(LlmUpstreamError) as caught:
        score_candidate(_settings(), "JD", "summary", client=client)

    assert client.post.call_count == 3
    assert "provider-secret-key" not in str(caught.value)


def test_retry_configuration_cannot_exceed_three_provider_calls() -> None:
    request = httpx.Request("POST", "https://llm.example/v1/chat/completions")
    client = Mock()
    client.post.side_effect = httpx.ConnectError("failed", request=request)

    with pytest.raises(LlmUpstreamError):
        score_candidate(_settings(llm_max_attempts=10), "JD", "summary", client=client)

    assert client.post.call_count == 3


def test_missing_key_fails_without_calling_provider_or_returning_placeholder() -> None:
    client = Mock()

    with pytest.raises(LlmNotConfiguredError):
        score_candidate(_settings(llm_api_key=""), "JD", "summary", client=client)

    client.post.assert_not_called()
