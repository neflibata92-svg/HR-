from __future__ import annotations

from unittest.mock import Mock

import pytest

from resume_agent.boss_live import BossLiveSession, PageStateError, RepeatedDomError
from resume_agent.config import AgentSettings
from resume_agent.parse_page import RawCandidate
from resume_agent.selectors import BossSelectors


def _selectors() -> BossSelectors:
    return BossSelectors(
        login_url="https://example/login",
        default_recommend_url="https://example/recommend",
        card_selectors=[".card"],
        name_selectors=[".name"],
        org_selectors=[".org"],
        greet_button_selectors=[".greet"],
        chat_input_selectors=[".input"],
        send_button_selectors=[".send"],
        conversation_item_selectors=[".conversation"],
        conversation_name_selectors=[".conversation-name"],
        conversation_boss_id_attributes=["data-boss-id"],
        attachment_selectors=[".attachment"],
        sent_message_selectors=[".sent"],
        result_page_url_keywords=["/recommend", "/search"],
        login_url_keywords=["/login"],
        login_keywords=["请登录"],
        captcha_keywords=["验证码"],
        error_keywords=["页面出错"],
        risk_keywords=["异常访问"],
    )


def _page(url: str, html: str):
    page = Mock()
    page.url = url
    page.content.return_value = html
    page.locator.return_value.count.return_value = 0
    return page


@pytest.mark.parametrize(
    ("url", "html", "code"),
    [
        ("https://example/login", "请登录", "login_required"),
        ("https://example/recommend", "请输入验证码", "captcha"),
        ("https://example/recommend", "异常访问", "risk"),
        ("https://example/recommend", "页面出错", "page_error"),
        ("https://example/chat", "普通页面", "not_results_page"),
    ],
)
def test_page_state_rejects_unsafe_or_wrong_pages(url, html, code) -> None:
    session = BossLiveSession(_page(url, html), AgentSettings(api_key="x"), _selectors(), min_delay_ms=0, max_delay_ms=0)
    with pytest.raises(PageStateError, match=code):
        session.ensure_task_page()


def test_candidate_without_stable_identity_never_uses_live_index() -> None:
    page = _page("https://example/recommend", "正常结果")
    cards = Mock()
    cards.count.return_value = 1
    card = Mock()
    card.inner_text.return_value = "王五 30岁 4年经验 公司A"
    card.get_attribute.return_value = None
    card.locator.return_value.count.return_value = 0
    cards.nth.return_value = card
    page.locator.side_effect = lambda selector: cards if selector == ".card" else Mock(count=Mock(return_value=0))
    session = BossLiveSession(page, AgentSettings(api_key="x"), _selectors(), min_delay_ms=0, max_delay_ms=0)

    candidate = session.extract_candidates()[0][0]
    assert candidate.boss_id == ""
    assert not candidate.boss_id.startswith("live-")


def test_greet_verifies_identity_before_clicking() -> None:
    session = BossLiveSession(_page("https://example/recommend", "正常结果"), AgentSettings(api_key="x"), _selectors(), min_delay_ms=0, max_delay_ms=0)
    candidate = RawCandidate("boss-1", "王五", "公司A", 30, 4, 2, 4)
    wrong_card = Mock()
    wrong_card.inner_text.return_value = "赵六 公司B"

    assert session.greet(candidate, "您好", wrong_card) is False
    wrong_card.click.assert_not_called()


def test_greet_rejects_same_name_from_other_company() -> None:
    session = BossLiveSession(_page("https://example/recommend", "正常结果"), AgentSettings(api_key="x"), _selectors(), min_delay_ms=0, max_delay_ms=0)
    candidate = RawCandidate("boss-1", "王五", "公司A", 30, 4, 2, 4)
    wrong_card = Mock()
    wrong_card.inner_text.return_value = "王五 公司B"
    wrong_card.get_attribute.return_value = "boss-2"

    assert session.greet(candidate, "您好", wrong_card) is False
    wrong_card.click.assert_not_called()


def test_page_change_after_click_stops_immediately() -> None:
    page = _page("https://example/recommend", "正常结果")
    session = BossLiveSession(page, AgentSettings(api_key="x"), _selectors(), min_delay_ms=0, max_delay_ms=0)
    candidate = RawCandidate("boss-1", "王五", "公司A", 30, 4, 2, 4)
    card = Mock()
    card.inner_text.return_value = "王五 公司A"
    card.get_attribute.return_value = "boss-1"

    def redirect(*args, **kwargs):
        page.url = "https://example/login"
        page.content.return_value = "请登录"

    card.click.side_effect = redirect
    with pytest.raises(PageStateError, match="login_required"):
        session.greet(candidate, "您好", card)


def test_extract_candidates_honors_task_limit_above_default() -> None:
    page = _page("https://example/recommend", "正常结果")
    cards = Mock()
    cards.count.return_value = 50
    card = Mock()
    card.inner_text.return_value = "王五 公司A"
    card.get_attribute.return_value = None
    card.locator.return_value.count.return_value = 0
    cards.nth.return_value = card
    page.locator.side_effect = lambda selector: cards if selector == ".card" else Mock(count=Mock(return_value=0))
    session = BossLiveSession(page, AgentSettings(api_key="x"), _selectors(), min_delay_ms=0, max_delay_ms=0)

    assert len(session.extract_candidates(limit=50)) == 50


def test_three_same_dom_errors_raise_pause_signal() -> None:
    session = BossLiveSession(_page("https://example/recommend", "正常结果"), AgentSettings(api_key="x"), _selectors(), min_delay_ms=0, max_delay_ms=0)
    candidate = RawCandidate("boss-1", "王五", "公司A", 30, 4, 2, 4)
    card = Mock()
    card.inner_text.return_value = "王五 公司A"
    card.get_attribute.return_value = None
    for _ in range(2):
        assert session.greet(candidate, "您好", card) is False
    with pytest.raises(RepeatedDomError, match="greet_button_missing"):
        session.greet(candidate, "您好", card)


def test_download_candidate_attachment_opens_unique_matching_conversation(tmp_path) -> None:
    page = _page("https://example/recommend", "正常结果")
    conversations = Mock()
    conversations.count.return_value = 1
    conversation = Mock()
    conversation.locator.return_value.count.return_value = 1
    conversation.locator.return_value.first.inner_text.return_value = "王五"
    conversation.get_attribute.side_effect = lambda key: "boss-1" if key == "data-boss-id" else None
    conversations.nth.return_value = conversation
    page.locator.side_effect = lambda selector: conversations if selector == ".conversation" else Mock(count=Mock(return_value=0))
    session = BossLiveSession(page, AgentSettings(api_key="x"), _selectors(), min_delay_ms=0, max_delay_ms=0)
    expected = tmp_path / "王五.pdf"
    session.wait_and_download_attachment = Mock(return_value=expected)

    downloaded = session.download_candidate_attachment(
        3,
        "王五",
        tmp_path,
        boss_id="boss-1",
    )

    assert downloaded == expected
    conversation.click.assert_called_once()
    session.wait_and_download_attachment.assert_called_once_with(tmp_path)


def test_download_candidate_attachment_rejects_ambiguous_same_name(tmp_path) -> None:
    page = _page("https://example/recommend", "正常结果")
    conversations = Mock()
    conversations.count.return_value = 2
    first = Mock()
    second = Mock()
    for item in (first, second):
        item.locator.return_value.count.return_value = 1
        item.locator.return_value.first.inner_text.return_value = "王五"
        item.get_attribute.return_value = None
    conversations.nth.side_effect = [first, second]
    page.locator.side_effect = lambda selector: conversations if selector == ".conversation" else Mock(count=Mock(return_value=0))
    session = BossLiveSession(page, AgentSettings(api_key="x"), _selectors(), min_delay_ms=0, max_delay_ms=0)

    assert session.download_candidate_attachment(3, "王五", tmp_path) is None
    first.click.assert_not_called()
    second.click.assert_not_called()
