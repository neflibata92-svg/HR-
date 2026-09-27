from __future__ import annotations

import pytest

from resume_domain.llm_schema import (
    CriticalFieldSuggestionResult,
    LlmScoreResult,
    parse_critical_field_suggestions,
    parse_llm_score_payload,
)


def _score_payload(**overrides) -> dict:
    payload = {
        "score": 85,
        "reason": "匹配",
        "evidence": ["具备 Python 项目经验"],
        "missing_fields": ["portfolio"],
        "estimated_fields": ["team_size"],
        "critical_fields": [
            {"key": "python", "label": "Python 经验", "present": True, "evidence": "项目经历"},
            {"key": "degree", "label": "学历", "present": False, "evidence": ""},
        ],
        "confidence": 0.8,
        "decision": "needs_review",
    }
    payload.update(overrides)
    return payload


def test_parse_complete_strict_score_payload() -> None:
    import json

    result = parse_llm_score_payload(json.dumps(_score_payload(), ensure_ascii=False))
    assert result.score == 85
    assert result.missing_fields == ["portfolio"]
    assert result.estimated_fields == ["team_size"]
    assert result.critical_fields[1].present is False
    assert result.confidence == 0.8
    assert result.decision == "needs_review"


@pytest.mark.parametrize(
    "overrides",
    [
        {"score": 101},
        {"confidence": 1.1},
        {"decision": "contact"},
        {"unexpected": True},
    ],
)
def test_score_payload_rejects_invalid_or_extra_fields(overrides) -> None:
    import json

    with pytest.raises(ValueError):
        parse_llm_score_payload(json.dumps(_score_payload(**overrides), ensure_ascii=False))


def test_score_result_preserves_server_model() -> None:
    result = LlmScoreResult(**_score_payload(), model="provider-model")
    assert result.model_dump()["model"] == "provider-model"


def test_critical_field_suggestions_require_stable_unique_keys() -> None:
    raw = '{"suggestions":[{"key":"python_experience","label":"Python经验","reason":"岗位明确要求"}]}'
    result = parse_critical_field_suggestions(raw)
    assert isinstance(result, CriticalFieldSuggestionResult)
    assert result.suggestions[0].key == "python_experience"

    duplicate = '{"suggestions":[{"key":"python","label":"Python","reason":"要求"},{"key":"python","label":"重复","reason":"重复"}]}'
    with pytest.raises(ValueError):
        parse_critical_field_suggestions(duplicate)


@pytest.mark.parametrize("raw", ["not-json", "```json\n{}\n```", '{"suggestions":[],"extra":1}'])
def test_critical_field_suggestions_never_accept_placeholder_or_wrapped_output(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_critical_field_suggestions(raw)
