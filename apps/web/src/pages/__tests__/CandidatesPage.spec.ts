import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import type { Candidate, UserMe } from "../../api";
import CandidatesPage from "../CandidatesPage.vue";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    listCandidates: vi.fn(),
    listJobs: vi.fn(),
    listCandidateJobs: vi.fn(),
    listCandidateResumes: vi.fn(),
    downloadResumeFile: vi.fn(),
    listReviews: vi.fn(),
    reviewCandidateJob: vi.fn(),
    reEvaluateCandidateJob: vi.fn(),
    markExchange: vi.fn(),
    previewCandidateMerge: vi.fn(),
    mergeCandidates: vi.fn(),
    revertCandidateMerge: vi.fn(),
  };
});

const user: UserMe = {
  id: 2,
  username: "member.hr",
  role: "member",
  is_active: true,
  must_change_password: false,
};

const candidate: Candidate = {
  id: 7,
  name: "林晓",
  boss_id: "boss-7788",
  fingerprint: "resume-fingerprint",
  phone: "13800138000",
  email: "lin@example.com",
  phone_normalized: "13800138000",
  email_normalized: "lin@example.com",
  merged_into_candidate_id: null,
  age: 29,
  years_of_experience: 6,
  job_segments_json: "[]",
  source: "boss",
  created_at: "2026-09-20T08:00:00Z",
};

function mountPage(currentUser: UserMe = user) {
  return mount(CandidatesPage, {
    props: { user: currentUser },
    global: { stubs: { teleport: true } },
  });
}

describe("CandidatesPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.listJobs).mockResolvedValue([]);
    vi.mocked(api.listCandidateJobs).mockResolvedValue([]);
    vi.mocked(api.listCandidateResumes).mockResolvedValue([]);
  });

  it("restores human potential structure without inventing evaluation data", async () => {
    vi.mocked(api.listCandidates).mockResolvedValue([candidate]);
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain("HUMAN POTENTIAL.");
    expect(wrapper.get('[data-testid="candidate-total"]').text()).toContain("1");
    for (const id of ["candidate-high-score", "candidate-contacted", "candidate-resume"]) {
      expect(wrapper.get(`[data-testid="${id}"]`).text()).toContain("—");
    }
    for (const label of ["筛选候选人岗位", "筛选处理状态", "筛选 AI 分数"]) {
      expect(wrapper.get(`[aria-label="${label}"]`).attributes("disabled")).toBeUndefined();
    }
    expect(wrapper.text()).toContain("暂未接入");
    expect(wrapper.text()).not.toMatch(/王女士|李先生|86 分|91 分/);

    await wrapper.get('[aria-label="查看林晓详情"]').trigger("click");
    const dialog = wrapper.get('[role="dialog"]');
    for (const section of ["EXPERIENCE", "MATCH EVIDENCE", "RISK NOTE", "ACTIVITY"]) {
      expect(dialog.text()).toContain(section);
    }
    expect(dialog.get('[aria-label="查看林晓简历"]').attributes("disabled")).toBeDefined();
  });

  it("sends job, status, score and review filters to the server", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([{
      id: 3,
      name: "前端工程师",
      jd_text: "前端岗位",
      score_threshold: 80,
      greet_template: "您好",
      boss_entry_url: "",
      hourly_greet_limit: 20,
      min_action_delay_ms: 1500,
      max_action_delay_ms: 4000,
      enabled: true,
      created_at: null,
    }]);
    vi.mocked(api.listCandidates).mockResolvedValue([candidate]);
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="筛选候选人岗位"]').setValue("3");
    await wrapper.get('[aria-label="筛选处理状态"]').setValue("needs_review");
    await wrapper.get('[aria-label="筛选 AI 分数"]').setValue("85");
    await wrapper.get('[aria-label="筛选待复核候选人"]').setValue(true);
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(api.listCandidates).toHaveBeenLastCalledWith("", {
      jobId: 3,
      status: "needs_review",
      minScore: 85,
      needsReview: true,
    });
  });

  it("loads real job links and resume versions when candidate detail opens", async () => {
    vi.mocked(api.listCandidates).mockResolvedValue([candidate]);
    vi.mocked(api.listCandidateJobs).mockResolvedValue([{
      id: 31,
      candidate_id: 7,
      job_id: 3,
      status: "needs_review",
      active_resume_id: 12,
      latest_score_event_id: 55,
      review_reason_json: "{}",
      created_at: null,
      updated_at: null,
    }]);
    vi.mocked(api.listCandidateResumes).mockResolvedValue([{
      id: 12,
      candidate_id: 7,
      version_number: 2,
      original_filename: "lin-v2.pdf",
      file_path: "/data/lin-v2.pdf",
      file_hash: "hash-v2",
      parsed_text: "",
      source: "upload",
      parse_status: "parsed",
      uploaded_by_user_id: 2,
      supersedes_resume_id: 11,
      created_at: "2026-09-21T09:00:00Z",
    }]);
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="查看林晓详情"]').trigger("click");
    await flushPromises();

    expect(api.listCandidateJobs).toHaveBeenCalledWith(7);
    expect(api.listCandidateResumes).toHaveBeenCalledWith(7);
    const dialog = wrapper.get('[role="dialog"]');
    expect(dialog.text()).toContain("needs_review");
    expect(dialog.text()).toContain("lin-v2.pdf");
    expect(dialog.text()).toContain("版本 2");
    expect(dialog.text()).toContain("评分证据与活动时间线读取接口暂未提供");
  });

  it("only lets lead or admin preview candidate merges and blocks conflicts", async () => {
    const target = { ...candidate, id: 8, name: "林晓（重复）", boss_id: "boss-8899" };
    vi.mocked(api.listCandidates).mockResolvedValue([candidate, target]);

    const memberWrapper = mountPage();
    await flushPromises();
    await memberWrapper.get('[aria-label="查看林晓详情"]').trigger("click");
    expect(memberWrapper.find('[aria-label="合并林晓候选人"]').exists()).toBe(false);

    vi.mocked(api.previewCandidateMerge).mockResolvedValue({
      source_candidate_id: 7,
      target_candidate_id: 8,
      merged_fields: { name: "林晓（重复）", age: 29 },
      moved_counts: { resumes: 2, candidate_jobs: 1 },
      conflicts: [{ entity_type: "resume", entity_id: 12, reason: "duplicate_file_hash_on_merged_candidate" }],
    });
    const leadWrapper = mountPage({ ...user, role: "lead", username: "lead.hr" });
    await flushPromises();
    await leadWrapper.get('[aria-label="查看林晓详情"]').trigger("click");
    await leadWrapper.get('[aria-label="合并林晓候选人"]').trigger("click");
    await leadWrapper.get('[aria-label="合并目标候选人"]').setValue("8");
    await leadWrapper.get('[aria-label="姓名保留来源"]').setValue("source");
    await leadWrapper.get('[aria-label="预览候选人合并"]').trigger("click");
    await flushPromises();

    expect(api.previewCandidateMerge).toHaveBeenCalledWith(expect.objectContaining({
      source_candidate_id: 7,
      target_candidate_id: 8,
      field_choices: expect.objectContaining({ name: "source" }),
    }));
    expect(leadWrapper.text()).toContain("duplicate_file_hash_on_merged_candidate");
    expect(leadWrapper.get('[aria-label="确认执行候选人合并"]').attributes("disabled")).toBeDefined();
    expect(api.mergeCandidates).not.toHaveBeenCalled();
  });

  it("discards a stale merge preview when the target changes before the response returns", async () => {
    const targetB = { ...candidate, id: 8, name: "目标 B", boss_id: "boss-b" };
    const targetC = { ...candidate, id: 9, name: "目标 C", boss_id: "boss-c" };
    vi.mocked(api.listCandidates).mockResolvedValue([candidate, targetB, targetC]);
    let resolvePreview!: (value: api.CandidateMergePreview) => void;
    vi.mocked(api.previewCandidateMerge).mockImplementation(() => new Promise((resolve) => { resolvePreview = resolve; }));
    const wrapper = mountPage({ ...user, role: "lead", username: "lead.hr" });
    await flushPromises();

    await wrapper.get('[aria-label="查看林晓详情"]').trigger("click");
    await wrapper.get('[aria-label="合并林晓候选人"]').trigger("click");
    await wrapper.get('[aria-label="合并目标候选人"]').setValue("8");
    await wrapper.get('[aria-label="预览候选人合并"]').trigger("click");
    await wrapper.get('[aria-label="合并目标候选人"]').setValue("9");
    resolvePreview({ source_candidate_id: 7, target_candidate_id: 8, merged_fields: {}, moved_counts: {}, conflicts: [] });
    await flushPromises();

    expect(wrapper.find('[aria-label="确认执行候选人合并"]').exists()).toBe(false);
    expect(api.mergeCandidates).not.toHaveBeenCalled();
  });

  it("clears stale candidates when a completed merge cannot refresh the list", async () => {
    const target = { ...candidate, id: 8, name: "林晓（主记录）", boss_id: "boss-8899" };
    vi.mocked(api.listCandidates).mockResolvedValueOnce([candidate, target]).mockRejectedValueOnce(new Error("refresh failed"));
    vi.mocked(api.previewCandidateMerge).mockResolvedValue({
      source_candidate_id: 7, target_candidate_id: 8, merged_fields: {}, moved_counts: {}, conflicts: [],
    });
    vi.mocked(api.mergeCandidates).mockResolvedValue({
      id: 42, source_candidate_id: 7, target_candidate_id: 8, field_choices: {}, status: "active",
      performed_by_user_id: 2, performed_at: "2026-09-23T08:00:00Z",
    });
    const wrapper = mountPage({ ...user, role: "lead", username: "lead.hr" });
    await flushPromises();
    await wrapper.get('[aria-label="查看林晓详情"]').trigger("click");
    await wrapper.get('[aria-label="合并林晓候选人"]').trigger("click");
    await wrapper.get('[aria-label="合并目标候选人"]').setValue("8");
    await wrapper.get('[aria-label="预览候选人合并"]').trigger("click");
    await flushPromises();
    await wrapper.get('[aria-label="确认执行候选人合并"]').trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("合并 #42 已完成，但列表刷新失败");
    expect(wrapper.text()).not.toContain("林晓（主记录）");
  });

  it("merges without conflicts and only offers reverting the merge completed in this session", async () => {
    const target = { ...candidate, id: 8, name: "林晓（主记录）", boss_id: "boss-8899" };
    vi.mocked(api.listCandidates)
      .mockResolvedValueOnce([candidate, target])
      .mockResolvedValueOnce([target])
      .mockResolvedValueOnce([candidate, target]);
    vi.mocked(api.previewCandidateMerge).mockResolvedValue({
      source_candidate_id: 7,
      target_candidate_id: 8,
      merged_fields: { name: "林晓（主记录）" },
      moved_counts: { resumes: 2 },
      conflicts: [],
    });
    vi.mocked(api.mergeCandidates).mockResolvedValue({
      id: 41,
      source_candidate_id: 7,
      target_candidate_id: 8,
      field_choices: { name: "target" },
      status: "active",
      performed_by_user_id: 2,
      performed_at: "2026-09-23T08:00:00Z",
    });
    vi.mocked(api.revertCandidateMerge).mockResolvedValue({ id: 41, status: "reverted", reverted: true, idempotent: false, conflicts: [] });
    const wrapper = mountPage({ ...user, role: "lead", username: "lead.hr" });
    await flushPromises();

    await wrapper.get('[aria-label="查看林晓详情"]').trigger("click");
    await wrapper.get('[aria-label="合并林晓候选人"]').trigger("click");
    await wrapper.get('[aria-label="合并目标候选人"]').setValue("8");
    await wrapper.get('[aria-label="预览候选人合并"]').trigger("click");
    await flushPromises();
    await wrapper.get('[aria-label="确认执行候选人合并"]').trigger("click");
    await flushPromises();

    expect(api.mergeCandidates).toHaveBeenCalled();
    expect(wrapper.text()).toContain("合并 #41 已完成");
    expect(wrapper.text()).toContain("只能撤销本次会话刚完成的合并");
    await wrapper.get('[aria-label="撤销刚完成的候选人合并"]').trigger("click");
    await flushPromises();

    expect(api.revertCandidateMerge).toHaveBeenCalledWith(41);
    expect(wrapper.text()).toContain("合并 #41 已撤销");
  });

  it("reviews pending candidates in place and archives through the real review action", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([{
      id: 3, name: "前端工程师", jd_text: "前端岗位", score_threshold: 85, greet_template: "您好",
      boss_entry_url: "", hourly_greet_limit: 20, min_action_delay_ms: 1500, max_action_delay_ms: 4000,
      default_requested_count: 20, critical_fields: [{ key: "portfolio", label: "作品集" }],
      critical_fields_confirmed: true, readiness: { ready: false, missing: ["boss_entry_url"] }, enabled: true, created_at: null,
    }]);
    vi.mocked(api.listCandidates).mockResolvedValue([candidate]);
    vi.mocked(api.listReviews).mockResolvedValue([{
      candidate_job_id: 31,
      candidate: { id: 7, name: "林晓" },
      job: { id: 3, name: "前端工程师" },
      score: 82,
      reason: "能力匹配，但关键资料不完整",
      threshold: 85,
      confidence: 0.76,
      missing_critical_fields: ["作品集"],
      estimated_fields: ["工作年限"],
      evidence: ["负责 Vue 项目交付"],
      model: "configured-model",
      task_id: 12,
      scored_at: "2026-09-21T09:00:00Z",
    }]);
    vi.mocked(api.listCandidateJobs).mockResolvedValue([{
      id: 31, candidate_id: 7, job_id: 3, status: "needs_review", active_resume_id: 12,
      latest_score_event_id: 55, review_reason_json: "{}", created_at: null, updated_at: null,
    }]);
    vi.mocked(api.listCandidateResumes).mockResolvedValue([{
      id: 12, candidate_id: 7, version_number: 2, original_filename: "lin-v2.pdf",
      file_path: "/data/lin-v2.pdf", file_hash: "hash-v2", parsed_text: "", source: "upload",
      parse_status: "parsed", uploaded_by_user_id: 2, supersedes_resume_id: 11, created_at: null,
    }]);
    vi.mocked(api.reEvaluateCandidateJob).mockResolvedValue({
      id: 56, candidate_id: 7, job_id: 3, candidate_job_id: 31, resume_id: 12, task_id: null,
      hard_filter_passed: true, hard_filter_reasons: [], score: 88, reason: "补充复核",
      evidence: ["仍需作品集"], missing_fields: ["portfolio"], estimated_fields: [], critical_fields: [],
      confidence: 0.9, decision: "needs_review", model: "configured-model", created_at: null,
    });
    vi.mocked(api.reviewCandidateJob).mockResolvedValue({ candidate_job_id: 31, status: "archived" });
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="筛选待复核候选人"]').setValue(true);
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(api.listReviews).toHaveBeenCalled();
    await wrapper.get('[aria-label="查看林晓详情"]').trigger("click");
    await flushPromises();

    const dialog = wrapper.get('[role="dialog"]');
    expect(dialog.text()).toContain("能力匹配，但关键资料不完整");
    expect(dialog.text()).toContain("作品集");
    expect(dialog.text()).toContain("工作年限");
    expect(dialog.text()).toContain("负责 Vue 项目交付");
    expect(dialog.text()).toContain("lin-v2.pdf");
    vi.mocked(api.downloadResumeFile).mockResolvedValue(new Blob(["pdf"], { type: "application/pdf" }));
    await dialog.get('[aria-label="查看简历lin-v2.pdf"]').trigger("click");
    await flushPromises();
    expect(api.downloadResumeFile).toHaveBeenCalledWith(12);
    await dialog.get('[aria-label="重新评估林晓"]').trigger("click");
    await flushPromises();
    expect(api.reEvaluateCandidateJob).toHaveBeenCalledWith(7, 3, 12);
    expect(wrapper.text()).toContain("评分：88 / 门槛 85");
    await wrapper.get('[aria-label="继续待定林晓"]').trigger("click");
    expect(api.reviewCandidateJob).toHaveBeenCalledWith(31, "keep_pending");
    await flushPromises();
    await wrapper.get('[aria-label="归档林晓"]').trigger("click");
    await flushPromises();
    expect(api.reviewCandidateJob).toHaveBeenCalledWith(31, "archive");
    expect(wrapper.text()).toContain("已归档林晓在前端工程师的待复核记录");
  });

  it("removes a review card when re-evaluation leaves pending review", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([{
      id: 3, name: "前端工程师", jd_text: "前端岗位", score_threshold: 85, greet_template: "您好",
      boss_entry_url: "", hourly_greet_limit: 20, min_action_delay_ms: 1500, max_action_delay_ms: 4000,
      default_requested_count: 20, critical_fields: [{ key: "portfolio", label: "作品集" }],
      critical_fields_confirmed: true, enabled: true, created_at: null,
    }]);
    vi.mocked(api.listCandidates).mockResolvedValue([candidate]);
    vi.mocked(api.listReviews).mockResolvedValue([{
      candidate_job_id: 31, candidate: { id: 7, name: "林晓" }, job: { id: 3, name: "前端工程师" },
      score: 82, reason: "缺少作品集", threshold: 85, confidence: 0.76,
      missing_critical_fields: ["作品集"], estimated_fields: [], evidence: [], model: "configured-model",
      task_id: null, scored_at: null,
    }]);
    vi.mocked(api.listCandidateJobs).mockResolvedValue([{
      id: 31, candidate_id: 7, job_id: 3, status: "needs_review", active_resume_id: 12,
      latest_score_event_id: 55, review_reason_json: "{}", created_at: null, updated_at: null,
    }]);
    vi.mocked(api.reEvaluateCandidateJob).mockResolvedValue({
      id: 56, candidate_id: 7, job_id: 3, candidate_job_id: 31, resume_id: 12, task_id: null,
      hard_filter_passed: true, hard_filter_reasons: [], score: 92, reason: "资料完整", evidence: [],
      missing_fields: [], estimated_fields: [], critical_fields: [], confidence: 0.95,
      decision: "eligible", model: "configured-model", created_at: null,
    });
    const wrapper = mountPage();
    await flushPromises();
    await wrapper.get('[aria-label="筛选待复核候选人"]').setValue(true);
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    await wrapper.get('[aria-label="查看林晓详情"]').trigger("click");
    await flushPromises();
    await wrapper.get('[aria-label="重新评估林晓"]').trigger("click");
    await flushPromises();

    expect(wrapper.find('[aria-label="继续待定林晓"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("林晓已退出待复核队列");
  });

  it("loads candidates and searches by name or BOSS ID", async () => {
    vi.mocked(api.listCandidates)
      .mockResolvedValueOnce([candidate])
      .mockResolvedValueOnce([candidate]);
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain("林晓");
    expect(wrapper.text()).toContain("boss-7788");

    await wrapper.get('[aria-label="搜索候选人"]').setValue(" boss-7788 ");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(api.listCandidates).toHaveBeenNthCalledWith(1, "");
    expect(api.listCandidates).toHaveBeenNthCalledWith(2, "boss-7788");
  });

  it("distinguishes no results from a failed request and retries", async () => {
    vi.mocked(api.listCandidates)
      .mockRejectedValueOnce(new Error("503 candidates unavailable"))
      .mockResolvedValueOnce([]);
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("加载候选人失败");
    expect(wrapper.text()).not.toContain("暂无候选人");

    await wrapper.get('[aria-label="重试加载候选人"]').trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("暂无候选人");
  });

  it("opens basic real details and marks unavailable details honestly", async () => {
    vi.mocked(api.listCandidates).mockResolvedValue([candidate]);
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="查看林晓详情"]').trigger("click");
    const dialog = wrapper.get('[role="dialog"]');
    expect(dialog.text()).toContain("29 岁");
    expect(dialog.text()).toContain("6 年经验");
    expect(dialog.text()).toContain("boss");
    expect(dialog.text()).toContain("AI 分数、匹配证据、风险和时间线详情接口暂未提供");
    expect(dialog.text()).not.toContain("resume-fingerprint");
  });

  it("marks an exchange with the signed-in username without inventing a stage", async () => {
    vi.mocked(api.listCandidates).mockResolvedValue([candidate]);
    vi.mocked(api.markExchange).mockResolvedValue({ id: 12 });
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="标记林晓已交换简历"]').trigger("click");
    await flushPromises();

    expect(api.markExchange).toHaveBeenCalledWith(7, "member.hr");
    expect(wrapper.text()).toContain("已记录林晓的简历交换");
    expect(wrapper.text()).not.toContain("进入面试");
  });

  it("keeps the candidate unchanged when marking an exchange fails", async () => {
    vi.mocked(api.listCandidates).mockResolvedValue([candidate]);
    vi.mocked(api.markExchange).mockRejectedValue(new Error("409 exchange blocked"));
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get('[aria-label="标记林晓已交换简历"]').trigger("click");
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("记录交换失败");
    expect(wrapper.text()).toContain("林晓");
    expect(wrapper.text()).not.toContain("已记录林晓的简历交换");
  });
});
