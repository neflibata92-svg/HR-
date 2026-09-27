"""真站任务驱动执行。"""

from __future__ import annotations

from pathlib import Path
import subprocess

from resume_agent.api_client import ApiClient
from resume_agent.boss_live import BossLiveSession, PageStateError, RepeatedDomError, RiskPageError
from resume_agent.browser import first_page, open_persistent_browser, save_failure_screenshot
from resume_agent.config import AgentSettings
from resume_agent.pipeline import Scorer
from resume_agent.runner import run_task_candidates
from resume_agent.selectors import BossSelectors, load_boss_selectors


def run_login(settings: AgentSettings, selectors: BossSelectors | None = None) -> int:
    selectors = selectors or _load(settings)
    profile = Path(settings.browser_user_data_dir).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not chrome.exists():
        print("未找到 Google Chrome，请先安装后重试。")
        return 1
    print("正在用普通 Chrome 打开 BOSS 登录页，请完成登录后关闭该 Chrome 窗口。")
    subprocess.run(
        [
            str(chrome),
            f"--user-data-dir={profile}",
            "--no-proxy-server",
            selectors.login_url,
        ],
        check=False,
    )
    print(f"登录状态已保存，Profile 目录: {settings.browser_user_data_dir}")
    return 0


def download_live_resume(
    settings: AgentSettings,
    *,
    candidate_id: int,
    candidate_name: str,
    boss_id: str = "",
    selectors: BossSelectors | None = None,
) -> Path | None:
    selectors = selectors or _load(settings)
    download_dir = Path(settings.download_dir).resolve()
    download_dir.mkdir(parents=True, exist_ok=True)
    with open_persistent_browser(settings) as context:
        page = first_page(context)
        session = BossLiveSession(settings=settings, page=page, selectors=selectors)
        session.goto(selectors.default_recommend_url)
        return session.download_candidate_attachment(
            candidate_id,
            candidate_name,
            download_dir,
            boss_id=boss_id,
        )


def check_boss_login_status(
    settings: AgentSettings,
    api: ApiClient,
    *,
    selectors: BossSelectors | None = None,
) -> str:
    """打开已保存的 Profile，并以真实页面状态判断登录是否仍有效。"""

    del api
    selectors = selectors or _load(settings)
    try:
        with open_persistent_browser(settings) as context:
            page = first_page(context)
            session = BossLiveSession(settings=settings, page=page, selectors=selectors)
            session.goto(selectors.default_recommend_url)
            session.ensure_task_page()
        return "logged_in"
    except PageStateError as exc:
        reason = str(exc).lower()
        page_url = str(getattr(locals().get("page"), "url", "")).lower()
        return "expired" if "login" in reason or "/login" in page_url else "unknown"
    except (RiskPageError, RepeatedDomError):
        return "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def run_live_round(
    settings: AgentSettings,
    api: ApiClient,
    scorer: Scorer,
    *,
    task_id: int,
    claimed_task: dict[str, object] | None = None,
    selectors: BossSelectors | None = None,
    entry_url: str = "",
) -> int:
    """领取服务端明确分配的任务，并按岗位入口处理候选人。"""

    del scorer
    selectors = selectors or _load(settings)
    try:
        api.heartbeat(
            "idle",
            availability="idle",
            boss_login_status="unknown",
        )
        task = claimed_task or api.get_task(task_id)
    except Exception as exc:  # noqa: BLE001
        print(f"API 不可达或指定任务不可读取，停止新招呼: {exc}")
        return 2

    task_claimed = claimed_task is not None
    try:
        with open_persistent_browser(settings) as context:
            page = first_page(context)
            session = BossLiveSession(settings=settings, page=page, selectors=selectors)
            target_url = str(task.get("boss_entry_url") or entry_url).strip()
            if target_url:
                session.goto(target_url)
            else:
                session.ensure_task_page()
            if claimed_task is None:
                task = api.claim_task(task_id)
                task_claimed = True
            api.heartbeat(
                "running",
                availability="busy",
                current_task_id=task_id,
                current_job_id=int(task["job_id"]),
                boss_login_status="logged_in",
            )
            pairs = session.extract_candidates(limit=int(task["requested_count"]))
            if not pairs:
                path = save_failure_screenshot(page, settings, "no_cards")
                api.pause_task(int(task["id"]), "no_cards")
                api.acknowledge_control(int(task["id"]))
                api.heartbeat("paused", last_error="no_cards")
                print(f"当前页未找到候选人卡片，任务已暂停。截图: {path}")
                return 4

            candidates = [raw for raw, _ in pairs]
            cards_by_identity = {
                (raw.boss_id, raw.name, raw.org): card for raw, card in pairs
            }

            class LiveGreeter:
                def greet(self, candidate, message: str) -> bool:
                    card = cards_by_identity.get(
                        (candidate.boss_id, candidate.name, candidate.org)
                    )
                    return session.greet(candidate, message, card)

            run_task_candidates(
                settings=settings,
                api=api,
                task=task,
                candidates=candidates,
                greeter=LiveGreeter(),
            )
            api.heartbeat("idle", boss_login_status="logged_in")
            return 0
    except (RiskPageError, PageStateError, RepeatedDomError) as exc:
        reason = str(exc)
        login_status = "expired" if isinstance(exc, PageStateError) and "login" in reason.lower() else "unknown"
        if task_claimed:
            api.pause_task(int(task["id"]), reason)
            api.acknowledge_control(int(task["id"]))
        api.heartbeat(
            "paused" if task_claimed else "idle",
            availability="offline" if login_status == "expired" else ("busy" if task_claimed else "idle"),
            current_task_id=int(task["id"]) if task_claimed else None,
            current_job_id=int(task["job_id"]) if task_claimed else None,
            boss_login_status=login_status,
            last_error=reason,
        )
        state = "任务已暂停" if task_claimed else "任务未领取"
        print(f"页面异常，{state}: {reason}")
        return 3
    except Exception as exc:  # noqa: BLE001
        reason = str(exc)
        if task_claimed:
            try:
                api.pause_task(int(task["id"]), reason)
                api.acknowledge_control(int(task["id"]))
                api.heartbeat("paused", last_error=reason)
            except Exception:  # noqa: BLE001
                pass
        print(f"真站运行失败: {reason}")
        return 5


def _load(settings: AgentSettings) -> BossSelectors:
    path = Path(settings.selectors_path) if settings.selectors_path else None
    return load_boss_selectors(path)
