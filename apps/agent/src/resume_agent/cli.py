"""Agent CLI。"""

from __future__ import annotations

import argparse
from pathlib import Path

from resume_agent.api_client import ApiClient
from resume_agent.config import AgentSettings
from resume_agent.llm import LlmScorer
from resume_agent.parse_page import detect_risk_page, parse_list_html
from resume_agent.pipeline import process_candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BOSS 简历筛选本机 Agent")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="运行一轮筛选")
    run_parser.add_argument("--fixture", type=str, default="", help="本地 HTML fixture 路径")

    args = parser.parse_args(argv)
    settings = AgentSettings()
    api = ApiClient(settings)
    scorer = LlmScorer(settings)

    if args.command == "run":
        return _run(settings, api, scorer, fixture=args.fixture)
    return 1


def _run(
    settings: AgentSettings,
    api: ApiClient,
    scorer: LlmScorer,
    *,
    fixture: str,
) -> int:
    try:
        api.heartbeat("running")
    except Exception as exc:  # noqa: BLE001
        print(f"API 不可达，停止新招呼: {exc}")
        return 2

    if not fixture:
        print("MVP CLI 请使用 --fixture 传入页面 HTML 快照；真站 Playwright 路径待选择器校准后启用。")
        api.heartbeat("idle")
        return 0

    html = Path(fixture).read_text(encoding="utf-8")
    if detect_risk_page(html):
        api.heartbeat("paused", last_error="risk_page_detected")
        print("检测到风控/验证码页，已停机")
        return 3

    jobs = api.list_enabled_jobs()
    if not jobs:
        print("无启用岗位")
        api.heartbeat("idle")
        return 0

    job = jobs[0]
    candidates = parse_list_html(html)
    for raw in candidates:
        upserted = api.upsert_candidate(
            {
                "boss_id": raw.boss_id or None,
                "fingerprint": __import__(
                    "resume_domain.fingerprint", fromlist=["candidate_fingerprint"]
                ).candidate_fingerprint(raw.name, raw.org),
                "name": raw.name,
                "age": raw.age,
                "years_of_experience": raw.years,
                "job_segments_json": "[]",
                "source": "boss",
            }
        )
        blocked = api.exchange_blocked(upserted["id"])
        result = process_candidate(
            raw,
            jd_text=job["jd_text"],
            threshold=job["score_threshold"],
            greet_template=job["greet_template"],
            exchanged_within_30_days=blocked,
            already_greeted=False,
            scorer=scorer,
            greeter=None,
        )
        api.post_score(
            {
                "candidate_id": upserted["id"],
                "job_id": job["id"],
                "hard_filter_passed": result.action
                not in {"hard_filter_reject", "score_error"},
                "hard_filter_reasons": result.reasons
                if result.action == "hard_filter_reject"
                else [],
                "score": result.score,
                "reason": ";".join(result.reasons),
                "model": settings.llm_model,
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
        print(f"{raw.name}: {result.action} score={result.score} reasons={result.reasons}")

    api.heartbeat("idle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
