"""一轮筛选的共享执行逻辑。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from resume_domain.fingerprint import candidate_fingerprint
from resume_agent.api_client import ApiClient
from resume_agent.config import AgentSettings
from resume_agent.parse_page import RawCandidate, parse_list_html, detect_risk_page
from resume_agent.pipeline import Scorer, process_candidate
from resume_agent.rate_limit import sleep_action_delay


class PipelineGreeter:
    def __init__(self, greet_fn: Any) -> None:
        self._greet_fn = greet_fn
        self.last_ok = False

    def greet(self, candidate: RawCandidate, message: str) -> bool:
        self.last_ok = bool(self._greet_fn(candidate, message))
        return self.last_ok


def process_job_candidates(
    *,
    settings: AgentSettings,
    api: ApiClient,
    scorer: Scorer,
    job: dict[str, Any],
    candidates: list[RawCandidate],
    greeter: PipelineGreeter | None = None,
    on_greeted: Any | None = None,
) -> int:
    """处理一批候选人，返回处理人数。"""

    hourly_limit = int(job.get("hourly_greet_limit") or 20)
    greeted_count = 0

    for raw in candidates:
        fingerprint = candidate_fingerprint(raw.name, raw.org or raw.boss_id or "unknown")
        upserted = api.upsert_candidate(
            {
                "boss_id": raw.boss_id or None,
                "fingerprint": fingerprint,
                "name": raw.name,
                "age": raw.age,
                "years_of_experience": raw.years,
                "job_segments_json": "[]",
                "source": "boss",
            }
        )
        already = api.outreach_exists(job["id"], upserted["id"])
        blocked = api.exchange_blocked(upserted["id"])
        result = process_candidate(
            raw,
            jd_text=job["jd_text"],
            threshold=int(job["score_threshold"]),
            greet_template=job["greet_template"],
            exchanged_within_30_days=blocked,
            already_greeted=already,
            scorer=scorer,
            greeter=greeter,
        )
        api.post_score(
            {
                "candidate_id": upserted["id"],
                "job_id": job["id"],
                "hard_filter_passed": result.action != "hard_filter_reject",
                "hard_filter_reasons": result.reasons
                if result.action == "hard_filter_reject"
                else [],
                "score": result.score,
                "reason": ";".join(result.reasons),
                "model": result.model,
            }
        )
        if result.action == "greeted":
            api.post_outreach(
                {
                    "candidate_id": upserted["id"],
                    "job_id": job["id"],
                    "greeted": True,
                }
            )
            greeted_count += 1
            if on_greeted is not None:
                on_greeted(raw, upserted)
            if greeted_count >= hourly_limit:
                print(f"已达本轮招呼上限 {hourly_limit}，停止")
                break
        print(f"{raw.name}: {result.action} score={result.score} reasons={result.reasons}")
        sleep_action_delay(
            int(job.get("min_action_delay_ms") or 1500),
            int(job.get("max_action_delay_ms") or 4000),
        )
    return len(candidates)


def run_fixture_round(
    settings: AgentSettings,
    api: ApiClient,
    scorer: Scorer,
    fixture: Path,
) -> int:
    html = fixture.read_text(encoding="utf-8")
    if detect_risk_page(html):
        api.heartbeat("paused", last_error="risk_page_detected")
        print("检测到风控/验证码页，已停机")
        return 3
    jobs = api.list_enabled_jobs()
    if not jobs:
        print("无启用岗位")
        api.heartbeat("idle")
        return 0
    process_job_candidates(
        settings=settings,
        api=api,
        scorer=scorer,
        job=jobs[0],
        candidates=parse_list_html(html),
        greeter=None,
    )
    api.heartbeat("idle")
    return 0
