import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import FirstPasswordChange from "../FirstPasswordChange.vue";
import * as api from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return { ...actual, changePassword: vi.fn() };
});

describe("FirstPasswordChange", () => {
  it("renders all three password fields and validates confirmation", async () => {
    const wrapper = mount(FirstPasswordChange);
    expect(wrapper.find('[aria-label="当前密码"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="新密码"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="确认新密码"]').exists()).toBe(true);

    await wrapper.get('[aria-label="当前密码"]').setValue("tempPass8");
    await wrapper.get('[aria-label="新密码"]').setValue("newPass88");
    await wrapper.get('[aria-label="确认新密码"]').setValue("different8");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.text()).toContain("两次输入的新密码不一致");
    expect(api.changePassword).not.toHaveBeenCalled();
  });

  it("shows current-password errors and prevents duplicate submissions", async () => {
    let rejectRequest!: (reason: Error) => void;
    vi.mocked(api.changePassword).mockImplementation(
      () => new Promise((_resolve, reject) => { rejectRequest = reject; }),
    );
    const wrapper = mount(FirstPasswordChange);
    await wrapper.get('[aria-label="当前密码"]').setValue("wrongPass8");
    await wrapper.get('[aria-label="新密码"]').setValue("newPass88");
    await wrapper.get('[aria-label="确认新密码"]').setValue("newPass88");
    await wrapper.get("form").trigger("submit");
    await wrapper.get("form").trigger("submit");
    expect(api.changePassword).toHaveBeenCalledTimes(1);

    rejectRequest(new Error("400 current password is incorrect"));
    await flushPromises();
    expect(wrapper.text()).toContain("current password is incorrect");
  });

  it("emits new tokens on success and supports logout", async () => {
    vi.mocked(api.changePassword).mockResolvedValue({
      access_token: "new-access",
      refresh_token: "new-refresh",
      token_type: "bearer",
    });
    const wrapper = mount(FirstPasswordChange);
    await wrapper.get('[aria-label="当前密码"]').setValue("tempPass8");
    await wrapper.get('[aria-label="新密码"]').setValue("newPass88");
    await wrapper.get('[aria-label="确认新密码"]').setValue("newPass88");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.emitted("changed")?.[0]).toEqual(["new-access", "new-refresh"]);
    await wrapper.get('[aria-label="退出登录"]').trigger("click");
    expect(wrapper.emitted("logout")).toHaveLength(1);
  });
});
