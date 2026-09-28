import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import type { ApiKeyRow, UserMe } from "../../api";
import SettingsPage from "../SettingsPage.vue";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    getMyOutreachQuota: vi.fn(),
    listUnknownOutreachEvents: vi.fn(),
    releaseUnknownOutreachEvent: vi.fn(),
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
const lead: UserMe = {
  id: 3, username: "lead.hr", role: "lead", is_active: true, must_change_password: false,
};
const activeKey: ApiKeyRow = {
  id: 3, name: "桌面 Agent", key_prefix: "rsk_live_abcd", created_at: "2026-09-20T08:00:00Z", revoked_at: null,
};
const unknownEvent: api.UnknownOutreachEvent = {
  id: 12,
  candidate_id: 4,
  candidate_name: "李女士",
  job_id: 3,
  job_name: "产品经理",
  quota_owner_username: "hr.one",
  task_id: 8,
  failure_reason: "未能确认发送结果",
  created_at: "2026-09-25T10:00:00Z",
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
    vi.mocked(api.getMyOutreachQuota).mockResolvedValue({
      limit: 200, confirmed: 17, reserved: 3, remaining: 180,
    });
    vi.mocked(api.listUnknownOutreachEvents).mockResolvedValue([]);
    vi.mocked(api.releaseUnknownOutreachEvent).mockResolvedValue({
      id: 12, idempotent_hit: false, candidate_id: 4, screening_record_id: null, job_id: 3,
      task_id: 8, message_snapshot: "你好", status: "released", failure_reason: "经核实未发送",
      manual_override_by_user_id: 1, created_at: "2026-09-25T10:00:00Z", confirmed_at: null,
    });
  });

  it("restores system settings while unsupported policies remain disabled", async () => {
    const wrapper = mountPage();
    await flushPromises();

    for (const text of ["SYSTEM SETTINGS.", "ACCOUNT & CONNECTION", "PERSONAL OUTREACH LIMIT", "累计 200 次", "SAFETY AUTOMATION"]) {
      expect(wrapper.text()).toContain(text);
    }
    expect(wrapper.text()).toContain("已确认 17");
    expect(wrapper.text()).toContain("预留中 3");
    expect(wrapper.text()).toContain("可用 180");
    expect(wrapper.text()).toContain("历史联系只用于去重，不扣新额度");
    expect(wrapper.text()).toContain("BOSS 账号状态暂未接入");
    for (const label of ["随机发送间隔", "登录失效自动暂停", "连续异常自动暂停", "额度耗尽自动暂停"]) {
      expect(wrapper.get(`[aria-label="${label}"]`).attributes("disabled")).toBeDefined();
    }
    expect(wrapper.text()).toContain("服务端策略，前端暂不可修改");
    expect(wrapper.text()).not.toContain("今日");
    expect(api.listUsers).not.toHaveBeenCalled();
    expect(api.listUnknownOutreachEvents).not.toHaveBeenCalled();
  });

  it("shows a quota load error without hiding the fixed limit", async () => {
    vi.mocked(api.getMyOutreachQuota).mockRejectedValue(new Error("503 unavailable"));
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain("累计 200 次");
    expect(wrapper.get('[role="alert"]').text()).toContain("加载联系额度失败");
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

  it("shows lead without granting admin account management", async () => {
    const wrapper = mountPage(lead);
    await flushPromises();

    expect(wrapper.text()).toContain("HR 负责人");
    expect(wrapper.text()).not.toContain("HR 账号管理");
    expect(api.listUsers).not.toHaveBeenCalled();
  });

  it("mounts HR account management only for an admin", async () => {
    const wrapper = mountPage(admin);
    await flushPromises();

    expect(wrapper.text()).toContain("HR 总负责人");
    expect(wrapper.text()).toContain("HR 账号管理");
    expect(api.listUsers).toHaveBeenCalledOnce();
    expect(api.listUnknownOutreachEvents).toHaveBeenCalledOnce();
  });

  it("lets only admins load and review unknown contacts", async () => {
    vi.mocked(api.listUnknownOutreachEvents).mockResolvedValue([unknownEvent]);
    const wrapper = mountPage(admin);
    await flushPromises();

    expect(wrapper.text()).toContain("待核实联系");
    expect(wrapper.text()).toContain("李女士 · 产品经理");
    expect(wrapper.text()).toContain("额度所属 HR：hr.one");
    expect(wrapper.get('label[for="unknown-reason-12"]').text()).toContain("核实理由（必填）");
    const submit = wrapper.get('button[type="submit"]');
    expect(submit.attributes("disabled")).toBeDefined();

    await wrapper.get("textarea").setValue("  ");
    expect(submit.attributes("disabled")).toBeDefined();
    await wrapper.get("textarea").setValue("已核实平台会话记录，确认没有发送");
    expect(submit.attributes("disabled")).toBeDefined();
    await wrapper.get('.unknown-outreach-panel input[type="checkbox"]').setValue(true);
    expect((wrapper.get('.unknown-outreach-panel input[type="checkbox"]').element as HTMLInputElement).checked).toBe(true);
    expect(wrapper.get('button[type="submit"]').attributes("disabled")).toBeUndefined();

    vi.mocked(api.listUnknownOutreachEvents).mockResolvedValueOnce([]);
    await wrapper.get(".unknown-outreach-review").trigger("submit");
    await flushPromises();

    expect(api.releaseUnknownOutreachEvent).toHaveBeenCalledWith(12, "已核实平台会话记录，确认没有发送");
    expect(api.listUnknownOutreachEvents).toHaveBeenCalledTimes(2);
    expect(api.getMyOutreachQuota).toHaveBeenCalledTimes(2);
    expect(wrapper.get('[role="status"]').text()).toContain("已确认候选人“李女士”未发送并退还额度");
    expect(wrapper.text()).toContain("当前没有待核实联系");
  });

  it("shows unknown-contact load and release errors accessibly", async () => {
    vi.mocked(api.listUnknownOutreachEvents).mockRejectedValueOnce(new Error("503 unavailable"));
    const wrapper = mountPage(admin);
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("加载待核实联系失败");

    vi.mocked(api.listUnknownOutreachEvents).mockResolvedValue([unknownEvent]);
    await wrapper.get(".unknown-outreach-panel button").trigger("click");
    await flushPromises();
    vi.mocked(api.releaseUnknownOutreachEvent).mockRejectedValue(new Error("409 conflict"));
    await wrapper.get("textarea").setValue("已人工核实未发送");
    await wrapper.get('.unknown-outreach-panel input[type="checkbox"]').setValue(true);
    await wrapper.get(".unknown-outreach-review").trigger("submit");
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("处理待核实联系失败：409 conflict");
    expect(wrapper.text()).toContain("李女士 · 产品经理");
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
