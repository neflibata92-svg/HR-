from resume_domain.decision import should_greet
from resume_domain.llm_schema import parse_llm_score_payload


def test_parse_valid_json() -> None:
    result = parse_llm_score_payload(
        '{"score": 85, "reason": "匹配", "evidence": ["Python"]}'
    )
    assert result.score == 85
    assert result.reason == "匹配"
    assert result.evidence == ["Python"]


def test_parse_rejects_out_of_range() -> None:
    try:
        parse_llm_score_payload('{"score": 120, "reason": "x", "evidence": []}')
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_should_greet_threshold() -> None:
    assert should_greet(80, 80) is True
    assert should_greet(79, 80) is False
