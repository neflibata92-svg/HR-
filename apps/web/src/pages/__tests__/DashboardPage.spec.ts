import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import DashboardPage from "../DashboardPage.vue";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return { ...actual, listAgentRuns: vi.fn() };
});

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("shows real agent status without invented dashboard metrics", async () => {
    vi.mocked(api.listAgentRuns).mockResolvedValue([
      {
        id: 1,
        machine_id: "hr-mac-01",
        status: "online",
        last_error: "",
        last_heartbeat: "2026-09-21T09:00:00Z",
      },
    ]);
    const wrapper = mount(DashboardPage);
    await flushPromises();

    expect(wrapper.text()).toContain("hr-mac-01");
    expect(wrapper.text()).toContain("在线");
    expect(wrapper.text()).toContain("2026");
    expect(wrapper.text()).toContain("每位 HR 每日 200 次，全岗位共享");
    expect(wrapper.text()).toContain("统计接口暂未提供");
    expect(wrapper.text()).toContain("动态接口暂未提供");
    expect(wrapper.text()).toContain("任务控制接口暂未提供");
    expect(wrapper.text()).not.toContain("今日发现 128");
    expect(wrapper.text()).not.toContain("已使用 142");
  });

  it("distinguishes a successful empty response", async () => {
    vi.mocked(api.listAgentRuns).mockResolvedValue([]);
    const wrapper = mount(DashboardPage);
    await flushPromises();

    expect(wrapper.text()).toContain("暂无 Agent 设备");
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });

  it("maps paused and offline states and labels device errors", async () => {
    vi.mocked(api.listAgentRuns).mockResolvedValue([
      {
        id: 3,
        machine_id: "paused-agent",
        status: "paused",
        last_error: "risk_page_detected",
        last_heartbeat: "2026-09-21T09:00:00Z",
      },
      {
        id: 4,
        machine_id: "offline-agent",
        status: "offline",
        last_error: "",
        last_heartbeat: null,
      },
    ]);
    const wrapper = mount(DashboardPage);
    await flushPromises();

    expect(wrapper.text()).toContain("已暂停");
    expect(wrapper.text()).toContain("离线");
    expect(wrapper.text()).toContain("最近错误：risk_page_detected");
    expect(wrapper.text()).toContain("本地时间");
    expect(wrapper.get('[aria-label="刷新 Agent 状态"]').text()).toBe("刷新状态");
  });

  it("shows an error and retries instead of pretending the list is empty", async () => {
    vi.mocked(api.listAgentRuns)
      .mockRejectedValueOnce(new Error("503 agent service unavailable"))
      .mockResolvedValueOnce([
        {
          id: 2,
          machine_id: "hr-windows-02",
          status: "idle",
          last_error: "",
          last_heartbeat: null,
        },
      ]);
    const wrapper = mount(DashboardPage);
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("加载 Agent 状态失败");
    expect(wrapper.text()).not.toContain("暂无 Agent 设备");

    await wrapper.get('[aria-label="刷新 Agent 状态"]').trigger("click");
    await flushPromises();
    expect(api.listAgentRuns).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("hr-windows-02");
  });
});
