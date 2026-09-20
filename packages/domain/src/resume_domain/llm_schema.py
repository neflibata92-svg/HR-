"""LLM 打分结果 schema。"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, ValidationError


class LlmScoreResult(BaseModel):
    """大模型返回的结构化打分。"""

    score: int = Field(ge=0, le=100)
    reason: str
    evidence: list[str] = Field(default_factory=list)
    model: str = ""


def parse_llm_score_payload(raw: str) -> LlmScoreResult:
    """解析并校验 LLM JSON；非法则抛 ValueError。"""

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {exc}") from exc
    try:
        return LlmScoreResult.model_validate(data)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
