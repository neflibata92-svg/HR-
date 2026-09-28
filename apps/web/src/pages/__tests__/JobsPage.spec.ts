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
    listScreeningTasks: vi.fn(),
    createJob: vi.fn(),
    updateJob: vi.fn(),
    suggestCriticalFields: vi.fn(),
    listCandidates: vi.fn(),
    listResumes: vi.fn(),
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
  critical_fields: [{ key: "portfolio", label: "作品集" }],
  critical_fields_confirmed: true,
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
    vi.mocked(api.listScreeningTasks).mockResolvedValue([]);
    vi.mocked(api.listCandidates).mockResolvedValue([]);
    vi.mocked(api.listResumes).mockResolvedValue([]);
  });

  it("restores job missions statistics and drawer sections from real jobs", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([frontendJob, designerJob]);
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain("JOB MISSIONS.");
    expect(wrapper.get('[data-testid="jobs-total"]').text()).toContain("2");
    expect(wrapper.get('[data-testid="jobs-running"]').text()).toContain("1");
    expect(wrapper.get('[data-testid="jobs-candidates"]').text()).toContain("0");
    expect(wrapper.text()).toContain("负责招聘工作台前端建设");
    expect(wrapper.text()).toContain("最近运行");

    await wrapper.get('[aria-label="查看高级前端工程师详情"]').trigger("click");
    const dialog = wrapper.get('[role="dialog"]');
    for (const text of ["JOB DESCRIPTION", "LAUNCH CONFIGURATION", "AI SCORE THRESHOLD", "GREETING", "TASK STATUS"]) {
      expect(dialog.text()).toContain(text);
    }
    expect(dialog.text()).not.toContain("CRITICAL FIELDS");
    expect(dialog.text()).toContain("BOSS 岗位入口");
    expect(dialog.text()).not.toContain("岗位额度");
  });

  it("shows the complete saved launch configuration without critical fields", async () => {
    const configuredJob: Job = {
      ...frontendJob,
      default_requested_count: 12,
      readiness: { ready: true, missing: [] },
    };
    vi.mocked(api.listJobs).mockResolvedValue([configuredJob]);
    const wrapper = mountPage();
    await flushPromises();
    await wrapper.get('[aria-label="查看高级前端工程师详情"]').trigger("click");

    const dialog = wrapper.get('[role="dialog"]');
    for (const text of [
      "https://www.zhipin.com/web/geek/job", "每小时 20 次", "1500–4000 毫秒",
      "默认筛选 12 人",
    ]) {
      expect(dialog.text()).toContain(text);
    }
    expect(dialog.text()).not.toContain("关键资料");
    expect(api.suggestCriticalFields).not.toHaveBeenCalled();
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

  it("shows real task totals, active state, and history for each job", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([frontendJob]);
    vi.mocked(api.listScreeningTasks).mockResolvedValue([
      {
        id: 8, job_id: 1, created_by_user_id: 1, machine_id: "mac-a",
        assigned_agent_run_id: 3, requested_count: 10, critical_fields: [],
        critical_fields_source: {}, job_name_snapshot: frontendJob.name,
        jd_text_snapshot: frontendJob.jd_text, score_threshold_snapshot: 82,
        greet_template_snapshot: frontendJob.greet_template, status: "running",
        pause_reason: "", processed_count: 4, eligible_count: 3, contacted_count: 2,
        review_count: 1, skipped_count: 0, failed_count: 0,
        created_at: "2026-09-23T10:00:00Z", started_at: "2026-09-23T10:01:00Z", finished_at: null,
      },
      {
        id: 7, job_id: 1, created_by_user_id: 1, machine_id: "mac-a",
        assigned_agent_run_id: 3, requested_count: 5, critical_fields: [],
        critical_fields_source: {}, job_name_snapshot: frontendJob.name,
        jd_text_snapshot: frontendJob.jd_text, score_threshold_snapshot: 82,
        greet_template_snapshot: frontendJob.greet_template, status: "completed",
        pause_reason: "", processed_count: 5, eligible_count: 4, contacted_count: 3,
        review_count: 1, skipped_count: 0, failed_count: 0,
        created_at: "2026-09-22T10:00:00Z", started_at: "2026-09-22T10:01:00Z", finished_at: "2026-09-22T10:10:00Z",
      },
    ]);

    const wrapper = mountPage();
    await flushPromises();

    expect(api.listScreeningTasks).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain("活动任务");
    expect(wrapper.text()).toContain("筛选记录");
    expect(wrapper.text()).toContain("9");
    await wrapper.get('[aria-label="查看高级前端工程师详情"]').trigger("click");
    const dialog = wrapper.get('[role="dialog"]');
    expect(dialog.text()).toContain("任务 #8");
    expect(dialog.text()).toContain("执行中");
    expect(dialog.text()).toContain("已处理 4 / 10");
    expect(dialog.text()).toContain("任务 #7");
    expect(dialog.text()).toContain("已完成");
  });

  it("saves every default configuration required to start a job", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([{
      ...frontendJob,
      default_requested_count: 12,
      critical_fields: [{ key: "portfolio", label: "作品集" }],
      critical_fields_confirmed: true,
      readiness: { ready: true, missing: [] },
    }]);
    vi.mocked(api.updateJob).mockResolvedValue(frontendJob);
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="查看高级前端工程师详情"]').trigger("click");
    await wrapper.get('[aria-label="编辑当前岗位"]').trigger("click");
    await wrapper.get('[aria-label="BOSS 岗位入口"]').setValue("https://www.zhipin.com/job/updated");
    await wrapper.get('[aria-label="每小时招呼上限"]').setValue("18");
    await wrapper.get('[aria-label="最小操作间隔"]').setValue("2000");
    await wrapper.get('[aria-label="最大操作间隔"]').setValue("5000");
    await wrapper.get('[aria-label="默认筛选人数"]').setValue("12");
    await wrapper.get('[role="dialog"] form').trigger("submit");
    await flushPromises();

    expect(api.updateJob).toHaveBeenCalledWith(1, expect.objectContaining({
      boss_entry_url: "https://www.zhipin.com/job/updated",
      hourly_greet_limit: 18,
      min_action_delay_ms: 2000,
      max_action_delay_ms: 5000,
      default_requested_count: 12,
    }));
  });

  it("shows real candidate and resume totals for each job", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([frontendJob]);
    vi.mocked(api.listCandidates).mockImplementation((_q, filters) =>
      Promise.resolve(filters?.jobId === 1 ? [{ id: 1 }, { id: 2 }] as api.Candidate[] : []),
    );
    vi.mocked(api.listResumes).mockImplementation((filters) =>
      Promise.resolve(filters?.jobId === 1 ? [{ id: 11 }] as api.Resume[] : []),
    );
    const wrapper = mountPage();
    await flushPromises();

    expect(api.listCandidates).toHaveBeenCalledWith("", { jobId: 1 });
    expect(api.listResumes).toHaveBeenCalledWith({ jobId: 1 });
    expect(wrapper.get('[data-testid="job-candidate-count-1"]').text()).toBe("2");
    expect(wrapper.get('[data-testid="job-resume-count-1"]').text()).toBe("1");
  });

  it("keeps successful job statistics and exposes a retry when one source fails", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([frontendJob]);
    vi.mocked(api.listCandidates).mockResolvedValue([{ id: 1 }] as api.Candidate[]);
    vi.mocked(api.listResumes)
      .mockRejectedValueOnce(new Error("resume service unavailable"))
      .mockResolvedValueOnce([{ id: 11 }] as api.Resume[]);
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.get('[data-testid="job-candidate-count-1"]').text()).toBe("1");
    expect(wrapper.get('[data-testid="job-resume-count-1"]').text()).not.toBe("0");
    expect(wrapper.get('[data-testid="job-stats-error-1"]').text()).toContain("简历统计加载失败");

    await wrapper.get('[aria-label="重试高级前端工程师统计"]').trigger("click");
    await flushPromises();

    expect(api.listCandidates).toHaveBeenCalledTimes(2);
    expect(api.listResumes).toHaveBeenCalledTimes(2);
    expect(wrapper.get('[data-testid="job-candidate-count-1"]').text()).toBe("1");
    expect(wrapper.get('[data-testid="job-resume-count-1"]').text()).toBe("1");
    expect(wrapper.find('[data-testid="job-stats-error-1"]').exists()).toBe(false);
  });

  it("refreshes task state while the jobs page remains open", async () => {
    vi.useFakeTimers();
    vi.mocked(api.listJobs).mockResolvedValue([frontendJob]);
    vi.mocked(api.listScreeningTasks)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{
        id: 8, job_id: 1, created_by_user_id: 1, machine_id: "mac-a",
        assigned_agent_run_id: 3, requested_count: 10, critical_fields: [], critical_fields_source: {},
        job_name_snapshot: frontendJob.name, jd_text_snapshot: frontendJob.jd_text,
        score_threshold_snapshot: 82, greet_template_snapshot: frontendJob.greet_template,
        status: "running", pause_reason: "", processed_count: 4, eligible_count: 3,
        contacted_count: 2, review_count: 1, skipped_count: 0, failed_count: 0,
        created_at: null, started_at: null, finished_at: null,
      }]);
    const wrapper = mountPage();
    await flushPromises();

    await vi.advanceTimersByTimeAsync(5000);
    await flushPromises();

    expect(api.listScreeningTasks).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("活动任务：执行中");
    wrapper.unmount();
    vi.useRealTimers();
  });

  it("keeps successful jobs visible when task history fails", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([frontendJob]);
    vi.mocked(api.listScreeningTasks).mockRejectedValue(new Error("tasks unavailable"));
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain("高级前端工程师");
    expect(wrapper.get('[data-testid="tasks-sync-error"]').text()).toContain("任务历史加载失败");
    expect(wrapper.find('[aria-label="重试加载岗位"]').exists()).toBe(false);
  });

  it("keeps old task data and exposes retry when polling fails", async () => {
    vi.useFakeTimers();
    const runningTask: api.ScreeningTask = {
      id: 8, job_id: 1, created_by_user_id: 1, machine_id: "mac-a", assigned_agent_run_id: 3,
      requested_count: 10, critical_fields: [], critical_fields_source: {}, job_name_snapshot: frontendJob.name,
      jd_text_snapshot: frontendJob.jd_text, score_threshold_snapshot: 82,
      greet_template_snapshot: frontendJob.greet_template, status: "running", pause_reason: "",
      processed_count: 4, eligible_count: 3, contacted_count: 2, review_count: 1,
      skipped_count: 0, failed_count: 0, created_at: null, started_at: null, finished_at: null,
    };
    vi.mocked(api.listJobs).mockResolvedValue([frontendJob]);
    vi.mocked(api.listScreeningTasks)
      .mockResolvedValueOnce([runningTask])
      .mockRejectedValueOnce(new Error("poll unavailable"))
      .mockResolvedValueOnce([{ ...runningTask, status: "completed" }]);
    const wrapper = mountPage();
    await flushPromises();

    await vi.advanceTimersByTimeAsync(5000);
    await flushPromises();
    expect(wrapper.text()).toContain("活动任务：执行中");
    expect(wrapper.get('[data-testid="tasks-sync-error"]').text()).toContain("任务状态同步失败");

    await wrapper.get('[aria-label="重试任务状态"]').trigger("click");
    await flushPromises();
    expect(wrapper.text()).not.toContain("活动任务：执行中");
    expect(wrapper.find('[data-testid="tasks-sync-error"]').exists()).toBe(false);
    wrapper.unmount();
    vi.useRealTimers();
  });

  it("opens the create form for an empty-workspace navigation target", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([]);
    const wrapper = mount(JobsPage, {
      props: { targetJobId: 0, editTarget: true },
      global: { stubs: { teleport: true } },
    });
    await flushPromises();

    expect(wrapper.get('[role="dialog"]').text()).toContain("新建岗位");
    expect(wrapper.get('[aria-label="岗位名称"]')).toBeTruthy();
  });

  it("keeps a newly created job when an older list request finishes later", async () => {
    let resolveOldList!: (jobs: Job[]) => void;
    vi.mocked(api.listJobs).mockImplementation(() => new Promise((resolve) => { resolveOldList = resolve; }));
    vi.mocked(api.createJob).mockResolvedValue(frontendJob);
    const wrapper = mountPage();

    await wrapper.get('[aria-label="新建岗位"]').trigger("click");
    await wrapper.get('[aria-label="岗位名称"]').setValue("高级前端工程师");
    await wrapper.get('[aria-label="职位描述"]').setValue("负责招聘工作台前端建设");
    await wrapper.get('[role="dialog"] form').trigger("submit");
    await flushPromises();
    resolveOldList([]);
    await flushPromises();

    expect(wrapper.text()).toContain("高级前端工程师");
    expect(wrapper.get('[data-testid="jobs-total"]').text()).toContain("1");
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
      boss_entry_url: "",
      hourly_greet_limit: 20,
      min_action_delay_ms: 1500,
      max_action_delay_ms: 4000,
      default_requested_count: 20,
      critical_fields: [],
      critical_fields_confirmed: false,
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
      boss_entry_url: "https://www.zhipin.com/web/geek/job",
      hourly_greet_limit: 20,
      min_action_delay_ms: 1500,
      max_action_delay_ms: 4000,
      default_requested_count: 20,
      critical_fields: [{ key: "portfolio", label: "作品集" }],
      critical_fields_confirmed: true,
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
