"""简历筛选领域逻辑包。"""

from resume_domain.decision import should_greet
from resume_domain.fingerprint import candidate_fingerprint
from resume_domain.hard_filter import CandidateSnapshot, HardFilterResult, apply_hard_filter
from resume_domain.llm_schema import LlmScoreResult, parse_llm_score_payload

__all__ = [
    "CandidateSnapshot",
    "HardFilterResult",
    "LlmScoreResult",
    "apply_hard_filter",
    "candidate_fingerprint",
    "parse_llm_score_payload",
    "should_greet",
]
