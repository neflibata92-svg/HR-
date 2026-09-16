"""Agent CLI。"""

from __future__ import annotations

import argparse
from pathlib import Path

from resume_agent.api_client import ApiClient
from resume_agent.config import AgentSettings
from resume_agent.live_runner import run_live_round, run_login
from resume_agent.llm import LlmScorer
from resume_agent.runner import run_fixture_round
from resume_agent.selectors import load_boss_selectors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BOSS 简历筛选本机 Agent")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="打开浏览器，人工登录并保存 Profile")

    run_parser = sub.add_parser("run", help="运行一轮筛选")
    run_parser.add_argument("--fixture", type=str, default="", help="本地 HTML fixture 路径")
    run_parser.add_argument("--live", action="store_true", help="使用 Playwright 打开真站")
    run_parser.add_argument("--entry-url", type=str, default="", help="覆盖岗位入口 URL")
    run_parser.add_argument("--selectors", type=str, default="", help="选择器 JSON 路径")

    args = parser.parse_args(argv)
    settings = AgentSettings()
    if getattr(args, "selectors", ""):
        settings.selectors_path = args.selectors

    if args.command == "login":
        return run_login(settings, load_boss_selectors(Path(settings.selectors_path) if settings.selectors_path else None))

    api = ApiClient(settings)
    scorer = LlmScorer(settings)

    if args.command == "run":
        if args.live:
            return run_live_round(
                settings,
                api,
                scorer,
                entry_url=args.entry_url,
            )
        if not args.fixture:
            print("请指定 --fixture 或使用 --live")
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
