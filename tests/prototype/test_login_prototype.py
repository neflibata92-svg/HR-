from pathlib import Path

from playwright.sync_api import sync_playwright


PROTOTYPE = (
    Path(__file__).parents[2]
    / ".superpowers/brainstorm/47853-1789903760/content/beyondx-style-dashboard.html"
)


def test_login_and_logout_flow() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(PROTOTYPE.as_uri())

        assert page.get_by_role("heading", name="欢迎回来").is_visible()
        assert page.locator(".shell").is_hidden()

        page.get_by_role("textbox", name="账号", exact=True).fill("demo.hr")
        page.locator("#loginPassword").fill("demo123")
        page.get_by_role("button", name="登录").click()

        assert page.locator(".shell").is_visible()
        page.get_by_role("button", name="退出登录").click()
        assert page.get_by_role("heading", name="欢迎回来").is_visible()
        browser.close()


def test_password_visibility_toggle() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(PROTOTYPE.as_uri())

        password = page.locator("#loginPassword")
        assert password.get_attribute("type") == "password"
        page.get_by_role("button", name="显示密码").click()
        assert password.get_attribute("type") == "text"
        browser.close()
