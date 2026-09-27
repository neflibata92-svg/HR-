import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App.vue";
import * as api from "../api";
import type { UserMe } from "../api";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    me: vi.fn(),
    changePassword: vi.fn(),
  };
});

const member: UserMe = {
  id: 2,
  username: "member.hr",
  role: "member",
  is_active: true,
  must_change_password: false,
};

async function mountWithToken(user: UserMe = member) {
  sessionStorage.setItem("access_token", "existing-access");
  vi.mocked(api.me).mockResolvedValue(user);
  const wrapper = mount(App);
  await flushPromises();
  return wrapper;
}

describe("App authentication flow", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.resetAllMocks();
  });

  it("shows only login when there is no token", async () => {
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.get('[data-testid="login-page"]')).toBeTruthy();
    expect(wrapper.find('[data-testid="authenticated-app"]').exists()).toBe(false);
    expect(wrapper.text()).not.toContain("注册");
    expect(api.me).not.toHaveBeenCalled();
  });

  it("shows the authenticated application after confirming the user", async () => {
    const wrapper = await mountWithToken();

    expect(wrapper.get('[data-testid="authenticated-app"]').text()).toContain("member.hr");
    expect(wrapper.getComponent({ name: "AppShell" }).props("user")).toEqual(member);
    expect(wrapper.find('[data-testid="login-page"]').exists()).toBe(false);
  });

  it("shows only password change when required", async () => {
    const wrapper = await mountWithToken({ ...member, must_change_password: true });

    expect(wrapper.text()).toContain("请先修改初始密码");
    expect(wrapper.find('[data-testid="authenticated-app"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="login-page"]').exists()).toBe(false);
  });

  it("stores changed tokens and confirms user state again", async () => {
    sessionStorage.setItem("access_token", "old-access");
    vi.mocked(api.me)
      .mockResolvedValueOnce({ ...member, must_change_password: true })
      .mockResolvedValueOnce(member);
    vi.mocked(api.changePassword).mockResolvedValue({
      access_token: "new-access",
      refresh_token: "new-refresh",
      token_type: "bearer",
    });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get('[aria-label="当前密码"]').setValue("tempPass8");
    await wrapper.get('[aria-label="新密码"]').setValue("newPass88");
    await wrapper.get('[aria-label="确认新密码"]').setValue("newPass88");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(sessionStorage.getItem("access_token")).toBe("new-access");
    expect(sessionStorage.getItem("refresh_token")).toBe("new-refresh");
    expect(api.me).toHaveBeenCalledTimes(2);
    expect(wrapper.get('[data-testid="authenticated-app"]').text()).toContain("member.hr");
  });

  it("shows a retryable error when current-user loading fails", async () => {
    sessionStorage.setItem("access_token", "existing-access");
    vi.mocked(api.me)
      .mockRejectedValueOnce(new Error("503 service unavailable"))
      .mockResolvedValueOnce(member);
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("503 service unavailable");
    expect(wrapper.find('[data-testid="login-page"]').exists()).toBe(false);

    await wrapper.get('[aria-label="重试确认登录状态"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-testid="authenticated-app"]')).toBeTruthy();
  });

  it("clears invalid tokens and returns to login on a 401", async () => {
    sessionStorage.setItem("access_token", "expired-access");
    sessionStorage.setItem("refresh_token", "expired-refresh");
    vi.mocked(api.me).mockRejectedValue(new Error("401 unauthorized"));
    const wrapper = mount(App);
    await flushPromises();

    expect(sessionStorage.getItem("access_token")).toBeNull();
    expect(sessionStorage.getItem("refresh_token")).toBeNull();
    expect(wrapper.get('[data-testid="login-page"]')).toBeTruthy();
  });

  it("clears tokens and returns to login when an authenticated API reports 401", async () => {
    const wrapper = await mountWithToken();
    sessionStorage.setItem("refresh_token", "existing-refresh");

    window.dispatchEvent(new Event("resume-screening:unauthorized"));
    await wrapper.vm.$nextTick();

    expect(sessionStorage.getItem("access_token")).toBeNull();
    expect(sessionStorage.getItem("refresh_token")).toBeNull();
    expect(wrapper.get('[data-testid="login-page"]')).toBeTruthy();
  });

  it("stores login tokens before confirming the current user", async () => {
    vi.mocked(api.me).mockResolvedValue(member);
    const wrapper = mount(App);

    await wrapper.getComponent({ name: "LoginPage" }).vm.$emit("authenticated", "access", "refresh");
    await flushPromises();

    expect(sessionStorage.getItem("access_token")).toBe("access");
    expect(sessionStorage.getItem("refresh_token")).toBe("refresh");
    expect(api.me).toHaveBeenCalledTimes(1);
    expect(wrapper.get('[data-testid="authenticated-app"]')).toBeTruthy();
  });
});
