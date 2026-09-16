"""真站一轮执行。"""

from __future__ import annotations

from pathlib import Path

from resume_domain.fingerprint import candidate_fingerprint
from resume_agent.api_client import ApiClient
from resume_agent.boss_live import BossLiveSession, RiskPageError
from resume_agent.browser import first_page, open_persistent_browser, save_failure_screenshot
from resume_agent.config import AgentSettings
from resume_agent.llm import LlmScorer
from resume_agent.pipeline import process_candidate
from resume_agent.rate_limit import sleep_action_delay
from resume_agent.selectors import BossSelectors, load_boss_selectors


def run_login(settings: AgentSettings, selectors: BossSelectors | None = None) -> int:
    selectors = selectors or _load(settings)
    with open_persistent_browser(settings) as context:
        page = first_page(context)
        session = BossLiveSession(page, settings, selectors)
        session.goto(selectors.login_url)
        session.wait_manual_login()
        print(f"登录完成，Profile 目录: {settings.browser_user_data_dir}")
    return 0


def run_live_round(
    settings: AgentSettings,
    api: ApiClient,
    scorer: LlmScorer,
    *,
    selectors: BossSelectors | None = None,
    entry_url: str = "",
) -> int:
    selectors = selectors or _load(settings)
    try:
        api.heartbeat("running")
    except Exception as exc:  # noqa: BLE001
        print(f"API 不可达，停止新招呼: {exc}")
        return 2

    jobs = api.list_enabled_jobs()
    if not jobs:
        print("无启用岗位")
        api.heartbeat("idle")
        return 0
    job = jobs[0]
    url = entry_url or job.get("boss_entry_url") or selectors.default_recommend_url
    hourly_limit = int(job.get("hourly_greet_limit") or 20)
    greeted_count = 0

    try:
        with open_persistent_browser(settings) as context:
            page = first_page(context)
            session = BossLiveSession(
                page,
                settings,
                selectors,
                min_delay_ms=int(job.get("min_action_delay_ms") or 1500),
                max_delay_ms=int(job.get("max_action_delay_ms") or 4000),
            )
            session.goto(url)
            pairs = session.extract_candidates()
            if not pairs:
                path = save_failure_screenshot(page, settings, "no_cards")
                print(
                    "未找到候选人卡片。请校准 apps/agent/boss_selectors.json 的 card_selectors。"
                    f" 截图: {path}"
                )
                api.heartbeat("paused", last_error="no_cards")
                return 4

            total = len(pairs)
            for index in range(total):
                # 每次回到列表，避免 locator 失效
                session.goto(url)
                pairs = session.extract_candidates()
                if index >= len(pairs):
                    break
                raw, card = pairs[index]
                if settings.open_detail_for_segments:
                    raw = session.enrich_from_detail(card, raw)

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

                def greet_fn(candidate, message: str) -> bool:
                    return session.greet(candidate, message, None)

                from resume_agent.runner import PipelineGreeter

                greeter = PipelineGreeter(greet_fn)
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
                        "hard_filter_passed": result.action
                        not in {"hard_filter_reject", "score_error", "skip_already_greeted"},
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
                    greeted_count += 1
                    if settings.wait_attachment_after_greet:
                        file_path = session.wait_and_download_attachment(Path(settings.download_dir))
                        if file_path is None:
                            print(f"{raw.name}: 已打招呼，暂未收到附件")
                        else:
                            api.upload_resume_file(file_path, candidate_id=upserted["id"])
                            api.mark_attachment_received(job["id"], upserted["id"])
                            print(f"{raw.name}: 附件已入库 {file_path.name}")
                    if greeted_count >= hourly_limit:
                        print(f"已达本轮招呼上限 {hourly_limit}，停止")
                        break

                print(f"{raw.name}: {result.action} score={result.score} reasons={result.reasons}")
                sleep_action_delay(
                    int(job.get("min_action_delay_ms") or 1500),
                    int(job.get("max_action_delay_ms") or 4000),
                )

            api.heartbeat("idle")
            return 0
    except RiskPageError as exc:
        api.heartbeat("paused", last_error=str(exc))
        print(f"风控停机: {exc}")
        return 3
    except Exception as exc:  # noqa: BLE001
        api.heartbeat("paused", last_error=str(exc))
        print(f"真站运行失败: {exc}")
        return 5


def _load(settings: AgentSettings) -> BossSelectors:
    path = Path(settings.selectors_path) if settings.selectors_path else None
    return load_boss_selectors(path)
