import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "../LoginPage.vue";
import * as api from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return { ...actual, login: vi.fn() };
});

describe("LoginPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("submits trimmed credentials and emits tokens", async () => {
    vi.mocked(api.login).mockResolvedValue({
      access_token: "access",
      refresh_token: "refresh",
      token_type: "bearer",
    });
    const wrapper = mount(LoginPage);

    await wrapper.get('[aria-label="用户名"]').setValue("  hr.one  ");
    await wrapper.get('[aria-label="密码"]').setValue("safePass8");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(api.login).toHaveBeenCalledWith("hr.one", "safePass8");
    expect(wrapper.emitted("authenticated")?.[0]).toEqual(["access", "refresh"]);
    expect(wrapper.text()).not.toContain("注册");
  });

  it("rejects a whitespace-only username before requesting login", async () => {
    const wrapper = mount(LoginPage);
    await wrapper.get('[aria-label="用户名"]').setValue("   ");
    await wrapper.get('[aria-label="密码"]').setValue("safePass8");
    await wrapper.get("form").trigger("submit");

    expect(api.login).not.toHaveBeenCalled();
    expect(wrapper.get('[role="alert"]').text()).toContain("请输入用户名");
  });

  it("prevents duplicate submissions while login is pending", async () => {
    let resolveRequest!: (tokens: api.TokenResponse) => void;
    vi.mocked(api.login).mockImplementation(
      () => new Promise((resolve) => { resolveRequest = resolve; }),
    );
    const wrapper = mount(LoginPage);

    await wrapper.get('[aria-label="用户名"]').setValue("hr.one");
    await wrapper.get('[aria-label="密码"]').setValue("safePass8");
    await wrapper.get("form").trigger("submit");
    await wrapper.get("form").trigger("submit");

    expect(api.login).toHaveBeenCalledTimes(1);
    expect(wrapper.get('button[type="submit"]').attributes("disabled")).toBeDefined();

    resolveRequest({ access_token: "access", refresh_token: "refresh", token_type: "bearer" });
    await flushPromises();
  });

  it("shows an authentication error without emitting tokens", async () => {
    vi.mocked(api.login).mockRejectedValue(new Error("401 用户名或密码错误"));
    const wrapper = mount(LoginPage);

    await wrapper.get('[aria-label="用户名"]').setValue("hr.one");
    await wrapper.get('[aria-label="密码"]').setValue("wrongPass8");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("用户名或密码错误");
    expect(wrapper.emitted("authenticated")).toBeUndefined();
  });
});
