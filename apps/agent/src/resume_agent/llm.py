"""LLM 打分适配器。"""

from __future__ import annotations

import httpx

from resume_domain.llm_schema import LlmScoreResult, parse_llm_score_payload
from resume_agent.config import AgentSettings

SCORE_PROMPT = """你是招聘筛选助手。根据 JD 与候选人摘要打分。
只输出 JSON：{"score":0-100整数,"reason":"简短中文理由","evidence":["依据1"]}。
不要输出其它文字。"""


class LlmScorer:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings

    def score_candidate(self, jd: str, summary: str) -> LlmScoreResult:
        """调用 OpenAI 兼容接口；最多重试 2 次（共 3 次尝试）。"""

        last_error: Exception | None = None
        for _ in range(3):
            try:
                return self._once(jd, summary)
            except (ValueError, httpx.HTTPError) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    def _once(self, jd: str, summary: str) -> LlmScoreResult:
        if not self.settings.llm_api_key:
            # 无密钥时用于本地联调：返回可解析的固定 JSON
            return parse_llm_score_payload(
                '{"score": 80, "reason": "无密钥占位分", "evidence": ["placeholder"]}'
            )
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": SCORE_PROMPT},
                {"role": "user", "content": f"JD:\n{jd}\n\n候选人:\n{summary}"},
            ],
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        return parse_llm_score_payload(content)
