import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App.vue";
import * as api from "../api";
import type { UserMe } from "../api";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    login: vi.fn(),
    register: vi.fn(),
    me: vi.fn(),
    changePassword: vi.fn(),
    listUsers: vi.fn(),
    listJobs: vi.fn(),
    listCandidates: vi.fn(),
    listAgentRuns: vi.fn(),
    listApiKeys: vi.fn(),
  };
});

const member = {
  id: 2,
  username: "member.hr",
  role: "member" as const,
  is_active: true,
  must_change_password: false,
};

const admin = {
  ...member,
  id: 1,
  username: "admin.hr",
  role: "admin" as const,
};

function mockEmptyWorkspace(): void {
  vi.mocked(api.listJobs).mockResolvedValue([]);
  vi.mocked(api.listCandidates).mockResolvedValue([]);
  vi.mocked(api.listAgentRuns).mockResolvedValue([]);
  vi.mocked(api.listApiKeys).mockResolvedValue([]);
  vi.mocked(api.listUsers).mockResolvedValue([]);
}

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
    mockEmptyWorkspace();
  });

  it("shows only login when there is no token", async () => {
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("登录");
    expect(wrapper.text()).not.toContain("创建岗位");
    expect(api.me).not.toHaveBeenCalled();
    expect(api.listJobs).not.toHaveBeenCalled();
  });

  it("loads a member workspace without account management", async () => {
    const wrapper = await mountWithToken(member);

    expect(wrapper.text()).toContain("创建岗位");
    expect(wrapper.text()).not.toContain("HR 账号管理");
    expect(api.listUsers).not.toHaveBeenCalled();
  });

  it("shows account management only for an admin", async () => {
    const wrapper = await mountWithToken(admin);

    expect(wrapper.text()).toContain("HR 账号管理");
    expect(api.listUsers).toHaveBeenCalledTimes(1);
  });

  it("shows only password change and skips workspace requests when required", async () => {
    const wrapper = await mountWithToken({ ...member, must_change_password: true });

    expect(wrapper.text()).toContain("请先修改初始密码");
    expect(wrapper.text()).not.toContain("创建岗位");
    expect(api.listJobs).not.toHaveBeenCalled();
    expect(api.listCandidates).not.toHaveBeenCalled();
    expect(api.listAgentRuns).not.toHaveBeenCalled();
    expect(api.listApiKeys).not.toHaveBeenCalled();
  });

  it("stores changed tokens, confirms user state, then loads workspace", async () => {
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
    expect(api.listJobs).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("创建岗位");
  });

  it("clears invalid tokens when current-user loading returns 401", async () => {
    sessionStorage.setItem("access_token", "expired-access");
    sessionStorage.setItem("refresh_token", "expired-refresh");
    vi.mocked(api.me).mockRejectedValue(new Error("401 unauthorized"));
    const wrapper = mount(App);
    await flushPromises();

    expect(sessionStorage.getItem("access_token")).toBeNull();
    expect(sessionStorage.getItem("refresh_token")).toBeNull();
    expect(wrapper.text()).toContain("登录");
    expect(api.listJobs).not.toHaveBeenCalled();
  });
});
