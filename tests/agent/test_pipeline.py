from resume_domain.llm_schema import LlmScoreResult
from resume_agent.parse_page import RawCandidate
from resume_agent.pipeline import process_candidate


class FakeScorer:
    def __init__(self, score: int) -> None:
        self.score = score
        self.called = False

    def score_candidate(self, jd: str, summary: str) -> LlmScoreResult:
        self.called = True
        return LlmScoreResult(
            score=self.score,
            reason="ok",
            evidence=["x"],
            model="server-model",
        )


class FakeGreeter:
    def __init__(self) -> None:
        self.called = False

    def greet(self, candidate: RawCandidate, message: str) -> bool:
        self.called = True
        return True


def _ok_candidate() -> RawCandidate:
    return RawCandidate(
        boss_id="1",
        name="王合格",
        org="公司",
        age=30,
        years=4,
        segments=3,
        total_years=4,
    )


def test_pipeline_greets_when_score_high() -> None:
    greeter = FakeGreeter()
    result = process_candidate(
        _ok_candidate(),
        jd_text="JD",
        threshold=80,
        greet_template="hi",
        exchanged_within_30_days=False,
        already_greeted=False,
        scorer=FakeScorer(85),
        greeter=greeter,
    )
    assert result.action == "greeted"
    assert result.model == "server-model"
    assert greeter.called is True


def test_pipeline_hard_filter() -> None:
    bad = RawCandidate("2", "赵", "公司", 40, 4, 2, 4)
    scorer = FakeScorer(99)
    result = process_candidate(
        bad,
        jd_text="JD",
        threshold=80,
        greet_template="hi",
        exchanged_within_30_days=False,
        already_greeted=False,
        scorer=scorer,
        greeter=None,
    )
    assert result.action == "hard_filter_reject"
    assert "age" in result.reasons
    assert scorer.called is False
