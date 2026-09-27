import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import DashboardPage from "../DashboardPage.vue";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    listAgentRuns: vi.fn(),
    listJobs: vi.fn(),
    listScreeningTasks: vi.fn(),
    createScreeningTask: vi.fn(),
    getScreeningTask: vi.fn(),
    suggestCriticalFields: vi.fn(),
    pauseScreeningTask: vi.fn(),
    resumeScreeningTask: vi.fn(),
    cancelScreeningTask: vi.fn(),
    listCandidates: vi.fn(),
    listResumes: vi.fn(),
    listReviews: vi.fn(),
  };
});

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.listJobs).mockResolvedValue([]);
    vi.mocked(api.listAgentRuns).mockResolvedValue([]);
    vi.mocked(api.listScreeningTasks).mockResolvedValue([]);
    vi.mocked(api.listCandidates).mockResolvedValue([]);
    vi.mocked(api.listResumes).mockResolvedValue([]);
    vi.mocked(api.listReviews).mockResolvedValue([]);
    vi.mocked(api.suggestCriticalFields).mockResolvedValue({ suggestions: [], model: "configured-model" });
  });

  it("replaces unsupported placeholder modules with the real job operations workspace", async () => {
    const wrapper = mount(DashboardPage);
    await flushPromises();

    expect(wrapper.text()).toContain("FIND.");
    expect(wrapper.text()).toContain("SCORE.");
    expect(wrapper.text()).toContain("CONNECT.");
    expect(wrapper.text()).toContain("暂无招聘岗位");
    expect(wrapper.get('[aria-label="创建第一个岗位"]')).toBeTruthy();
    expect(wrapper.text()).not.toContain("统计接口暂未提供");
    expect(wrapper.text()).not.toContain("实时动态暂未接入");
    expect(wrapper.text()).not.toContain("用量接口暂未接入");
    expect(wrapper.text()).not.toMatch(/326|148|126|37|王女士|李先生/);
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
    expect(wrapper.text()).not.toContain("统计接口暂未提供");
    expect(wrapper.text()).not.toContain("动态接口暂未提供");
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

  it("uses the job JD without showing a separate critical-fields form", async () => {
    vi.mocked(api.listAgentRuns).mockResolvedValue([]);
    vi.mocked(api.listJobs).mockResolvedValue([{
      id: 7, name: "资深产品经理", jd_text: "JD", score_threshold: 85,
      greet_template: "你好", boss_entry_url: "", hourly_greet_limit: 0,
      min_action_delay_ms: 0, max_action_delay_ms: 0, enabled: true, created_at: null,
    }]);
    const wrapper = mount(DashboardPage);
    await flushPromises();
    await wrapper.get('[aria-label="新建筛选任务"]').trigger("click");

    expect(api.suggestCriticalFields).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("完整 JD 自动评分");
    expect(wrapper.text()).not.toContain("关键资料");
  });

  it("refreshes a current task from the server", async () => {
    vi.mocked(api.listAgentRuns).mockResolvedValue([]);
    vi.mocked(api.listJobs).mockResolvedValue([{
      id: 7, name: "产品经理", jd_text: "JD", score_threshold: 80,
      greet_template: "你好", boss_entry_url: "", hourly_greet_limit: 0,
      min_action_delay_ms: 0, max_action_delay_ms: 0, enabled: true, created_at: null,
    }]);
    vi.mocked(api.suggestCriticalFields).mockResolvedValue({
      suggestions: [{ key: "portfolio", label: "作品集", reason: "岗位要求" }],
      model: "configured-model",
    });
    const ready = {
      id: 15, job_id: 7, created_by_user_id: 1, machine_id: null, requested_count: 10,
      critical_fields: [{ key: "portfolio", label: "作品集" }], critical_fields_source: { confirmed: true },
      job_name_snapshot: "产品经理", jd_text_snapshot: "JD", score_threshold_snapshot: 80,
      greet_template_snapshot: "你好", status: "ready", pause_reason: "", processed_count: 0,
      eligible_count: 0, contacted_count: 0, review_count: 0, skipped_count: 0, failed_count: 0,
      created_at: null, started_at: null, finished_at: null,
    };
    vi.mocked(api.listScreeningTasks).mockResolvedValue([ready]);
    vi.mocked(api.getScreeningTask).mockResolvedValue({ ...ready, status: "running", processed_count: 4 });
    const wrapper = mount(DashboardPage);
    await flushPromises();
    await wrapper.get('[aria-label="刷新当前任务"]').trigger("click");
    await flushPromises();

    expect(api.getScreeningTask).toHaveBeenCalledWith(15);
    expect(wrapper.text()).toContain("已处理 4 / 10 人");
    expect(wrapper.get('[aria-label="暂停任务"]')).toBeTruthy();
  });

  it("creates a confirmed task and only shows legal state actions", async () => {
    vi.mocked(api.listAgentRuns).mockResolvedValue([{
      id: 4,
      machine_id: "idle-mac",
      status: "idle",
      availability: "idle",
      current_task_id: null,
      current_job_id: null,
      boss_login_status: "logged_in",
      last_error: "",
      last_heartbeat: new Date().toISOString(),
    }]);
    vi.mocked(api.listJobs).mockResolvedValue([{
      id: 7,
      name: "资深产品经理",
      jd_text: "负责产品策略与交付",
      score_threshold: 85,
      greet_template: "你好",
      boss_entry_url: "",
      hourly_greet_limit: 0,
      min_action_delay_ms: 0,
      max_action_delay_ms: 0,
      default_requested_count: 20,
      critical_fields: [],
      critical_fields_confirmed: false,
      readiness: { ready: true, missing: [] },
      enabled: true,
      created_at: null,
    }]);
    vi.mocked(api.suggestCriticalFields).mockResolvedValue({
      suggestions: [{ key: "portfolio", label: "作品集", reason: "岗位要求作品集" }],
      model: "configured-model",
    });
    vi.mocked(api.createScreeningTask).mockResolvedValue({
      id: 12,
      job_id: 7,
      created_by_user_id: 1,
      machine_id: null,
      requested_count: 20,
      critical_fields: [{ key: "portfolio", label: "作品集" }],
      critical_fields_source: { confirmed: true, source: "manual" },
      job_name_snapshot: "资深产品经理",
      jd_text_snapshot: "负责产品策略与交付",
      score_threshold_snapshot: 85,
      greet_template_snapshot: "你好",
      status: "ready",
      pause_reason: "",
      processed_count: 0,
      eligible_count: 0,
      contacted_count: 0,
      review_count: 0,
      skipped_count: 0,
      failed_count: 0,
      created_at: null,
      started_at: null,
      finished_at: null,
    });
    const wrapper = mount(DashboardPage);
    await flushPromises();

    await wrapper.get('[aria-label="新建筛选任务"]').trigger("click");
    await wrapper.get('[aria-label="任务岗位"]').setValue("7");
    await flushPromises();
    await wrapper.get('[aria-label="筛选人数"]').setValue("20");
    await wrapper.get('[aria-label="任务 Agent"]').setValue("4");
    await wrapper.get('[aria-label="筛选任务表单"]').trigger("submit");
    await flushPromises();

    expect(api.createScreeningTask).toHaveBeenCalledWith({
      job_id: 7,
      assigned_agent_run_id: 4,
      requested_count: 20,
    });
    expect(wrapper.text()).toContain("任务 #12");
    expect(wrapper.find('[aria-label="暂停任务"]').exists()).toBe(false);
    expect(wrapper.get('[aria-label="停止任务"]').attributes("disabled")).toBeUndefined();
  });

  it("pauses a running task and then exposes resume", async () => {
    vi.mocked(api.listAgentRuns).mockResolvedValue([]);
    vi.mocked(api.listJobs).mockResolvedValue([{
      id: 7, name: "产品经理", jd_text: "JD", score_threshold: 80,
      greet_template: "你好", boss_entry_url: "", hourly_greet_limit: 0,
      min_action_delay_ms: 0, max_action_delay_ms: 0, enabled: true, created_at: null,
    }]);
    vi.mocked(api.suggestCriticalFields).mockResolvedValue({
      suggestions: [{ key: "portfolio", label: "作品集", reason: "岗位要求" }],
      model: "configured-model",
    });
    const running = {
      id: 15, job_id: 7, created_by_user_id: 1, machine_id: "mac-a", requested_count: 10,
      critical_fields: [], critical_fields_source: { confirmed: true, source: "manual" }, job_name_snapshot: "产品经理",
      jd_text_snapshot: "JD", score_threshold_snapshot: 80, greet_template_snapshot: "你好", status: "running",
      pause_reason: "", processed_count: 4, eligible_count: 3, contacted_count: 2, review_count: 1,
      skipped_count: 0, failed_count: 0, created_at: null, started_at: null, finished_at: null,
    };
    vi.mocked(api.listScreeningTasks).mockResolvedValue([running]);
    vi.mocked(api.pauseScreeningTask).mockResolvedValue({ ...running, status: "paused", pause_reason: "人工检查" });
    const wrapper = mount(DashboardPage);
    await flushPromises();

    await wrapper.get('[aria-label="暂停任务"]').trigger("click");
    await flushPromises();

    expect(api.pauseScreeningTask).toHaveBeenCalledWith(15, "人工检查");
    expect(wrapper.get('[aria-label="继续任务"]')).toBeTruthy();
  });

  it("restores the active task and assigned agent after refresh", async () => {
    vi.mocked(api.listAgentRuns).mockResolvedValue([{
      id: 3,
      machine_id: "hr-mac",
      status: "running",
      availability: "busy",
      current_task_id: 9,
      current_job_id: 1,
      boss_login_status: "logged_in",
      last_error: "",
      last_heartbeat: "2026-09-23T10:00:00Z",
    }]);
    vi.mocked(api.listJobs).mockResolvedValue([{
      id: 1, name: "后端工程师", jd_text: "Python", score_threshold: 80,
      greet_template: "您好", boss_entry_url: "https://www.zhipin.com/job/1",
      hourly_greet_limit: 20, min_action_delay_ms: 1500, max_action_delay_ms: 4000,
      default_requested_count: 5, critical_fields: [{ key: "degree", label: "学历" }],
      critical_fields_confirmed: true, readiness: { ready: true, missing: [] },
      enabled: true, created_at: null,
    }]);
    vi.mocked(api.listScreeningTasks).mockResolvedValue([{
      id: 9, job_id: 1, created_by_user_id: 1, machine_id: "hr-mac",
      assigned_agent_run_id: 3, requested_count: 5,
      critical_fields: [{ key: "degree", label: "学历" }],
      critical_fields_source: { confirmed: true }, job_name_snapshot: "后端工程师",
      jd_text_snapshot: "Python", score_threshold_snapshot: 80,
      greet_template_snapshot: "您好", status: "running", pause_reason: "",
      processed_count: 3, eligible_count: 2, contacted_count: 1, review_count: 1,
      skipped_count: 0, failed_count: 0, created_at: null, started_at: null, finished_at: null,
    }]);

    const wrapper = mount(DashboardPage);
    await flushPromises();

    expect(api.listScreeningTasks).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain("任务 #9 · 后端工程师");
    expect(wrapper.text()).toContain("已处理 3 / 5 人");
    expect(wrapper.text()).toContain("执行设备：hr-mac");
    expect(wrapper.get('[aria-label="暂停任务"]')).toBeTruthy();
  });

  it("creates a task with the selected ready agent", async () => {
    vi.mocked(api.listAgentRuns).mockResolvedValue([{
      id: 3,
      machine_id: "idle-mac",
      status: "idle",
      availability: "idle",
      current_task_id: null,
      current_job_id: null,
      boss_login_status: "logged_in",
      last_error: "",
      last_heartbeat: new Date().toISOString(),
    }]);
    vi.mocked(api.listJobs).mockResolvedValue([{
      id: 1, name: "后端工程师", jd_text: "Python", score_threshold: 80,
      greet_template: "您好", boss_entry_url: "https://www.zhipin.com/job/1",
      hourly_greet_limit: 20, min_action_delay_ms: 1500, max_action_delay_ms: 4000,
      default_requested_count: 5, critical_fields: [{ key: "degree", label: "学历" }],
      critical_fields_confirmed: true, readiness: { ready: true, missing: [] },
      enabled: true, created_at: null,
    }]);
    vi.mocked(api.createScreeningTask).mockResolvedValue({
      id: 10, job_id: 1, created_by_user_id: 1, machine_id: null,
      assigned_agent_run_id: 3, requested_count: 5,
      critical_fields: [{ key: "degree", label: "学历" }],
      critical_fields_source: { confirmed: true }, job_name_snapshot: "后端工程师",
      jd_text_snapshot: "Python", score_threshold_snapshot: 80,
      greet_template_snapshot: "您好", status: "ready", pause_reason: "",
      processed_count: 0, eligible_count: 0, contacted_count: 0, review_count: 0,
      skipped_count: 0, failed_count: 0, created_at: null, started_at: null, finished_at: null,
    });
    const wrapper = mount(DashboardPage);
    await flushPromises();

    await wrapper.get('[aria-label="新建筛选任务"]').trigger("click");
    await wrapper.get('[aria-label="任务岗位"]').setValue("1");
    await flushPromises();
    await wrapper.get('[aria-label="任务 Agent"]').setValue("3");
    await wrapper.get('[aria-label="筛选任务表单"]').trigger("submit");
    await flushPromises();

    expect(api.createScreeningTask).toHaveBeenCalledWith({
      job_id: 1,
      assigned_agent_run_id: 3,
      requested_count: 5,
    });
    expect(wrapper.text()).toContain("等待领取");
  });

  it("excludes an idle agent whose heartbeat is stale", async () => {
    vi.setSystemTime(new Date("2026-09-23T10:05:00Z"));
    vi.mocked(api.listAgentRuns).mockResolvedValue([{
      id: 3,
      machine_id: "stale-mac",
      status: "idle",
      availability: "idle",
      current_task_id: null,
      current_job_id: null,
      boss_login_status: "logged_in",
      last_error: "",
      last_heartbeat: "2026-09-23T10:00:00Z",
    }]);
    const wrapper = mount(DashboardPage);
    await flushPromises();
    await wrapper.get('[aria-label="新建筛选任务"]').trigger("click");

    expect(wrapper.find('[aria-label="任务 Agent"] option[value="3"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("没有在线、空闲且已登录 BOSS 的 Agent");
    vi.useRealTimers();
  });

  it("restores and displays every active task", async () => {
    const baseTask = {
      id: 9, job_id: 1, created_by_user_id: 1, machine_id: "mac-a",
      assigned_agent_run_id: 3, requested_count: 5, critical_fields: [],
      critical_fields_source: {}, job_name_snapshot: "后端工程师", jd_text_snapshot: "Python",
      score_threshold_snapshot: 80, greet_template_snapshot: "您好", status: "running",
      pause_reason: "", processed_count: 3, eligible_count: 2, contacted_count: 1,
      review_count: 1, skipped_count: 0, failed_count: 0, created_at: null,
      started_at: null, finished_at: null,
    };
    vi.mocked(api.listAgentRuns).mockResolvedValue([]);
    vi.mocked(api.listScreeningTasks).mockResolvedValue([
      baseTask,
      { ...baseTask, id: 10, job_id: 2, job_name_snapshot: "产品经理", status: "paused" },
    ]);

    const wrapper = mount(DashboardPage);
    await flushPromises();

    expect(wrapper.text()).toContain("任务 #9 · 后端工程师");
    expect(wrapper.text()).toContain("任务 #10 · 产品经理");
    expect(wrapper.findAll('[data-testid="active-task-card"]')).toHaveLength(2);
  });

  it("discovers new tasks and refreshes agents while the dashboard stays open", async () => {
    vi.useFakeTimers();
    const task = {
      id: 21, job_id: 1, created_by_user_id: 1, machine_id: "mac-live",
      assigned_agent_run_id: 7, requested_count: 5, critical_fields: [], critical_fields_source: {},
      job_name_snapshot: "算法工程师", jd_text_snapshot: "Python", score_threshold_snapshot: 80,
      greet_template_snapshot: "您好", status: "running", pause_reason: "", processed_count: 1,
      eligible_count: 1, contacted_count: 0, review_count: 0, skipped_count: 0, failed_count: 0,
      created_at: null, started_at: null, finished_at: null,
    };
    vi.mocked(api.listAgentRuns)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{
        id: 7, machine_id: "mac-live", status: "running", availability: "busy",
        current_task_id: 21, current_job_id: 1, boss_login_status: "logged_in",
        last_error: "", last_heartbeat: new Date().toISOString(),
      }]);
    vi.mocked(api.listScreeningTasks)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([task]);
    const wrapper = mount(DashboardPage);
    await flushPromises();

    await vi.advanceTimersByTimeAsync(5000);
    await flushPromises();

    expect(api.listScreeningTasks).toHaveBeenCalledTimes(2);
    expect(api.listAgentRuns).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("任务 #21 · 算法工程师");
    expect(wrapper.text()).toContain("mac-live");
    wrapper.unmount();
    vi.useRealTimers();
  });

  it("shows one real workspace card per job without mixing operational data", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([
      {
        id: 1, name: "后端工程师", jd_text: "Python", score_threshold: 80,
        greet_template: "您好", boss_entry_url: "https://www.zhipin.com/job/1",
        hourly_greet_limit: 20, min_action_delay_ms: 1500, max_action_delay_ms: 4000,
        default_requested_count: 5, critical_fields: [{ key: "degree", label: "学历" }],
        critical_fields_confirmed: true, readiness: { ready: true, missing: [] },
        enabled: true, created_at: null,
      },
      {
        id: 2, name: "产品经理", jd_text: "产品规划", score_threshold: 85,
        greet_template: "您好", boss_entry_url: "", hourly_greet_limit: 20,
        min_action_delay_ms: 1500, max_action_delay_ms: 4000,
        default_requested_count: 8, critical_fields: [], critical_fields_confirmed: false,
        readiness: { ready: false, missing: ["boss_entry_url"] },
        enabled: true, created_at: null,
      },
    ]);
    vi.mocked(api.listAgentRuns).mockResolvedValue([{
      id: 3, machine_id: "hr-mac", status: "online", availability: "busy",
      current_task_id: 9, current_job_id: 1, boss_login_status: "logged_in",
      last_error: "", last_heartbeat: new Date().toISOString(),
    }]);
    vi.mocked(api.listScreeningTasks).mockResolvedValue([{
      id: 9, job_id: 1, created_by_user_id: 1, machine_id: "hr-mac",
      assigned_agent_run_id: 3, requested_count: 5, critical_fields: [], critical_fields_source: {},
      job_name_snapshot: "后端工程师", jd_text_snapshot: "Python", score_threshold_snapshot: 80,
      greet_template_snapshot: "您好", status: "running", pause_reason: "", processed_count: 3,
      eligible_count: 2, contacted_count: 1, review_count: 1, skipped_count: 0, failed_count: 0,
      created_at: null, started_at: null, finished_at: null,
    }]);
    vi.mocked(api.listCandidates).mockImplementation((_q, filters) => {
      if (filters?.jobId === 1 && filters.status === "waiting_resume") return Promise.resolve([{ id: 1 }, { id: 2 }] as api.Candidate[]);
      if (filters?.jobId === 1 && filters.status === "resume_received") return Promise.resolve([{ id: 3 }] as api.Candidate[]);
      return Promise.resolve(filters?.jobId === 1 ? [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }] as api.Candidate[] : [{ id: 5 }] as api.Candidate[]);
    });
    vi.mocked(api.listReviews).mockResolvedValue([{
      candidate_job_id: 31, candidate: { id: 4, name: "待复核候选人" }, job: { id: 1, name: "后端工程师" },
      score: 79, reason: "接近门槛，需人工确认", threshold: 80, confidence: 0.6, missing_critical_fields: [], estimated_fields: [],
      evidence: [], model: "test-model", task_id: 11, scored_at: null,
    }]);
    vi.mocked(api.listResumes).mockImplementation((filters) =>
      Promise.resolve(filters?.jobId === 1 ? [{ id: 11 }] as api.Resume[] : []),
    );

    const wrapper = mount(DashboardPage);
    await flushPromises();

    const backendCard = wrapper.get('[data-testid="dashboard-job-card-1"]');
    expect(backendCard.get('[data-testid="job-readiness-1"]').text()).toContain("配置完整");
    expect(backendCard.get('[data-testid="job-task-progress-1"]').text()).toContain("3 / 5");
    expect(backendCard.get('[data-testid="job-agent-1"]').text()).toContain("hr-mac");
    expect(backendCard.text()).toContain("岗位状态：招聘中");
    expect(backendCard.text()).toContain("Agent 状态：在线");
    expect(backendCard.get('[data-testid="job-contacted-count-1"]').text()).toBe("1");
    expect(backendCard.get('[data-testid="job-waiting-resume-count-1"]').text()).toBe("2");
    expect(backendCard.get('[data-testid="job-resume-received-count-1"]').text()).toBe("1");
    expect(backendCard.get('[data-testid="job-review-count-1"]').text()).toBe("1");
    expect(backendCard.get('[data-testid="job-failed-count-1"]').text()).toBe("0");
    expect(backendCard.get('[aria-label="暂停后端工程师任务"]')).toBeTruthy();
    expect(backendCard.get('[aria-label="终止后端工程师任务"]')).toBeTruthy();

    const productCard = wrapper.get('[data-testid="dashboard-job-card-2"]');
    expect(productCard.get('[data-testid="job-readiness-2"]').text()).toContain("配置未完成");
    expect(productCard.text()).toContain("缺少 BOSS 岗位入口");
    expect(productCard.get('[data-testid="job-task-progress-2"]').text()).toContain("暂无活动任务");
    expect(productCard.get('[aria-label="启动产品经理任务"]').attributes("disabled")).toBeDefined();
  });

  it("opens a ready job directly from its operations card", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([{
      id: 7, name: "算法工程师", jd_text: "Python", score_threshold: 80, greet_template: "您好",
      boss_entry_url: "https://www.zhipin.com/job/7", hourly_greet_limit: 20,
      min_action_delay_ms: 1500, max_action_delay_ms: 4000, default_requested_count: 12,
      critical_fields: [{ key: "degree", label: "学历" }], critical_fields_confirmed: true,
      readiness: { ready: true, missing: [] }, enabled: true, created_at: null,
    }]);
    vi.mocked(api.listAgentRuns).mockResolvedValue([{
      id: 3,
      machine_id: "mac-a",
      status: "online",
      availability: "idle",
      current_task_id: null,
      boss_login_status: "logged_in",
      last_error: "",
      last_heartbeat: new Date().toISOString(),
    }]);
    const wrapper = mount(DashboardPage);
    await flushPromises();

    await wrapper.get('[aria-label="启动算法工程师任务"]').trigger("click");
    await flushPromises();

    expect(wrapper.get<HTMLSelectElement>('[aria-label="任务岗位"]').element.value).toBe("7");
    expect(wrapper.get<HTMLInputElement>('[aria-label="筛选人数"]').element.value).toBe("12");
    expect(wrapper.text()).toContain("完整 JD 自动评分");
    expect(wrapper.text()).not.toContain("关键资料");
  });

  it("disables only the job that already has an active task", async () => {
    const readyJob = (id: number, name: string): api.Job => ({
      id, name, jd_text: `${name} JD`, score_threshold: 80, greet_template: "您好",
      boss_entry_url: `https://www.zhipin.com/job/${id}`, hourly_greet_limit: 20,
      min_action_delay_ms: 1500, max_action_delay_ms: 4000, default_requested_count: 5,
      critical_fields: [{ key: "degree", label: "学历" }], critical_fields_confirmed: true,
      readiness: { ready: true, missing: [] }, enabled: true, created_at: null,
    });
    vi.mocked(api.listJobs).mockResolvedValue([readyJob(1, "后端工程师"), readyJob(2, "产品经理")]);
    vi.mocked(api.listScreeningTasks).mockResolvedValue([{
      id: 9, job_id: 1, created_by_user_id: 1, machine_id: "mac-a", requested_count: 5,
      critical_fields: [], critical_fields_source: {}, job_name_snapshot: "后端工程师",
      jd_text_snapshot: "JD", score_threshold_snapshot: 80, greet_template_snapshot: "您好",
      status: "running", pause_reason: "", processed_count: 1, eligible_count: 1,
      contacted_count: 0, review_count: 0, skipped_count: 0, failed_count: 0,
      created_at: null, started_at: null, finished_at: null,
    }]);

    const wrapper = mount(DashboardPage);
    await flushPromises();
    await wrapper.get('[aria-label="新建筛选任务"]').trigger("click");

    expect(wrapper.get('[aria-label="任务岗位"] option[value="1"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[aria-label="任务岗位"] option[value="2"]').attributes("disabled")).toBeUndefined();
  });

  it("only offers jobs explicitly ready and agents that are online and idle", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([
      { id: 1, name: "缺少就绪信息", jd_text: "A", score_threshold: 80, greet_template: "您好", boss_entry_url: "", hourly_greet_limit: 20, min_action_delay_ms: 1500, max_action_delay_ms: 4000, enabled: true, created_at: null },
      { id: 2, name: "配置完整岗位", jd_text: "B", score_threshold: 80, greet_template: "您好", boss_entry_url: "https://www.zhipin.com/job/2", hourly_greet_limit: 20, min_action_delay_ms: 1500, max_action_delay_ms: 4000, enabled: true, readiness: { ready: true, missing: [] }, created_at: null },
    ]);
    const fresh = new Date().toISOString();
    vi.mocked(api.listAgentRuns).mockResolvedValue([
      { id: 1, machine_id: "online-idle", status: "online", availability: "idle", current_task_id: null, boss_login_status: "logged_in", last_error: "", last_heartbeat: fresh },
      { id: 2, machine_id: "offline-idle", status: "offline", availability: "idle", current_task_id: null, boss_login_status: "logged_in", last_error: "", last_heartbeat: fresh },
      { id: 3, machine_id: "online-busy", status: "online", availability: "busy", current_task_id: 10, boss_login_status: "logged_in", last_error: "", last_heartbeat: fresh },
    ]);

    const wrapper = mount(DashboardPage);
    await flushPromises();
    await wrapper.get('[aria-label="新建筛选任务"]').trigger("click");

    expect(wrapper.get('[aria-label="任务岗位"] option[value="1"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[aria-label="任务岗位"] option[value="2"]').attributes("disabled")).toBeUndefined();
    expect(wrapper.find('[aria-label="任务 Agent"] option[value="1"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="任务 Agent"] option[value="2"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="任务 Agent"] option[value="3"]').exists()).toBe(false);
  });

  it("locks task controls and keeps the server state while pause is pending", async () => {
    const running = {
      id: 15, job_id: 7, created_by_user_id: 1, machine_id: "mac-a", requested_count: 10,
      critical_fields: [], critical_fields_source: {}, job_name_snapshot: "产品经理", jd_text_snapshot: "JD",
      score_threshold_snapshot: 80, greet_template_snapshot: "您好", status: "running", pause_reason: "",
      processed_count: 4, eligible_count: 3, contacted_count: 2, review_count: 1, skipped_count: 0,
      failed_count: 0, created_at: null, started_at: null, finished_at: null,
    };
    let resolvePause!: (task: api.ScreeningTask) => void;
    vi.mocked(api.listScreeningTasks).mockResolvedValue([running]);
    vi.mocked(api.pauseScreeningTask).mockImplementation(() => new Promise((resolve) => { resolvePause = resolve; }));
    const wrapper = mount(DashboardPage);
    await flushPromises();

    await wrapper.get('[aria-label="暂停任务"]').trigger("click");
    await wrapper.get('[aria-label="暂停任务"]').trigger("click");

    expect(api.pauseScreeningTask).toHaveBeenCalledTimes(1);
    expect(wrapper.get('[aria-label="暂停任务"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[aria-label="停止任务"]').attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("执行中");

    resolvePause({ ...running, status: "paused", pause_reason: "人工检查" });
    await flushPromises();
    expect(wrapper.find('[aria-label="暂停任务"]').exists()).toBe(false);
    expect(wrapper.get('[aria-label="继续任务"]').attributes("disabled")).toBeUndefined();
  });

  it("keeps a newly created task when an older poll finishes later", async () => {
    vi.useFakeTimers();
    const fresh = new Date().toISOString();
    const job: api.Job = {
      id: 7, name: "后端工程师", jd_text: "Python", score_threshold: 80, greet_template: "您好",
      boss_entry_url: "https://www.zhipin.com/job/7", hourly_greet_limit: 20,
      min_action_delay_ms: 1500, max_action_delay_ms: 4000, default_requested_count: 5,
      critical_fields: [{ key: "degree", label: "学历" }], critical_fields_confirmed: true,
      readiness: { ready: true, missing: [] }, enabled: true, created_at: null,
    };
    const created: api.ScreeningTask = {
      id: 40, job_id: 7, created_by_user_id: 1, machine_id: "mac-a", assigned_agent_run_id: 3,
      requested_count: 5, critical_fields: job.critical_fields!, critical_fields_source: { confirmed: true },
      job_name_snapshot: job.name, jd_text_snapshot: job.jd_text, score_threshold_snapshot: 80,
      greet_template_snapshot: "您好", status: "ready", pause_reason: "", processed_count: 0,
      eligible_count: 0, contacted_count: 0, review_count: 0, skipped_count: 0, failed_count: 0,
      created_at: null, started_at: null, finished_at: null,
    };
    let resolveOldPoll!: (tasks: api.ScreeningTask[]) => void;
    vi.mocked(api.listJobs).mockResolvedValue([job]);
    vi.mocked(api.listAgentRuns).mockResolvedValue([{ id: 3, machine_id: "mac-a", status: "online", availability: "idle", current_task_id: null, boss_login_status: "logged_in", last_error: "", last_heartbeat: fresh }]);
    vi.mocked(api.listScreeningTasks)
      .mockResolvedValueOnce([])
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOldPoll = resolve; }));
    vi.mocked(api.createScreeningTask).mockResolvedValue(created);
    const wrapper = mount(DashboardPage);
    await flushPromises();
    await wrapper.get('[aria-label="新建筛选任务"]').trigger("click");
    await wrapper.get('[aria-label="任务岗位"]').setValue("7");
    await wrapper.get('[aria-label="任务 Agent"]').setValue("3");

    await vi.advanceTimersByTimeAsync(5000);
    await wrapper.get('[aria-label="筛选任务表单"]').trigger("submit");
    await flushPromises();
    resolveOldPoll([]);
    await flushPromises();

    expect(wrapper.text()).toContain("任务 #40 · 后端工程师");
    wrapper.unmount();
    vi.useRealTimers();
  });

  it("ignores a manual refresh response that started before pause completed", async () => {
    const running: api.ScreeningTask = {
      id: 41, job_id: 1, created_by_user_id: 1, machine_id: "mac-a", requested_count: 5,
      critical_fields: [], critical_fields_source: {}, job_name_snapshot: "后端工程师", jd_text_snapshot: "JD",
      score_threshold_snapshot: 80, greet_template_snapshot: "您好", status: "running", pause_reason: "",
      processed_count: 2, eligible_count: 1, contacted_count: 0, review_count: 0, skipped_count: 0,
      failed_count: 0, created_at: null, started_at: null, finished_at: null,
    };
    let resolveOldRefresh!: (task: api.ScreeningTask) => void;
    vi.mocked(api.listScreeningTasks).mockResolvedValue([running]);
    vi.mocked(api.getScreeningTask).mockImplementation(() => new Promise((resolve) => { resolveOldRefresh = resolve; }));
    vi.mocked(api.pauseScreeningTask).mockResolvedValue({ ...running, status: "paused", pause_reason: "人工检查" });
    const wrapper = mount(DashboardPage);
    await flushPromises();

    await wrapper.get('[aria-label="刷新当前任务"]').trigger("click");
    await wrapper.get('[aria-label="暂停任务"]').trigger("click");
    await flushPromises();
    resolveOldRefresh(running);
    await flushPromises();

    expect(wrapper.text()).toContain("已暂停");
    expect(wrapper.find('[aria-label="暂停任务"]').exists()).toBe(false);
    expect(wrapper.get('[aria-label="继续任务"]')).toBeTruthy();
  });

  it("keeps the last successful task snapshot when polling fails", async () => {
    vi.useFakeTimers();
    const running = {
      id: 31, job_id: 1, created_by_user_id: 1, machine_id: "mac-a", requested_count: 5,
      critical_fields: [], critical_fields_source: {}, job_name_snapshot: "后端工程师", jd_text_snapshot: "JD",
      score_threshold_snapshot: 80, greet_template_snapshot: "您好", status: "running", pause_reason: "",
      processed_count: 2, eligible_count: 1, contacted_count: 0, review_count: 0, skipped_count: 0,
      failed_count: 0, created_at: null, started_at: null, finished_at: null,
    };
    vi.mocked(api.listScreeningTasks)
      .mockResolvedValueOnce([running])
      .mockRejectedValueOnce(new Error("tasks unavailable"));
    const wrapper = mount(DashboardPage);
    await flushPromises();

    await vi.advanceTimersByTimeAsync(5000);
    await flushPromises();

    expect(wrapper.text()).toContain("任务 #31 · 后端工程师");
    expect(wrapper.text()).toContain("已处理 2 / 5 人");
    expect(wrapper.get('[role="alert"]').text()).toContain("任务列表加载失败");
    wrapper.unmount();
    vi.useRealTimers();
  });

  it("ignores a polling response that started before pause completed", async () => {
    vi.useFakeTimers();
    const running = {
      id: 32, job_id: 1, created_by_user_id: 1, machine_id: "mac-a", requested_count: 5,
      critical_fields: [], critical_fields_source: {}, job_name_snapshot: "后端工程师", jd_text_snapshot: "JD",
      score_threshold_snapshot: 80, greet_template_snapshot: "您好", status: "running", pause_reason: "",
      processed_count: 2, eligible_count: 1, contacted_count: 0, review_count: 0, skipped_count: 0,
      failed_count: 0, created_at: null, started_at: null, finished_at: null,
    };
    let resolveOldPoll!: (tasks: api.ScreeningTask[]) => void;
    vi.mocked(api.listScreeningTasks)
      .mockResolvedValueOnce([running])
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOldPoll = resolve; }));
    vi.mocked(api.pauseScreeningTask).mockResolvedValue({ ...running, status: "paused", pause_reason: "人工检查" });
    const wrapper = mount(DashboardPage);
    await flushPromises();

    await vi.advanceTimersByTimeAsync(5000);
    await wrapper.get('[aria-label="暂停任务"]').trigger("click");
    await flushPromises();
    resolveOldPoll([running]);
    await flushPromises();

    expect(wrapper.text()).toContain("已暂停");
    expect(wrapper.find('[aria-label="暂停任务"]').exists()).toBe(false);
    expect(wrapper.get('[aria-label="继续任务"]')).toBeTruthy();
    wrapper.unmount();
    vi.useRealTimers();
  });

  it("clears an Agent selection that is no longer ready before submit", async () => {
    vi.useFakeTimers();
    const fresh = new Date().toISOString();
    vi.mocked(api.listJobs).mockResolvedValue([{
      id: 1, name: "后端工程师", jd_text: "Python", score_threshold: 80, greet_template: "您好",
      boss_entry_url: "https://www.zhipin.com/job/1", hourly_greet_limit: 20,
      min_action_delay_ms: 1500, max_action_delay_ms: 4000, default_requested_count: 5,
      critical_fields: [{ key: "degree", label: "学历" }], critical_fields_confirmed: true,
      readiness: { ready: true, missing: [] }, enabled: true, created_at: null,
    }]);
    vi.mocked(api.listAgentRuns)
      .mockResolvedValueOnce([{ id: 3, machine_id: "mac-a", status: "online", availability: "idle", current_task_id: null, boss_login_status: "logged_in", last_error: "", last_heartbeat: fresh }])
      .mockResolvedValueOnce([{ id: 3, machine_id: "mac-a", status: "online", availability: "busy", current_task_id: 99, boss_login_status: "logged_in", last_error: "", last_heartbeat: fresh }]);
    const wrapper = mount(DashboardPage);
    await flushPromises();
    await wrapper.get('[aria-label="新建筛选任务"]').trigger("click");
    await wrapper.get('[aria-label="任务岗位"]').setValue("1");
    await wrapper.get('[aria-label="任务 Agent"]').setValue("3");

    await vi.advanceTimersByTimeAsync(5000);
    await flushPromises();

    expect(wrapper.get<HTMLSelectElement>('[aria-label="任务 Agent"]').element.value).toBe("");
    expect(wrapper.get('[aria-label="提交筛选任务"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[aria-label="筛选任务表单"]').trigger("submit");
    expect(api.createScreeningTask).not.toHaveBeenCalled();
    wrapper.unmount();
    vi.useRealTimers();
  });

  it("emits the selected job from its detail and configuration actions", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([
      { id: 1, name: "完整岗位", jd_text: "A", score_threshold: 80, greet_template: "您好", boss_entry_url: "https://www.zhipin.com/job/1", hourly_greet_limit: 20, min_action_delay_ms: 1500, max_action_delay_ms: 4000, default_requested_count: 5, critical_fields: [{ key: "degree", label: "学历" }], critical_fields_confirmed: true, readiness: { ready: true, missing: [] }, enabled: true, created_at: null },
      { id: 2, name: "待完善岗位", jd_text: "B", score_threshold: 80, greet_template: "您好", boss_entry_url: "", hourly_greet_limit: 20, min_action_delay_ms: 1500, max_action_delay_ms: 4000, default_requested_count: 5, critical_fields: [], critical_fields_confirmed: false, readiness: { ready: false, missing: ["boss_entry_url", "critical_fields"] }, enabled: true, created_at: null },
    ]);
    const wrapper = mount(DashboardPage);
    await flushPromises();

    await wrapper.get('[aria-label="查看完整岗位详情"]').trigger("click");
    await wrapper.get('[aria-label="完善待完善岗位配置"]').trigger("click");

    expect(wrapper.emitted("open-job")).toEqual([[1, false], [2, true]]);
  });

  it("keeps Agent details but disables submission when Agent polling fails", async () => {
    vi.useFakeTimers();
    const fresh = new Date().toISOString();
    vi.mocked(api.listJobs).mockResolvedValue([{
      id: 1, name: "后端工程师", jd_text: "Python", score_threshold: 80, greet_template: "您好",
      boss_entry_url: "https://www.zhipin.com/job/1", hourly_greet_limit: 20,
      min_action_delay_ms: 1500, max_action_delay_ms: 4000, default_requested_count: 5,
      critical_fields: [{ key: "degree", label: "学历" }], critical_fields_confirmed: true,
      readiness: { ready: true, missing: [] }, enabled: true, created_at: null,
    }]);
    vi.mocked(api.listAgentRuns)
      .mockResolvedValueOnce([{ id: 3, machine_id: "mac-a", status: "online", availability: "idle", current_task_id: null, boss_login_status: "logged_in", last_error: "", last_heartbeat: fresh }])
      .mockRejectedValueOnce(new Error("agent unavailable"));
    const wrapper = mount(DashboardPage);
    await flushPromises();
    await wrapper.get('[aria-label="新建筛选任务"]').trigger("click");
    await wrapper.get('[aria-label="任务岗位"]').setValue("1");
    await wrapper.get('[aria-label="任务 Agent"]').setValue("3");

    await vi.advanceTimersByTimeAsync(5000);
    await flushPromises();

    expect(wrapper.text()).toContain("mac-a");
    expect(wrapper.get('[role="alert"]').text()).toContain("加载 Agent 状态失败");
    expect(wrapper.get<HTMLSelectElement>('[aria-label="任务 Agent"]').element.value).toBe("");
    expect(wrapper.get('[aria-label="提交筛选任务"]').attributes("disabled")).toBeDefined();
    wrapper.unmount();
    vi.useRealTimers();
  });

  it("shows and retries a job-list error independently from successful tasks", async () => {
    vi.mocked(api.listJobs)
      .mockRejectedValueOnce(new Error("jobs unavailable"))
      .mockResolvedValueOnce([{
        id: 1, name: "恢复岗位", jd_text: "JD", score_threshold: 80, greet_template: "您好",
        boss_entry_url: "https://www.zhipin.com/job/1", hourly_greet_limit: 20,
        min_action_delay_ms: 1500, max_action_delay_ms: 4000, default_requested_count: 5,
        critical_fields: [{ key: "degree", label: "学历" }], critical_fields_confirmed: true,
        readiness: { ready: true, missing: [] }, enabled: true, created_at: null,
      }]);
    vi.mocked(api.listScreeningTasks).mockResolvedValue([]);
    const wrapper = mount(DashboardPage);
    await flushPromises();

    expect(wrapper.get('[data-testid="jobs-load-error"]').text()).toContain("岗位列表加载失败");
    await wrapper.get('[aria-label="重试岗位列表"]').trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("恢复岗位");
    expect(wrapper.find('[data-testid="jobs-load-error"]').exists()).toBe(false);
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
