import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import AppDrawer from "../../components/AppDrawer.vue";
import EmptyState from "../../components/EmptyState.vue";
import StatusBadge from "../../components/StatusBadge.vue";
import AppShell from "../AppShell.vue";
import type { UserMe } from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return { ...actual, listAgentRuns: vi.fn() };
});

const member: UserMe = {
  id: 2,
  username: "member.hr",
  role: "member",
  is_active: true,
  must_change_password: false,
};

describe("AppShell", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.listAgentRuns).mockRejectedValue(new Error("agent unavailable"));
  });

  it("restores the original shell with honest connection placeholders", async () => {
    const wrapper = mount(AppShell, { props: { user: member } });
    await flushPromises();

    expect(wrapper.text()).toContain("RECRUITING AUTOMATION");
    expect(wrapper.text()).toContain("01");
    expect(wrapper.text()).toContain("05");
    expect(wrapper.text()).not.toContain("06");
    expect(wrapper.find('[aria-label="前往复核中心"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("CURRENT DEVICE");
    expect(wrapper.text()).toContain("BOSS ACCOUNT");
    expect(wrapper.text()).toContain("状态未知");
    expect(wrapper.get('[aria-label="重试 Agent 状态"] .connection-dot').classes()).toContain("connection-dot--unknown");
    expect(wrapper.text()).toContain("状态暂未接入");
    expect(wrapper.text()).toContain("BEYOND THE RESUME");
    expect(wrapper.get(".user-menu").text()).toContain("ME");
  });

  it("retries the Agent summary after a failed request", async () => {
    const wrapper = mount(AppShell, { props: { user: member } });
    await flushPromises();

    expect(wrapper.text()).toContain("状态未知");
    const callsBeforeRetry = vi.mocked(api.listAgentRuns).mock.calls.length;
    vi.mocked(api.listAgentRuns).mockResolvedValue([{ machine_id: "mac-studio", status: "online" } as never]);
    await wrapper.get('[aria-label="重试 Agent 状态"]').trigger("click");
    await flushPromises();

    expect(api.listAgentRuns).toHaveBeenCalledTimes(callsBeforeRetry + 1);
    expect(wrapper.text()).toContain("mac-studio");
  });

  it("switches among all five pages and logs out", async () => {
    vi.mocked(api.listAgentRuns).mockResolvedValue([]);
    const wrapper = mount(AppShell, { props: { user: member } });
    await flushPromises();
    const expected = [
      ["工作台", "dashboard-page"],
      ["岗位管理", "jobs-page"],
      ["候选人", "candidates-page"],
      ["简历库", "resumes-page"],
      ["系统设置", "settings-page"],
    ];

    for (const [label, testId] of expected) {
      await wrapper.get(`button[aria-label="前往${label}"]`).trigger("click");
      expect(wrapper.get(`[data-testid="${testId}"]`)).toBeTruthy();
      expect(wrapper.findAll("[data-page-panel]")).toHaveLength(1);
    }

    await wrapper.get('[aria-label="前往工作台查看 Agent 状态"]').trigger("click");
    expect(wrapper.get('[data-testid="dashboard-page"]')).toBeTruthy();
    expect(wrapper.text()).toContain("LEION HR");
    expect(wrapper.text()).toContain("member.hr");
    await wrapper.get('[aria-label="退出登录"]').trigger("click");
    expect(wrapper.emitted("logout")).toHaveLength(1);
  });

  it("consumes a dashboard job target only once", async () => {
    vi.mocked(api.listAgentRuns).mockResolvedValue([]);
    const wrapper = mount(AppShell, {
      props: { user: member },
      global: {
        stubs: {
          DashboardPage: { template: '<button data-testid="open-job" @click="$emit(\'open-job\', 7, true)">open</button>', emits: ["open-job"] },
          JobsPage: { props: ["targetJobId", "editTarget"], template: '<div data-testid="jobs-page">{{ targetJobId ?? "none" }}-{{ editTarget }}</div>' },
          CandidatesPage: { template: '<div data-testid="candidates-page" />' },
        },
      },
    });
    await flushPromises();

    await wrapper.get('[data-testid="open-job"]').trigger("click");
    expect(wrapper.get('[data-testid="jobs-page"]').text()).toBe("7-true");
    await wrapper.get('button[aria-label="前往候选人"]').trigger("click");
    await wrapper.get('button[aria-label="前往岗位管理"]').trigger("click");

    expect(wrapper.get('[data-testid="jobs-page"]').text()).toBe("none-false");
  });

  it("marks the current navigation item", async () => {
    const wrapper = mount(AppShell, { props: { user: member } });
    const dashboard = wrapper.get('button[aria-label="前往工作台"]');
    const jobs = wrapper.get('button[aria-label="前往岗位管理"]');

    expect(dashboard.attributes("aria-current")).toBe("page");
    await jobs.trigger("click");
    expect(jobs.attributes("aria-current")).toBe("page");
    expect(dashboard.attributes("aria-current")).toBeUndefined();
  });
});

describe("shared interface components", () => {
  it("manages focus and closes an accessible drawer", async () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();
    const wrapper = mount(AppDrawer, {
      props: { open: true, title: "岗位详情" },
      slots: { default: "真实内容" },
      attachTo: document.body,
      global: { stubs: { teleport: true } },
    });
    await Promise.resolve();

    const dialog = wrapper.get('[role="dialog"]');
    const titleId = dialog.attributes("aria-labelledby");
    expect(dialog.attributes("aria-modal")).toBe("true");
    expect(wrapper.get(`#${titleId}`).text()).toBe("岗位详情");
    expect(document.activeElement).toBe(dialog.element);
    expect(wrapper.text()).toContain("真实内容");

    await dialog.trigger("keydown", { key: "Escape" });
    await wrapper.get('[aria-label="关闭岗位详情"]').trigger("click");
    await wrapper.get(".drawer-backdrop").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(3);

    await wrapper.setProps({ open: false });
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
    expect(document.activeElement).toBe(trigger);
    wrapper.unmount();
    trigger.remove();
  });

  it("renders empty-state guidance and status text", () => {
    const empty = mount(EmptyState, {
      props: { title: "暂无岗位", description: "创建岗位后会显示在这里。" },
    });
    const unavailable = mount(EmptyState, {
      props: { title: "统计暂未提供", description: "后端接口暂未接入。", kind: "unavailable" },
    });
    const status = mount(StatusBadge, { props: { label: "在线", tone: "success" } });

    expect(empty.text()).toContain("暂无岗位");
    expect(empty.text()).toContain("创建岗位后会显示在这里。");
    expect(unavailable.classes()).toContain("empty-state--unavailable");
    expect(status.text()).toBe("在线");
    expect(status.classes()).toContain("status-badge--success");
  });
});
