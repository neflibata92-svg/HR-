from pathlib import Path

from resume_agent.parse_page import detect_risk_page, parse_list_html


def test_parse_fixture() -> None:
    html = Path("tests/fixtures/boss_list.html").read_text(encoding="utf-8")
    cards = parse_list_html(html)
    assert len(cards) == 3
    assert cards[0].name == "王合格"
    assert cards[0].age == 30


def test_detect_risk() -> None:
    assert detect_risk_page("<div>请完成验证</div>") is True
    assert detect_risk_page("<div>正常列表</div>") is False
