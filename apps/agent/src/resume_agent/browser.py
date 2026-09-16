"""浏览器启动占位：真站使用 Playwright persistent context。"""

from __future__ import annotations

from pathlib import Path

from resume_agent.config import AgentSettings


def ensure_profile_dir(settings: AgentSettings) -> Path:
    path = Path(settings.browser_user_data_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path
