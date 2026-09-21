import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import type { Job } from "../../api";
import JobsPage from "../JobsPage.vue";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    listJobs: vi.fn(),
    createJob: vi.fn(),
    updateJob: vi.fn(),
  };
});

const frontendJob: Job = {
  id: 1,
  name: "高级前端工程师",
  jd_text: "负责招聘工作台前端建设",
  score_threshold: 82,
  greet_template: "您好，期待和您沟通前端岗位。",
  boss_entry_url: "https://www.zhipin.com/web/geek/job",
  hourly_greet_limit: 20,
  min_action_delay_ms: 1500,
  max_action_delay_ms: 4000,
  enabled: true,
  created_at: "2026-09-20T08:00:00Z",
};

const designerJob: Job = {
  ...frontendJob,
  id: 2,
  name: "产品设计师",
  jd_text: "负责产品体验设计",
  enabled: false,
};

function mountPage() {
  return mount(JobsPage, {
    global: { stubs: { teleport: true } },
  });
}

describe("JobsPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("restores job missions statistics and drawer sections from real jobs", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([frontendJob, designerJob]);
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain("JOB MISSIONS.");
    expect(wrapper.get('[data-testid="jobs-total"]').text()).toContain("2");
    expect(wrapper.get('[data-testid="jobs-running"]').text()).toContain("1");
    expect(wrapper.get('[data-testid="jobs-candidates"]').text()).toContain("—");
    expect(wrapper.text()).toContain("负责招聘工作台前端建设");
    expect(wrapper.text()).toContain("最近运行");

    await wrapper.get('[aria-label="查看高级前端工程师详情"]').trigger("click");
    const dialog = wrapper.get('[role="dialog"]');
    for (const text of ["JOB DESCRIPTION", "HARD REQUIREMENTS", "AI SCORE THRESHOLD", "GREETING", "TASK STATUS"]) {
      expect(dialog.text()).toContain(text);
    }
    expect(dialog.text()).toContain("硬性条件暂未接入");
    expect(dialog.text()).not.toContain("岗位额度");
  });

  it("loads real jobs and filters them by name and status", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([frontendJob, designerJob]);
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain("高级前端工程师");
    expect(wrapper.text()).toContain("产品设计师");

    await wrapper.get('[aria-label="搜索岗位名称"]').setValue("前端");
    expect(wrapper.text()).toContain("高级前端工程师");
    expect(wrapper.text()).not.toContain("产品设计师");

    await wrapper.get('[aria-label="搜索岗位名称"]').setValue("");
    await wrapper.get('[aria-label="筛选岗位状态"]').setValue("disabled");
    expect(wrapper.text()).not.toContain("高级前端工程师");
    expect(wrapper.text()).toContain("产品设计师");
  });

  it("distinguishes an empty list from a failed request and can retry", async () => {
    vi.mocked(api.listJobs)
      .mockRejectedValueOnce(new Error("503 jobs unavailable"))
      .mockResolvedValueOnce([]);
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("加载岗位失败");
    expect(wrapper.text()).not.toContain("暂无岗位");

    await wrapper.get('[aria-label="重试加载岗位"]').trigger("click");
    await flushPromises();

    expect(api.listJobs).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("暂无岗位");
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });

  it("opens a real job detail when its card is selected", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([frontendJob]);
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="查看高级前端工程师详情"]').trigger("click");

    const dialog = wrapper.get('[role="dialog"]');
    expect(dialog.text()).toContain("负责招聘工作台前端建设");
    expect(dialog.text()).toContain("82");
    expect(dialog.text()).toContain("您好，期待和您沟通前端岗位。");
    expect(dialog.text()).not.toContain("岗位额度");
  });

  it("creates a job with the supported editable fields", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([]);
    vi.mocked(api.createJob).mockResolvedValue(frontendJob);
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="新建岗位"]').trigger("click");
    await wrapper.get('[aria-label="岗位名称"]').setValue("高级前端工程师");
    await wrapper.get('[aria-label="职位描述"]').setValue("负责招聘工作台前端建设");
    await wrapper.get('[aria-label="匹配分数阈值"]').setValue(82);
    await wrapper.get('[aria-label="招呼话术"]').setValue("您好，期待和您沟通前端岗位。");
    await wrapper.get('[role="dialog"] form').trigger("submit");
    await flushPromises();

    expect(api.createJob).toHaveBeenCalledWith({
      name: "高级前端工程师",
      jd_text: "负责招聘工作台前端建设",
      score_threshold: 82,
      greet_template: "您好，期待和您沟通前端岗位。",
    });
    expect(wrapper.text()).toContain("高级前端工程师");
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
  });

  it("edits and disables a job through the update API", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([frontendJob]);
    vi.mocked(api.updateJob)
      .mockResolvedValueOnce({ ...frontendJob, name: "前端技术负责人" })
      .mockResolvedValueOnce({ ...frontendJob, name: "前端技术负责人", enabled: false });
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="查看高级前端工程师详情"]').trigger("click");
    await wrapper.get('[aria-label="编辑当前岗位"]').trigger("click");
    await wrapper.get('[aria-label="岗位名称"]').setValue("前端技术负责人");
    await wrapper.get('[role="dialog"] form').trigger("submit");
    await flushPromises();

    expect(api.updateJob).toHaveBeenNthCalledWith(1, 1, {
      name: "前端技术负责人",
      jd_text: "负责招聘工作台前端建设",
      score_threshold: 82,
      greet_template: "您好，期待和您沟通前端岗位。",
    });
    expect(wrapper.text()).toContain("前端技术负责人");

    await wrapper.get('[aria-label="停用前端技术负责人"]').trigger("click");
    await flushPromises();
    expect(api.updateJob).toHaveBeenNthCalledWith(2, 1, { enabled: false });
    expect(wrapper.text()).toContain("已停用");
  });

  it("locks a job toggle while the update request is pending", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([frontendJob]);
    let resolveRequest!: (job: Job) => void;
    vi.mocked(api.updateJob).mockImplementation(
      () => new Promise((resolve) => { resolveRequest = resolve; }),
    );
    const wrapper = mountPage();
    await flushPromises();

    const toggle = wrapper.get('[aria-label="停用高级前端工程师"]');
    await toggle.trigger("click");
    await toggle.trigger("click");

    expect(api.updateJob).toHaveBeenCalledTimes(1);
    expect(toggle.attributes("disabled")).toBeDefined();
    resolveRequest({ ...frontendJob, enabled: false });
    await flushPromises();
    expect(wrapper.text()).toContain("已停用");
  });

  it("keeps loaded jobs visible when a status update fails", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([frontendJob]);
    vi.mocked(api.updateJob).mockRejectedValue(new Error("500 update failed"));
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="停用高级前端工程师"]').trigger("click");
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("更新岗位状态失败");
    expect(wrapper.text()).toContain("高级前端工程师");
    expect(wrapper.find('[aria-label="重试加载岗位"]').exists()).toBe(false);
  });

  it("keeps an unsaved form open when saving fails and prevents duplicate saves", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([]);
    let rejectRequest!: (error: Error) => void;
    vi.mocked(api.createJob).mockImplementation(
      () => new Promise((_resolve, reject) => { rejectRequest = reject; }),
    );
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="新建岗位"]').trigger("click");
    await wrapper.get('[aria-label="岗位名称"]').setValue("数据分析师");
    await wrapper.get('[aria-label="职位描述"]').setValue("负责业务数据分析");
    await wrapper.get('[aria-label="招呼话术"]').setValue("您好，期待与您沟通。 ");
    await wrapper.get('[role="dialog"] form').trigger("submit");
    await wrapper.get('[role="dialog"] form').trigger("submit");

    expect(api.createJob).toHaveBeenCalledTimes(1);
    expect(wrapper.get('[aria-label="保存岗位"]').attributes("disabled")).toBeDefined();

    rejectRequest(new Error("500 save failed"));
    await flushPromises();
    expect(wrapper.get('[role="dialog"] [role="alert"]').text()).toContain("保存岗位失败");
    expect(wrapper.get<HTMLInputElement>('[aria-label="岗位名称"]').element.value).toBe("数据分析师");
  });
});
