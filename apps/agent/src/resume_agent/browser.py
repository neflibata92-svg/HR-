"""Playwright 持久化浏览器。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from resume_agent.config import AgentSettings


def ensure_profile_dir(settings: AgentSettings) -> Path:
    path = Path(settings.browser_user_data_dir).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_screenshot_dir(settings: AgentSettings) -> Path:
    path = Path(settings.screenshot_dir).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def open_persistent_browser(settings: AgentSettings) -> Iterator[Any]:
    """打开 headed Chromium persistent context，退出时关闭。"""

    from playwright.sync_api import sync_playwright

    profile = ensure_profile_dir(settings)
    launch_kwargs: dict[str, object] = {
        "user_data_dir": str(profile),
        "headless": False,
        "viewport": None,
        "accept_downloads": True,
        "ignore_default_args": ["--no-sandbox"],
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-proxy-server",
        ],
    }
    if settings.browser_channel:
        launch_kwargs["channel"] = settings.browser_channel
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(**launch_kwargs)
        try:
            yield context
        finally:
            context.close()


def first_page(context: Any) -> Any:
    if context.pages:
        return context.pages[0]
    return context.new_page()


def save_failure_screenshot(page: Any, settings: AgentSettings, label: str) -> Path:
    folder = ensure_screenshot_dir(settings)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = folder / f"{stamp}_{label}.png"
    page.screenshot(path=str(path), full_page=True)
    return path
