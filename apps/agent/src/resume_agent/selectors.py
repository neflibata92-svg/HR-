"""选择器配置加载。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BossSelectors:
    login_url: str
    default_recommend_url: str
    card_selectors: list[str] = field(default_factory=list)
    name_selectors: list[str] = field(default_factory=list)
    org_selectors: list[str] = field(default_factory=list)
    greet_button_selectors: list[str] = field(default_factory=list)
    chat_input_selectors: list[str] = field(default_factory=list)
    send_button_selectors: list[str] = field(default_factory=list)
    attachment_selectors: list[str] = field(default_factory=list)
    risk_keywords: list[str] = field(default_factory=list)
    max_cards_per_run: int = 30
    attachment_wait_seconds: int = 120


def default_selectors_path() -> Path:
    # apps/agent/boss_selectors.json（相对包上级）
    return Path(__file__).resolve().parents[2] / "boss_selectors.json"


def load_boss_selectors(path: Path | None = None) -> BossSelectors:
    target = path or default_selectors_path()
    data = json.loads(target.read_text(encoding="utf-8"))
    return BossSelectors(
        login_url=data["login_url"],
        default_recommend_url=data["default_recommend_url"],
        card_selectors=list(data.get("card_selectors", [])),
        name_selectors=list(data.get("name_selectors", [])),
        org_selectors=list(data.get("org_selectors", [])),
        greet_button_selectors=list(data.get("greet_button_selectors", [])),
        chat_input_selectors=list(data.get("chat_input_selectors", [])),
        send_button_selectors=list(data.get("send_button_selectors", [])),
        attachment_selectors=list(data.get("attachment_selectors", [])),
        risk_keywords=list(data.get("risk_keywords", [])),
        max_cards_per_run=int(data.get("max_cards_per_run", 30)),
        attachment_wait_seconds=int(data.get("attachment_wait_seconds", 120)),
    )
