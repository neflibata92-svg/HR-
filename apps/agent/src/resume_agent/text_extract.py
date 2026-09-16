"""从中文候选人卡片文本抽取年龄/年限等信息。"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedCardText:
    name: str
    org: str
    age: int | None
    years: float | None
    segments: int | None
    total_years: float | None


_AGE_RE = re.compile(r"(\d{1,2})\s*岁")
_YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*年(?:以上|经验|工作)?")
_SEG_HINT_RE = re.compile(r"(?:经历|任职|就职)[^\d]*(\d+)\s*(?:段|家|份)")
_DATE_RANGE_RE = re.compile(
    r"(20\d{2}[./年]\d{1,2})\s*[-–—至到]\s*(20\d{2}[./年]\d{1,2}|至今|现在)"
)


def count_job_segments(text: str) -> int | None:
    """按工作经历日期区间数量估算段数。"""

    ranges = _DATE_RANGE_RE.findall(text)
    if ranges:
        return len(ranges)
    hinted = _first_int(_SEG_HINT_RE, text)
    return hinted


def parse_card_text(text: str, *, fallback_name: str = "", fallback_org: str = "") -> ParsedCardText:
    """从自由文本解析年龄、工作年限与经历段数。"""

    cleaned = re.sub(r"\s+", " ", text).strip()
    age = _first_int(_AGE_RE, cleaned)
    years = _first_float(_YEARS_RE, cleaned)
    segments = count_job_segments(cleaned)
    total_years = years
    name = fallback_name.strip() or _guess_name(cleaned)
    org = fallback_org.strip() or _guess_org(cleaned)
    return ParsedCardText(
        name=name,
        org=org,
        age=age,
        years=years,
        segments=segments,
        total_years=total_years,
    )


def _first_int(pattern: re.Pattern[str], text: str) -> int | None:
    match = pattern.search(text)
    if not match:
        return None
    return int(match.group(1))


def _first_float(pattern: re.Pattern[str], text: str) -> float | None:
    match = pattern.search(text)
    if not match:
        return None
    return float(match.group(1))


def _guess_name(text: str) -> str:
    # 取首个较短中文词，避免把整段当姓名
    match = re.search(r"[\u4e00-\u9fff]{2,4}", text)
    return match.group(0) if match else "未知"


def _guess_org(text: str) -> str:
    match = re.search(
        r"([\u4e00-\u9fffA-Za-z0-9]{2,20}(?:科技|网络|信息|集团|公司|银行|医院))",
        text,
    )
    return match.group(1) if match else ""
