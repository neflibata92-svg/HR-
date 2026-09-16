"""BOSS 真站页面操作。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from resume_agent.browser import save_failure_screenshot
from resume_agent.config import AgentSettings
from resume_agent.parse_page import RawCandidate, detect_risk_page
from resume_agent.rate_limit import sleep_action_delay
from resume_agent.selectors import BossSelectors
from resume_agent.text_extract import parse_card_text


class RiskPageError(RuntimeError):
    """检测到风控页。"""


class BossLiveSession:
    """基于 Playwright Page 的真站会话。"""

    def __init__(
        self,
        page: Any,
        settings: AgentSettings,
        selectors: BossSelectors,
        *,
        min_delay_ms: int = 1500,
        max_delay_ms: int = 4000,
    ) -> None:
        self.page = page
        self.settings = settings
        self.selectors = selectors
        self.min_delay_ms = min_delay_ms
        self.max_delay_ms = max_delay_ms

    def goto(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        self._sleep()
        self.ensure_not_risk("goto")

    def ensure_not_risk(self, label: str) -> None:
        html = self.page.content()
        keywords = tuple(self.selectors.risk_keywords) or None
        if detect_risk_page(html, keywords=keywords):
            path = save_failure_screenshot(self.page, self.settings, f"risk_{label}")
            raise RiskPageError(f"risk page detected, screenshot={path}")

    def wait_manual_login(self) -> None:
        print("请在打开的浏览器中完成 BOSS 登录（含验证码）。完成后回到终端按 Enter。")
        input()
        self.ensure_not_risk("after_login")

    def extract_candidates(self) -> list[tuple[RawCandidate, Any]]:
        """返回 (候选人, 卡片 locator) 列表。"""

        self.ensure_not_risk("list")
        locator = self._first_matching_locator(self.selectors.card_selectors)
        if locator is None:
            # 回退：整页文本无法逐卡操作，返回空让上层提示校准选择器
            return []

        count = min(locator.count(), self.selectors.max_cards_per_run)
        results: list[tuple[RawCandidate, Any]] = []
        for index in range(count):
            card = locator.nth(index)
            raw = self._card_to_candidate(card, index)
            results.append((raw, card))
        return results

    def enrich_from_detail(self, card: Any, candidate: RawCandidate) -> RawCandidate:
        """点击卡片打开详情，补充工作段数。"""

        try:
            card.click(timeout=5_000)
            self._sleep()
            self.ensure_not_risk("detail")
            detail_text = self.page.inner_text("body")
            parsed = parse_card_text(
                detail_text,
                fallback_name=candidate.name,
                fallback_org=candidate.org,
            )
            return RawCandidate(
                boss_id=candidate.boss_id,
                name=parsed.name or candidate.name,
                org=parsed.org or candidate.org,
                age=parsed.age if parsed.age is not None else candidate.age,
                years=parsed.years if parsed.years is not None else candidate.years,
                segments=parsed.segments if parsed.segments is not None else candidate.segments,
                total_years=parsed.total_years
                if parsed.total_years is not None
                else candidate.total_years,
            )
        except RiskPageError:
            raise
        except Exception:
            return candidate

    def greet(self, candidate: RawCandidate, message: str, card: Any | None = None) -> bool:
        """点击打招呼并发送话术。"""

        if card is not None:
            try:
                card.click(timeout=5_000)
                self._sleep()
            except Exception:
                pass

        greet_btn = self._first_matching_locator(self.selectors.greet_button_selectors)
        if greet_btn is None:
            save_failure_screenshot(self.page, self.settings, "greet_button_missing")
            return False
        greet_btn.first.click(timeout=5_000)
        self._sleep()
        self.ensure_not_risk("greet")

        input_box = self._first_matching_locator(self.selectors.chat_input_selectors)
        if input_box is not None:
            target = input_box.first
            try:
                target.fill(message, timeout=3_000)
            except Exception:
                target.click()
                self.page.keyboard.type(message, delay=20)
            self._sleep()
            send_btn = self._first_matching_locator(self.selectors.send_button_selectors)
            if send_btn is not None:
                send_btn.first.click(timeout=5_000)
            else:
                self.page.keyboard.press("Enter")
            self._sleep()
        return True

    def wait_and_download_attachment(self, download_dir: Path) -> Path | None:
        """等待附件并下载到目录。"""

        download_dir.mkdir(parents=True, exist_ok=True)
        attach = self._first_matching_locator(self.selectors.attachment_selectors)
        if attach is None:
            # 轮询等待
            deadline_ms = self.selectors.attachment_wait_seconds * 1000
            try:
                self.page.wait_for_selector(
                    ", ".join(self.selectors.attachment_selectors),
                    timeout=deadline_ms,
                )
                attach = self._first_matching_locator(self.selectors.attachment_selectors)
            except Exception:
                return None
        if attach is None:
            return None
        try:
            with self.page.expect_download(timeout=self.selectors.attachment_wait_seconds * 1000) as dl_info:
                attach.first.click()
            download = dl_info.value
            target = download_dir / download.suggested_filename
            download.save_as(str(target))
            return target
        except Exception:
            save_failure_screenshot(self.page, self.settings, "attachment_download_failed")
            return None

    def _card_to_candidate(self, card: Any, index: int) -> RawCandidate:
        text = ""
        try:
            text = card.inner_text(timeout=3_000)
        except Exception:
            text = ""
        name = self._child_text(card, self.selectors.name_selectors)
        org = self._child_text(card, self.selectors.org_selectors)
        boss_id = ""
        try:
            boss_id = card.get_attribute("data-boss-id") or card.get_attribute("data-geekid") or ""
        except Exception:
            boss_id = ""
        if not boss_id:
            boss_id = f"live-{index}"
        parsed = parse_card_text(text, fallback_name=name, fallback_org=org)
        return RawCandidate(
            boss_id=boss_id,
            name=parsed.name,
            org=parsed.org,
            age=parsed.age,
            years=parsed.years,
            segments=parsed.segments,
            total_years=parsed.total_years,
        )

    def _child_text(self, card: Any, selectors: list[str]) -> str:
        for selector in selectors:
            try:
                loc = card.locator(selector)
                if loc.count() > 0:
                    return (loc.first.inner_text(timeout=1_000) or "").strip()
            except Exception:
                continue
        return ""

    def _first_matching_locator(self, selectors: list[str]) -> Any | None:
        for selector in selectors:
            try:
                loc = self.page.locator(selector)
                if loc.count() > 0:
                    return loc
            except Exception:
                continue
        return None

    def _sleep(self) -> None:
        sleep_action_delay(self.min_delay_ms, self.max_delay_ms)
