"""服务端第三方大模型评分适配器。"""

from __future__ import annotations

from typing import Protocol

import httpx

from resume_api.core.config import Settings
from resume_domain.llm_schema import LlmScoreResult, parse_llm_score_payload

SCORE_PROMPT = """你是招聘筛选助手。根据 JD 与候选人摘要打分。
只输出 JSON：{"score":0-100整数,"reason":"简短中文理由","evidence":["依据1"]}。
不要输出其它文字。"""


class LlmNotConfiguredError(RuntimeError):
    """供应商密钥未在服务端配置。"""


class LlmUpstreamError(RuntimeError):
    """供应商请求失败或返回内容无效。"""


class HttpClient(Protocol):
    def post(self, url: str, **kwargs): ...


def score_candidate(
    settings: Settings,
    jd: str,
    summary: str,
    *,
    client: HttpClient | None = None,
) -> LlmScoreResult:
    """调用服务端配置的 OpenAI 兼容接口并返回严格评分结果。"""

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
                            {"role": "system", "content": SCORE_PROMPT},
                            {"role": "user", "content": f"JD:\n{jd}\n\n候选人:\n{summary}"},
                        ],
                        "temperature": 0,
                    },
                    timeout=settings.llm_timeout_seconds,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                result = parse_llm_score_payload(content)
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
