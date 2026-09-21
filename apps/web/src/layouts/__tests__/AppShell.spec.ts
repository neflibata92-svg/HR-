import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import AppDrawer from "../../components/AppDrawer.vue";
import EmptyState from "../../components/EmptyState.vue";
import StatusBadge from "../../components/StatusBadge.vue";
import AppShell from "../AppShell.vue";
import type { UserMe } from "../../api";

const member: UserMe = {
  id: 2,
  username: "member.hr",
  role: "member",
  is_active: true,
  must_change_password: false,
};

describe("AppShell", () => {
  it("switches among all five pages and logs out", async () => {
    const wrapper = mount(AppShell, { props: { user: member } });
    const expected = [
      ["工作台", "dashboard-page"],
      ["岗位管理", "jobs-page"],
      ["候选人", "candidates-page"],
      ["简历库", "resumes-page"],
      ["系统设置", "settings-page"],
    ];

    for (const [label, testId] of expected) {
      await wrapper.get(`button[aria-label="前往${label}"]`).trigger("click");
      expect(wrapper.get(`[data-testid="${testId}"]`).exists()).toBe(true);
      expect(wrapper.findAll("[data-page-panel]")).toHaveLength(1);
    }

    await wrapper.get('[aria-label="前往工作台查看 Agent 状态"]').trigger("click");
    expect(wrapper.get('[data-testid="dashboard-page"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("LEION HR");
    expect(wrapper.text()).toContain("member.hr");
    await wrapper.get('[aria-label="退出登录"]').trigger("click");
    expect(wrapper.emitted("logout")).toHaveLength(1);
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
    const status = mount(StatusBadge, { props: { label: "在线", tone: "success" } });

    expect(empty.text()).toContain("暂无岗位");
    expect(empty.text()).toContain("创建岗位后会显示在这里。");
    expect(status.text()).toBe("在线");
    expect(status.classes()).toContain("status-badge--success");
  });
});
