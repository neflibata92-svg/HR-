import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HrAccountManagement from "../HrAccountManagement.vue";
import * as api from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    listUsers: vi.fn(),
    createHr: vi.fn(),
    setUserStatus: vi.fn(),
    resetUserPassword: vi.fn(),
  };
});

const admin = {
  id: 1,
  username: "admin",
  role: "admin" as const,
  is_active: true,
  must_change_password: false,
  created_at: "2026-09-20T10:00:00Z",
};
const member = {
  id: 2,
  username: "lisi",
  role: "member" as const,
  is_active: true,
  must_change_password: true,
  created_at: "2026-09-20T11:00:00Z",
};

function mountManagement() {
  return mount(HrAccountManagement, { global: { stubs: { teleport: true } } });
}

describe("HrAccountManagement", () => {
  beforeEach(() => {
    vi.mocked(api.listUsers).mockResolvedValue([admin, member]);
  });

  it("retries a failed account list request", async () => {
    vi.mocked(api.listUsers)
      .mockRejectedValueOnce(new Error("users unavailable"))
      .mockResolvedValueOnce([admin, member]);
    const wrapper = mount(HrAccountManagement, { global: { stubs: { teleport: true } } });
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("users unavailable");
    await wrapper.get('[aria-label="重试加载 HR 账号"]').trigger("click");
    await flushPromises();

    expect(api.listUsers).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("lisi");
  });

  it("shows validation errors inside the active account drawer", async () => {
    const wrapper = mount(HrAccountManagement, { global: { stubs: { teleport: true } } });
    await flushPromises();
    await wrapper.get('[aria-label="新增 HR"]').trigger("click");
    await wrapper.get('[aria-label="用户名"]').setValue("wang.hr");
    await wrapper.get('[aria-label="临时密码"]').setValue("tempPass8");
    await wrapper.get('[aria-label="确认密码"]').setValue("different8");
    await wrapper.get("form").trigger("submit");

    expect(wrapper.get('[role="dialog"] [role="alert"]').text()).toContain("两次输入的密码不一致");
    expect(wrapper.get('[role="dialog"]').classes()).toContain("app-drawer");
  });

  it("shows roles and never offers admin operations", async () => {
    const wrapper = mountManagement();
    await flushPromises();

    expect(wrapper.text()).toContain("HR 总负责人");
    expect(wrapper.text()).toContain("普通 HR");
    expect(wrapper.find('[aria-label="停用 admin"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="停用 lisi"]').exists()).toBe(true);
  });

  it("validates create confirmation before calling the API", async () => {
    const wrapper = mountManagement();
    await flushPromises();
    await wrapper.get('[aria-label="新增 HR"]').trigger("click");
    await wrapper.get('[aria-label="用户名"]').setValue("wang.hr");
    await wrapper.get('[aria-label="临时密码"]').setValue("tempPass8");
    await wrapper.get('[aria-label="确认密码"]').setValue("different8");
    await wrapper.get("form").trigger("submit");

    expect(wrapper.text()).toContain("两次输入的密码不一致");
    expect(api.createHr).not.toHaveBeenCalled();
  });

  it("does not change local status when disable fails or is cancelled", async () => {
    vi.mocked(api.setUserStatus).mockRejectedValueOnce(new Error("network error"));
    const wrapper = mountManagement();
    await flushPromises();

    await wrapper.get('[aria-label="停用 lisi"]').trigger("click");
    await wrapper.get('[aria-label="取消停用"]').trigger("click");
    expect(api.setUserStatus).not.toHaveBeenCalled();

    await wrapper.get('[aria-label="停用 lisi"]').trigger("click");
    await wrapper.get('[aria-label="确认停用"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[aria-label="停用 lisi"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("network error");
  });

  it("validates password reset confirmation before calling the API", async () => {
    const wrapper = mountManagement();
    await flushPromises();

    await wrapper.get('[aria-label="重置 lisi 密码"]').trigger("click");
    await wrapper.get('[aria-label="重置临时密码"]').setValue("resetPass8");
    await wrapper.get('[aria-label="确认重置临时密码"]').setValue("different8");
    await wrapper.get('[aria-label="确认重置密码"]').trigger("click");

    expect(wrapper.text()).toContain("两次输入的密码不一致");
    expect(api.resetUserPassword).not.toHaveBeenCalled();
  });

  it("updates after enable succeeds and confirms password reset", async () => {
    vi.mocked(api.listUsers).mockResolvedValueOnce([{ ...admin }, { ...member, is_active: false }]);
    vi.mocked(api.setUserStatus).mockResolvedValue({ ...member, is_active: true });
    vi.mocked(api.resetUserPassword).mockResolvedValue({ ...member, must_change_password: true });
    const wrapper = mountManagement();
    await flushPromises();

    await wrapper.get('[aria-label="重新启用 lisi"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[aria-label="停用 lisi"]').exists()).toBe(true);

    await wrapper.get('[aria-label="重置 lisi 密码"]').trigger("click");
    await wrapper.get('[aria-label="重置临时密码"]').setValue("resetPass8");
    await wrapper.get('[aria-label="确认重置临时密码"]').setValue("resetPass8");
    await wrapper.get('[aria-label="确认重置密码"]').trigger("click");
    await flushPromises();
    expect(api.resetUserPassword).toHaveBeenCalledWith(2, "resetPass8");
  });
});
