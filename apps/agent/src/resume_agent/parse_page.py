"""从 HTML 解析候选人列表（fixture / 页面快照）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True)
class RawCandidate:
    boss_id: str
    name: str
    org: str
    age: int | None
    years: float | None
    segments: int | None
    total_years: float | None


class _CardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cards: list[RawCandidate] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            return
        mapping = {k: (v or "") for k, v in attrs}
        if mapping.get("class") != "candidate-card":
            return
        self.cards.append(
            RawCandidate(
                boss_id=mapping.get("data-boss-id", ""),
                name=mapping.get("data-name", ""),
                org=mapping.get("data-org", ""),
                age=_to_int(mapping.get("data-age")),
                years=_to_float(mapping.get("data-years")),
                segments=_to_int(mapping.get("data-segments")),
                total_years=_to_float(mapping.get("data-total-years")),
            )
        )


def _to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_list_html(html: str) -> list[RawCandidate]:
    parser = _CardParser()
    parser.feed(html)
    return parser.cards


def detect_risk_page(html: str) -> bool:
    """检测验证码/风控关键词。"""

    patterns = ("验证码", "异常访问", "安全验证", "请完成验证")
    return any(p in html for p in patterns)


# 真站选择器占位（需按实际 DOM 校准）
BOSS_CARD_SELECTOR = ".candidate-card"
