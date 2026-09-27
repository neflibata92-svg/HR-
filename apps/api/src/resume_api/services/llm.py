"""服务端第三方大模型评分与关键资料建议适配器。"""

from __future__ import annotations

import json
from typing import Protocol

import httpx

from resume_api.core.config import Settings
from resume_domain.llm_schema import (
    CriticalFieldSuggestionResult,
    LlmScoreResult,
    parse_critical_field_suggestions,
    parse_llm_score_payload,
)

SCORE_PROMPT = """你是招聘筛选助手。请严格根据人工填写的完整岗位 JD 与候选人摘要评分。
JD 中写明的学历、经验、技能等要求都属于评分依据；候选人资料未提及的内容不得猜测为满足。
只输出严格 JSON，字段为 score、reason、evidence、missing_fields、estimated_fields、critical_fields、confidence、decision。
critical_fields 固定输出空数组；decision 根据匹配情况输出 eligible 或 below_threshold。
不要输出其它文字。"""

CRITICAL_FIELDS_PROMPT = """你是招聘岗位分析助手。根据 JD 建议必须确认的关键资料。
每项只包含稳定英文 key（小写字母、数字、下划线）、中文 label 和中文 reason。
只输出严格 JSON：{"suggestions":[{"key":"example_key","label":"中文名","reason":"理由"}]}。
至少返回一项，不要输出其它文字。"""


class LlmNotConfiguredError(RuntimeError):
    """供应商密钥未在服务端配置。"""


class LlmUpstreamError(RuntimeError):
    """供应商请求失败或返回内容无效。"""


class HttpClient(Protocol):
    def post(self, url: str, **kwargs): ...


def _call_json(
    settings: Settings,
    *,
    system_prompt: str,
    user_content: str,
    parser,
    client: HttpClient | None,
):
    if not settings.llm_api_key:
        raise LlmNotConfiguredError("LLM provider is not configured")
    owned_client = client is None
    http_client = client or httpx.Client()
    attempts = min(3, max(1, settings.llm_max_attempts))
    try:
        for attempt in range(attempts):
            try:
                response = http_client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.llm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.llm_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content},
                        ],
                        "temperature": 0,
                    },
                    timeout=settings.llm_timeout_seconds,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                result = parser(content)
                return result.model_copy(update={"model": settings.llm_model})
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
                if attempt == attempts - 1:
                    raise LlmUpstreamError("LLM provider request failed") from None
    finally:
        if owned_client:
            close = getattr(http_client, "close", None)
            if close is not None:
                close()
    raise LlmUpstreamError("LLM provider request failed")


def finalize_score(
    result: LlmScoreResult,
    *,
    critical_fields: list[dict[str, str]] | None = None,
    threshold: int,
) -> LlmScoreResult:
    """按岗位分数阈值计算最终结论；旧关键资料参数仅为接口兼容保留。"""

    del critical_fields
    decision = "eligible" if result.score >= threshold else "below_threshold"
    return result.model_copy(update={"decision": decision, "critical_fields": []})


def score_candidate(
    settings: Settings,
    jd: str,
    summary: str,
    *,
    critical_fields: list[dict[str, str]] | None = None,
    client: HttpClient | None = None,
) -> LlmScoreResult:
    """调用服务端配置的 OpenAI 兼容接口并返回严格评分结果。"""

    del critical_fields
    return _call_json(
        settings,
        system_prompt=SCORE_PROMPT,
        user_content=f"岗位 JD:\n{jd}\n\n候选人摘要:\n{summary}",
        parser=parse_llm_score_payload,
        client=client,
    )


def suggest_critical_fields(
    settings: Settings,
    jd: str,
    *,
    client: HttpClient | None = None,
) -> CriticalFieldSuggestionResult:
    """根据岗位 JD 请求关键资料建议；失败时不提供伪造占位结果。"""

    return _call_json(
        settings,
        system_prompt=CRITICAL_FIELDS_PROMPT,
        user_content=f"JD:\n{jd}",
        parser=parse_critical_field_suggestions,
        client=client,
    )
