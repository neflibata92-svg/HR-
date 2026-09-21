import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import type { ApiKeyRow, UserMe } from "../../api";
import SettingsPage from "../SettingsPage.vue";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    listApiKeys: vi.fn(),
    createApiKey: vi.fn(),
    revokeApiKey: vi.fn(),
    listUsers: vi.fn(),
  };
});

const member: UserMe = {
  id: 2, username: "member.hr", role: "member", is_active: true, must_change_password: false,
};
const admin: UserMe = {
  id: 1, username: "admin.hr", role: "admin", is_active: true, must_change_password: false,
};
const activeKey: ApiKeyRow = {
  id: 3, name: "桌面 Agent", key_prefix: "rsk_live_abcd", created_at: "2026-09-20T08:00:00Z", revoked_at: null,
};

function mountPage(user: UserMe = member) {
  return mount(SettingsPage, {
    props: { user },
    global: { stubs: { teleport: true } },
  });
}

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.listApiKeys).mockResolvedValue([activeKey]);
    vi.mocked(api.listUsers).mockResolvedValue([]);
  });

  it("restores system settings while unsupported policies remain disabled", async () => {
    const wrapper = mountPage();
    await flushPromises();

    for (const text of ["SYSTEM SETTINGS.", "ACCOUNT & CONNECTION", "DAILY SHARED QUOTA", "200 次 / 天", "SAFETY AUTOMATION"]) {
      expect(wrapper.text()).toContain(text);
    }
    expect(wrapper.text()).toContain("BOSS 账号状态暂未接入");
    for (const label of ["随机发送间隔", "登录失效自动暂停", "连续异常自动暂停", "额度耗尽自动暂停"]) {
      expect(wrapper.get(`[aria-label="${label}"]`).attributes("disabled")).toBeDefined();
    }
    expect(wrapper.text()).toContain("服务端策略，前端暂不可修改");
    expect(wrapper.text()).not.toMatch(/今日已用 126|剩余 74/);
    expect(api.listUsers).not.toHaveBeenCalled();
  });

  it("shows the member account and personal keys without loading HR management", async () => {
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain("member.hr");
    expect(wrapper.text()).toContain("普通 HR");
    expect(wrapper.text()).toContain("桌面 Agent");
    expect(wrapper.text()).toContain("大模型 Key 仅在服务端配置");
    expect(wrapper.text()).toContain("共享额度");
    expect(api.listApiKeys).toHaveBeenCalledOnce();
    expect(api.listUsers).not.toHaveBeenCalled();
    expect(wrapper.text()).not.toContain("HR 账号管理");
  });

  it("mounts HR account management only for an admin", async () => {
    const wrapper = mountPage(admin);
    await flushPromises();

    expect(wrapper.text()).toContain("HR 总负责人");
    expect(wrapper.text()).toContain("HR 账号管理");
    expect(api.listUsers).toHaveBeenCalledOnce();
  });

  it("distinguishes a failed key load from an empty list and retries", async () => {
    vi.mocked(api.listApiKeys)
      .mockRejectedValueOnce(new Error("503 keys unavailable"))
      .mockResolvedValueOnce([]);
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("加载 Agent Key 失败");
    expect(wrapper.text()).not.toContain("暂未创建 Agent Key");

    await wrapper.get('[aria-label="重试加载 Agent Key"]').trigger("click");
    await flushPromises();
    expect(api.listApiKeys).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("暂未创建 Agent Key");
  });

  it("requires a key name and reveals a newly created key only once", async () => {
    vi.mocked(api.createApiKey).mockResolvedValue({
      id: 4,
      name: "浏览器 Agent",
      key_prefix: "rsk_live_xyz1",
      api_key: "rsk_live_xyz123-secret",
      created_at: "2026-09-21T10:00:00Z",
    });
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="创建 Agent Key"]').trigger("click");
    await wrapper.get('[aria-label="确认创建 Agent Key"]').trigger("click");
    expect(api.createApiKey).not.toHaveBeenCalled();
    expect(wrapper.get('[role="dialog"] [role="alert"]').text()).toContain("请输入 Key 名称");
    expect(wrapper.get('[role="dialog"]').classes()).toContain("app-drawer");

    await wrapper.get('[aria-label="Agent Key 名称"]').setValue(" 浏览器 Agent ");
    await wrapper.get('[aria-label="确认创建 Agent Key"]').trigger("click");
    await flushPromises();

    expect(api.createApiKey).toHaveBeenCalledWith("浏览器 Agent");
    expect(wrapper.text()).toContain("rsk_live_xyz123-secret");
    expect(wrapper.text()).toContain("仅显示这一次");

    await wrapper.get('[aria-label="关闭 Agent Key 明文"]').trigger("click");
    expect(wrapper.text()).not.toContain("rsk_live_xyz123-secret");
    expect(wrapper.text()).toContain("浏览器 Agent");
  });

  it("revokes a key and updates its state", async () => {
    vi.mocked(api.revokeApiKey).mockResolvedValue({
      ...activeKey, revoked_at: "2026-09-21T11:00:00Z",
    });
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="吊销桌面 Agent"]').trigger("click");
    await flushPromises();

    expect(api.revokeApiKey).toHaveBeenCalledWith(3);
    expect(wrapper.text()).toContain("已吊销");
    expect(wrapper.find('[aria-label="吊销桌面 Agent"]').exists()).toBe(false);
  });

  it("keeps the key list when creation or revocation fails", async () => {
    vi.mocked(api.createApiKey).mockRejectedValue(new Error("500 create failed"));
    vi.mocked(api.revokeApiKey).mockRejectedValue(new Error("500 revoke failed"));
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="创建 Agent Key"]').trigger("click");
    await wrapper.get('[aria-label="Agent Key 名称"]').setValue("失败 Key");
    await wrapper.get('[aria-label="确认创建 Agent Key"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("创建 Agent Key 失败");
    expect(wrapper.text()).toContain("桌面 Agent");

    await wrapper.get('[aria-label="吊销桌面 Agent"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("吊销 Agent Key 失败");
    expect(wrapper.text()).toContain("桌面 Agent");
  });
});
