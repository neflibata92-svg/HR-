"""LLM 评分与关键资料建议的严格结构。"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class CriticalFieldResult(BaseModel):
    """单项关键资料在候选人资料中的判断。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    present: bool
    evidence: str


class LlmScoreResult(BaseModel):
    """大模型返回的完整结构化打分。"""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1)
    evidence: list[str]
    missing_fields: list[str]
    estimated_fields: list[str]
    critical_fields: list[CriticalFieldResult]
    confidence: float = Field(ge=0, le=1)
    decision: Literal["eligible", "needs_review", "below_threshold", "error"]
    model: str = ""


class CriticalFieldSuggestion(BaseModel):
    """供 HR 确认的一项关键资料建议。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class CriticalFieldSuggestionResult(BaseModel):
    """关键资料建议结果。"""

    model_config = ConfigDict(extra="forbid")

    suggestions: list[CriticalFieldSuggestion] = Field(min_length=1)
    model: str = ""

    @field_validator("suggestions")
    @classmethod
    def require_unique_keys(
        cls, values: list[CriticalFieldSuggestion]
    ) -> list[CriticalFieldSuggestion]:
        keys = [item.key for item in values]
        if len(keys) != len(set(keys)):
            raise ValueError("suggestion keys must be unique")
        return values


def _parse(raw: str, model_type):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {exc}") from exc
    try:
        return model_type.model_validate(data)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


def parse_llm_score_payload(raw: str) -> LlmScoreResult:
    """解析并严格校验 LLM 评分 JSON。"""

    return _parse(raw, LlmScoreResult)


def parse_critical_field_suggestions(raw: str) -> CriticalFieldSuggestionResult:
    """解析并严格校验关键资料建议 JSON。"""

    return _parse(raw, CriticalFieldSuggestionResult)
