from resume_domain.llm_schema import LlmScoreResult
from resume_agent.llm import LlmScorer
from resume_agent.config import AgentSettings


def test_llm_placeholder_without_key() -> None:
    scorer = LlmScorer(AgentSettings(llm_api_key=""))
    result = scorer.score_candidate("JD", "候选人")
    assert isinstance(result, LlmScoreResult)
    assert result.score == 80
