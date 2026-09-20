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
        page.goto(PROTOTYPE.as_uri(), wait_until="domcontentloaded")

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
        page.goto(PROTOTYPE.as_uri(), wait_until="domcontentloaded")

        password = page.locator("#loginPassword")
        assert password.get_attribute("type") == "password"
        page.get_by_role("button", name="显示密码").click()
        assert password.get_attribute("type") == "text"
        browser.close()


def test_admin_can_create_disable_and_enable_hr() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(PROTOTYPE.as_uri(), wait_until="domcontentloaded")

        page.get_by_role("textbox", name="账号", exact=True).fill("admin")
        page.locator("#loginPassword").fill("adminPass8")
        page.get_by_role("button", name="登录").click()
        page.locator('[data-page="settings"]').click()

        account_management = page.locator("#accountManagement")
        assert account_management.is_visible()
        account_management.get_by_role("button", name="新增 HR").click()
        page.get_by_role("textbox", name="用户名").fill("lisi")
        page.get_by_label("临时密码", exact=True).fill("tempPass8")
        page.get_by_label("确认密码", exact=True).fill("tempPass8")
        page.get_by_role("button", name="创建账号").click()

        row = account_management.get_by_role("row").filter(has_text="lisi")
        assert row.is_visible()
        row.get_by_role("button", name="停用 lisi").click()
        page.get_by_role("button", name="确认停用").click()
        assert "已停用" in row.inner_text()

        row.get_by_role("button", name="重新启用 lisi").click()
        assert "正常" in row.inner_text()
        browser.close()


def test_temporary_password_user_must_change_password() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(PROTOTYPE.as_uri(), wait_until="domcontentloaded")

        page.get_by_role("textbox", name="账号", exact=True).fill("new.hr")
        page.locator("#loginPassword").fill("tempPass8")
        page.get_by_role("button", name="登录").click()

        password_screen = page.locator("#passwordChangeScreen")
        assert password_screen.is_visible()
        assert page.locator(".shell").is_hidden()
        password_screen.get_by_label("当前密码").fill("tempPass8")
        password_screen.get_by_label("新密码", exact=True).fill("newPass88")
        password_screen.get_by_label("确认新密码").fill("newPass88")
        password_screen.get_by_role("button", name="保存新密码").click()

        assert page.locator(".shell").is_visible()
        assert password_screen.is_hidden()
        browser.close()
