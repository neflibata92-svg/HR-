"""Agent CLI。"""

from __future__ import annotations

import argparse
from pathlib import Path

from resume_agent.api_client import ApiClient
from resume_agent.config import AgentSettings
from resume_agent.live_runner import (
    check_boss_login_status,
    download_live_resume,
    run_live_round,
    run_login,
)
from resume_agent.resident import ResidentAgent
from resume_agent.resume_monitor import ResumeMonitor
from resume_agent.runner import run_fixture_round
from resume_agent.selectors import load_boss_selectors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BOSS 简历筛选本机 Agent")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="打开浏览器，人工登录并保存 Profile")

    run_parser = sub.add_parser("run", help="运行一轮筛选")
    run_parser.add_argument("--fixture", type=str, default="", help="本地 HTML fixture 路径")
    run_parser.add_argument("--live", action="store_true", help="使用 Playwright 打开真站")
    run_parser.add_argument("--resident", action="store_true", help="常驻运行并接收分配任务")
    run_parser.add_argument("--task-id", type=int, default=None, help="真站单轮的明确任务编号")
    run_parser.add_argument("--entry-url", type=str, default="", help="覆盖岗位入口 URL")
    run_parser.add_argument("--selectors", type=str, default="", help="选择器 JSON 路径")

    args = parser.parse_args(argv)
    settings = AgentSettings()
    if getattr(args, "selectors", ""):
        settings.selectors_path = args.selectors

    if args.command == "login":
        return run_login(settings, load_boss_selectors(Path(settings.selectors_path) if settings.selectors_path else None))

    api = ApiClient(settings)
    scorer = api

    if args.command == "run":
        if args.resident:
            selectors = load_boss_selectors(
                Path(settings.selectors_path) if settings.selectors_path else None
            )
            resume_monitor = ResumeMonitor(
                api,
                download_attachment=lambda candidate_id, candidate_name, boss_id: (
                    download_live_resume(
                        settings,
                        candidate_id=candidate_id,
                        candidate_name=candidate_name,
                        boss_id=boss_id,
                        selectors=selectors,
                    )
                ),
            )
            resident = ResidentAgent(
                settings,
                api,
                run_task=lambda task: run_live_round(
                    settings,
                    api,
                    scorer,
                    task_id=int(task["id"]),
                    claimed_task=task,
                    selectors=selectors,
                    entry_url=args.entry_url,
                ),
                poll_resumes=resume_monitor.poll_once,
                check_login_status=lambda: check_boss_login_status(
                    settings,
                    api,
                    selectors=selectors,
                ),
            )
            try:
                resident.run_forever()
            except KeyboardInterrupt:
                return 0
            return 0
        if args.live:
            if args.task_id is None:
                print("真站单轮必须指定 --task-id；长期运行请使用 --resident")
                return 1
            return run_live_round(
                settings,
                api,
                scorer,
                task_id=args.task_id,
                entry_url=args.entry_url,
            )
        if not args.fixture:
            print("请指定 --fixture、--live --task-id 或使用 --resident")
            return 1
        try:
            api.heartbeat("running")
        except Exception as exc:  # noqa: BLE001
            print(f"API 不可达，停止新招呼: {exc}")
            return 2
        return run_fixture_round(settings, api, scorer, Path(args.fixture))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
