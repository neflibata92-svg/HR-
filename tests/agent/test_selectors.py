from pathlib import Path

from resume_agent.selectors import load_boss_selectors


def test_load_default_selectors() -> None:
    path = Path("apps/agent/boss_selectors.json")
    selectors = load_boss_selectors(path)
    assert "打招呼" in "".join(selectors.greet_button_selectors)
    assert selectors.max_cards_per_run > 0
