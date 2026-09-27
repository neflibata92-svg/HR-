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


class PageStateError(RuntimeError):
    """当前页面不适合继续自动处理。"""


class RiskPageError(PageStateError):
    """检测到风控页。"""


class RepeatedDomError(PageStateError):
    """同类 DOM 错误连续出现，必须暂停人工检查。"""


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
        self._dom_error_code = ""
        self._dom_error_count = 0

    def ensure_task_page(self) -> None:
        html = self.page.content()
        url = str(getattr(self.page, "url", ""))
        checks = (
            (self.selectors.login_url_keywords, url, "login_required"),
            (self.selectors.login_keywords, html, "login_required"),
            (self.selectors.captcha_keywords, html, "captcha"),
            (self.selectors.risk_keywords, html, "risk"),
            (self.selectors.error_keywords, html, "page_error"),
        )
        for keywords, value, code in checks:
            if any(keyword and keyword in value for keyword in keywords):
                raise PageStateError(code)
        result_keywords = self.selectors.result_page_url_keywords
        if result_keywords and not any(keyword in url for keyword in result_keywords):
            raise PageStateError("not_results_page")

    def _dom_error(self, code: str) -> bool:
        if self._dom_error_code == code:
            self._dom_error_count += 1
        else:
            self._dom_error_code = code
            self._dom_error_count = 1
        if self._dom_error_count >= 3:
            raise RepeatedDomError(code)
        return False

    def _clear_dom_error(self) -> None:
        self._dom_error_code = ""
        self._dom_error_count = 0

    def goto(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        self._sleep()
        self.ensure_not_risk("goto")

    def ensure_not_risk(self, label: str) -> None:
        del label
        self.ensure_task_page()

    def wait_manual_login(self) -> None:
        print("请在打开的浏览器中完成 BOSS 登录（含验证码）。完成后回到终端按 Enter。")
        input()
        self.ensure_not_risk("after_login")

    def extract_candidates(self, *, limit: int | None = None) -> list[tuple[RawCandidate, Any]]:
        """返回 (候选人, 卡片 locator) 列表。"""

        self.ensure_task_page()
        locator = self._first_matching_locator(self.selectors.card_selectors)
        if locator is None:
            # 回退：整页文本无法逐卡操作，返回空让上层提示校准选择器
            return []

        requested_limit = limit if limit is not None else self.selectors.max_cards_per_run
        count = min(locator.count(), requested_limit)
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
        """核对候选人身份后发送，并验证消息已出现在页面。"""

        if card is not None:
            try:
                card_text = (card.inner_text(timeout=3_000) or "").strip()
                card_boss_id = (
                    card.get_attribute("data-boss-id")
                    or card.get_attribute("data-geekid")
                    or ""
                )
            except Exception:
                return self._dom_error("candidate_identity_unavailable")
            identity_mismatch = (
                not candidate.name
                or candidate.name not in card_text
                or bool(candidate.org) and candidate.org not in card_text
                or bool(candidate.boss_id)
                and bool(card_boss_id)
                and candidate.boss_id != card_boss_id
            )
            if identity_mismatch:
                return self._dom_error("candidate_identity_mismatch")
            try:
                card.click(timeout=5_000)
                self._sleep()
                self.ensure_task_page()
            except PageStateError:
                raise
            except Exception:
                return self._dom_error("candidate_open_failed")

        greet_btn = self._first_matching_locator(self.selectors.greet_button_selectors)
        if greet_btn is None:
            save_failure_screenshot(self.page, self.settings, "greet_button_missing")
            return self._dom_error("greet_button_missing")
        greet_btn.first.click(timeout=5_000)
        self._sleep()
        self.ensure_not_risk("greet")

        input_box = self._first_matching_locator(self.selectors.chat_input_selectors)
        if input_box is None:
            return self._dom_error("chat_input_missing")
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
        self.ensure_not_risk("send")

        sent = self._first_matching_locator(self.selectors.sent_message_selectors)
        if sent is None:
            return self._dom_error("sent_message_not_found")
        for index in range(sent.count()):
            try:
                if message in (sent.nth(index).inner_text(timeout=1_000) or ""):
                    self._clear_dom_error()
                    return True
            except Exception:
                continue
        return self._dom_error("sent_message_not_verified")

    def download_candidate_attachment(
        self,
        candidate_id: int,
        candidate_name: str,
        download_dir: Path,
        *,
        boss_id: str = "",
    ) -> Path | None:
        """仅在会话身份唯一匹配时打开聊天并下载附件。"""

        del candidate_id
        conversations = self._first_matching_locator(
            self.selectors.conversation_item_selectors
        )
        if conversations is None:
            return None
        matches: list[Any] = []
        for index in range(conversations.count()):
            item = conversations.nth(index)
            name = self._child_text(item, self.selectors.conversation_name_selectors)
            item_boss_id = ""
            for attribute in self.selectors.conversation_boss_id_attributes:
                try:
                    item_boss_id = item.get_attribute(attribute) or ""
                except Exception:
                    continue
                if item_boss_id:
                    break
            if boss_id and item_boss_id:
                if item_boss_id == boss_id:
                    matches.append(item)
            elif name == candidate_name:
                matches.append(item)
        if len(matches) != 1:
            return None
        try:
            matches[0].click(timeout=5_000)
            self._sleep()
            self.ensure_task_page()
        except PageStateError:
            raise
        except Exception:
            return self._dom_error("conversation_open_failed") and None
        return self.wait_and_download_attachment(download_dir)

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
