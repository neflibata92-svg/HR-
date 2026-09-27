import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import type { Job, Resume } from "../../api";
import ResumesPage from "../ResumesPage.vue";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    listJobs: vi.fn(),
    createJob: vi.fn(),
    listCandidates: vi.fn(),
    listCandidateJobs: vi.fn(),
    listResumes: vi.fn(),
    batchImportResumes: vi.fn(),
    setActiveResume: vi.fn(),
    reEvaluateCandidateJob: vi.fn(),
    uploadResume: vi.fn(),
  };
});

const job: Job = {
  id: 1, name: "高级前端工程师", jd_text: "前端岗位", score_threshold: 80,
  greet_template: "您好", boss_entry_url: "", hourly_greet_limit: 20,
  min_action_delay_ms: 1500, max_action_delay_ms: 4000, enabled: true,
  created_at: "2026-09-20T08:00:00Z",
};

const existingCandidate: api.Candidate = {
  id: 7,
  name: "林晓",
  boss_id: "boss-7",
  fingerprint: "fingerprint-7",
  phone: null,
  email: null,
  phone_normalized: null,
  email_normalized: null,
  merged_into_candidate_id: null,
  age: 29,
  years_of_experience: 6,
  job_segments_json: "[]",
  source: "boss",
  created_at: null,
};

const resume: Resume = {
  id: 9,
  candidate_id: 7,
  version_number: 2,
  original_filename: "candidate.pdf",
  file_path: "/data/resume.pdf",
  file_hash: "hash-9",
  parsed_text: "",
  source: "upload",
  parse_status: "parsed",
  uploaded_by_user_id: 1,
  supersedes_resume_id: 8,
  created_at: "2026-09-21T09:00:00Z",
};

function selectFile(wrapper: ReturnType<typeof mount>, file: File) {
  const input = wrapper.get<HTMLInputElement>('[aria-label="选择简历文件"]');
  Object.defineProperty(input.element, "files", {
    configurable: true,
    value: [file],
  });
  return input.trigger("change");
}

describe("ResumesPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.listCandidates).mockResolvedValue([{
      id: 7,
      name: "林晓",
      boss_id: "boss-7",
      fingerprint: "fingerprint-7",
      phone: null,
      email: null,
      phone_normalized: null,
      email_normalized: null,
      merged_into_candidate_id: null,
      age: 29,
      years_of_experience: 6,
      job_segments_json: "[]",
      source: "boss",
      created_at: null,
    }]);
    vi.mocked(api.listResumes).mockResolvedValue([]);
    vi.mocked(api.listCandidateJobs).mockResolvedValue([]);
  });

  it("keeps the original resume library structure after selecting a real job", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job]);
    vi.mocked(api.listResumes).mockResolvedValue([resume]);
    const wrapper = mount(ResumesPage);
    await flushPromises();

    expect(wrapper.text()).toContain("RESUME LIBRARY.");
    expect(wrapper.text()).toContain("STEP 01 / 选择一个岗位");
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();
    expect(api.listResumes).toHaveBeenCalledWith({ jobId: 1 });
    expect(wrapper.text()).toContain("candidate.pdf");
    expect(wrapper.text()).toContain("版本 2");
    expect(wrapper.text()).not.toContain("简历列表及岗位关联暂未接入");
    expect(wrapper.text()).not.toContain("示例简历");
  });

  it("requires a real job selection before showing the upload area", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job]);
    const wrapper = mount(ResumesPage);
    await flushPromises();

    expect(wrapper.text()).toContain("请先选择岗位");
    expect(wrapper.find('[aria-label="选择简历文件"]').exists()).toBe(false);
    expect(wrapper.get('[aria-label="选择岗位高级前端工程师"]').text()).toContain("高级前端工程师");

    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[aria-label="选择简历文件"]')).toBeTruthy();
    expect(api.listResumes).toHaveBeenCalledWith({ jobId: 1 });
  });

  it("shows disabled jobs so the library stays in sync with job management", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([{ ...job, enabled: false }]);
    const wrapper = mount(ResumesPage);
    await flushPromises();

    expect(wrapper.get('[aria-label="选择岗位高级前端工程师"]').text()).toContain("高级前端工程师");
    expect(wrapper.get('[aria-label="选择岗位高级前端工程师"]').text()).toContain("已停用");
    expect(wrapper.text()).not.toContain("暂无可用岗位");
  });

  it("creates a job with only its name and selects it for resume work", async () => {
    const createdJob: Job = {
      ...job,
      id: 8,
      name: "数据分析师",
      jd_text: "",
      boss_entry_url: "",
      default_requested_count: undefined,
      critical_fields: [],
      critical_fields_confirmed: false,
      readiness: { ready: false, missing: ["boss_entry_url", "default_requested_count", "critical_fields"] },
    };
    vi.mocked(api.listJobs).mockResolvedValue([]);
    vi.mocked(api.createJob).mockResolvedValue(createdJob);
    const wrapper = mount(ResumesPage, { global: { stubs: { teleport: true } } });
    await flushPromises();

    await wrapper.get('[aria-label="在简历库新建岗位"]').trigger("click");
    expect(wrapper.find('[aria-label="职位描述"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="BOSS 岗位入口"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="默认筛选人数"]').exists()).toBe(false);
    await wrapper.get('[aria-label="岗位名称"]').setValue("数据分析师");
    await wrapper.get('[aria-label="简历库新建岗位表单"]').trigger("submit");
    await flushPromises();

    expect(api.createJob).toHaveBeenCalledWith(expect.objectContaining({
      name: "数据分析师",
      jd_text: "",
      boss_entry_url: "",
      default_requested_count: null,
      critical_fields: [],
      critical_fields_confirmed: false,
    }));
    expect(wrapper.get('[aria-label="选择岗位数据分析师"]').attributes("aria-pressed")).toBe("true");
    expect(api.listResumes).toHaveBeenCalledWith({ jobId: 8 });
    expect(wrapper.get('[aria-label="选择简历文件"]')).toBeTruthy();
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
  });

  it("shows job creation errors in the drawer without losing entered data", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([]);
    vi.mocked(api.createJob).mockRejectedValue(new Error("name already exists"));
    const wrapper = mount(ResumesPage, { global: { stubs: { teleport: true } } });
    await flushPromises();

    await wrapper.get('[aria-label="在简历库新建岗位"]').trigger("click");
    await wrapper.get('[aria-label="岗位名称"]').setValue("重复岗位");
    await wrapper.get('[aria-label="简历库新建岗位表单"]').trigger("submit");
    await flushPromises();

    expect(wrapper.get('[role="dialog"] [role="alert"]').text()).toContain("创建岗位失败");
    expect(wrapper.get<HTMLInputElement>('[aria-label="岗位名称"]').element.value).toBe("重复岗位");
  });

  it("ignores candidate and resume responses from a previously selected job", async () => {
    const secondJob = { ...job, id: 2, name: "产品经理" };
    const secondCandidate: api.Candidate = {
      id: 8, name: "周宁", boss_id: "boss-8", fingerprint: "fingerprint-8",
      phone: null, email: null, phone_normalized: null, email_normalized: null,
      merged_into_candidate_id: null, age: 31, years_of_experience: 7,
      job_segments_json: "[]", source: "boss", created_at: null,
    };
    const secondResume = { ...resume, id: 10, candidate_id: null, original_filename: "product.pdf" };
    let resolveOldCandidates!: (rows: api.Candidate[]) => void;
    let resolveOldResumes!: (rows: api.Resume[]) => void;
    vi.mocked(api.listJobs).mockResolvedValue([job, secondJob]);
    vi.mocked(api.listCandidates).mockImplementation((_query, filters) => {
      if (filters?.jobId === 1) return new Promise((resolve) => { resolveOldCandidates = resolve; });
      return Promise.resolve([secondCandidate]);
    });
    vi.mocked(api.listResumes).mockImplementation((filters) => {
      if (filters?.jobId === 1) return new Promise((resolve) => { resolveOldResumes = resolve; });
      return Promise.resolve([secondResume]);
    });
    const wrapper = mount(ResumesPage);
    await flushPromises();

    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await wrapper.get('[aria-label="选择岗位产品经理"]').trigger("click");
    await flushPromises();
    resolveOldCandidates([{ ...secondCandidate, id: 7, name: "旧岗位候选人" }]);
    resolveOldResumes([{ ...secondResume, id: 9, original_filename: "old-job.pdf" }]);
    await flushPromises();

    expect(wrapper.text()).toContain("product.pdf");
    expect(wrapper.text()).not.toContain("old-job.pdf");
    expect(wrapper.get('[aria-label="选择简历候选人"]').text()).toContain("周宁");
    expect(wrapper.get('[aria-label="选择简历候选人"]').text()).not.toContain("旧岗位候选人");
  });

  it("does not show an upload result after switching away from its job", async () => {
    const secondJob = { ...job, id: 2, name: "产品经理" };
    let resolveUpload!: (row: api.Resume) => void;
    vi.mocked(api.listJobs).mockResolvedValue([job, secondJob]);
    vi.mocked(api.listCandidates).mockResolvedValue([existingCandidate]);
    vi.mocked(api.uploadResume).mockImplementation(() => new Promise((resolve) => { resolveUpload = resolve; }));
    const wrapper = mount(ResumesPage);
    await flushPromises();

    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();
    await wrapper.get('[aria-label="选择简历候选人"]').setValue("7");
    const file = new File(["resume"], "resume.pdf", { type: "application/pdf" });
    Object.defineProperty(wrapper.get<HTMLInputElement>('[aria-label="选择简历文件"]').element, "files", {
      value: [file], configurable: true,
    });
    await wrapper.get('[aria-label="选择简历文件"]').trigger("change");
    await wrapper.get("form.resume-version-upload").trigger("submit");
    await wrapper.get('[aria-label="选择岗位产品经理"]').trigger("click");
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();
    resolveUpload(resume);
    await flushPromises();

    expect(wrapper.text()).not.toContain("上传结果");
    expect(wrapper.text()).not.toContain("记录编号：9");
  });

  it("ignores an active-version result after switching away from its job", async () => {
    const secondJob = { ...job, id: 2, name: "产品经理" };
    let resolveActivation!: (row: api.CandidateJob) => void;
    vi.mocked(api.listJobs).mockResolvedValue([job, secondJob]);
    vi.mocked(api.listCandidates).mockResolvedValue([existingCandidate]);
    vi.mocked(api.listResumes).mockImplementation((filters) => Promise.resolve(filters?.jobId === 1 ? [resume] : []));
    vi.mocked(api.listCandidateJobs).mockResolvedValue([]);
    vi.mocked(api.setActiveResume).mockImplementation(() => new Promise((resolve) => { resolveActivation = resolve; }));
    const wrapper = mount(ResumesPage);
    await flushPromises();

    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();
    await wrapper.get('[aria-label="设 candidate.pdf 为当前版本"]').trigger("click");
    await wrapper.get('[aria-label="选择岗位产品经理"]').trigger("click");
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();
    resolveActivation({
      id: 31, candidate_id: 7, job_id: 1, status: "resume_received", active_resume_id: 9,
      latest_score_event_id: null, review_reason_json: "{}", created_at: null, updated_at: null,
    });
    await flushPromises();

    expect(wrapper.text()).not.toContain("已切换当前版本");
  });

  it("uploads PDF files directly to the selected job without a candidate", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job]);
    vi.mocked(api.listCandidates).mockResolvedValue([]);
    vi.mocked(api.batchImportResumes).mockResolvedValue({
      job_id: 1,
      summary: { imported: 1, duplicate: 1, failed: 0 },
      items: [
        { original_filename: "new.pdf", status: "imported", resume_id: 21, error: "" },
        { original_filename: "known.pdf", status: "duplicate", resume_id: 9, error: "" },
      ],
    });
    const wrapper = mount(ResumesPage);
    await flushPromises();
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();

    const files = [
      new File(["%PDF-1.4 new"], "new.pdf", { type: "application/pdf" }),
      new File(["%PDF-1.4 known"], "known.pdf", { type: "application/pdf" }),
    ];
    const input = wrapper.get<HTMLInputElement>('[aria-label="选择岗位简历文件"]');
    Object.defineProperty(input.element, "files", { configurable: true, value: files });
    await input.trigger("change");
    await wrapper.get("form.direct-resume-upload").trigger("submit");
    await flushPromises();

    expect(api.batchImportResumes).toHaveBeenCalledWith(files, 1);
    expect(api.uploadResume).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("成功 1 份");
    expect(wrapper.text()).toContain("重复 1 份");
    expect(api.listResumes).toHaveBeenLastCalledWith({ jobId: 1 });
  });

  it("uploads a selected file and displays the real parse status", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job]);
    vi.mocked(api.uploadResume).mockResolvedValue(resume);
    const wrapper = mount(ResumesPage);
    await flushPromises();
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();
    await wrapper.get("form.resume-version-upload").trigger("submit");
    expect(api.uploadResume).not.toHaveBeenCalled();

    await wrapper.get('[aria-label="选择简历候选人"]').setValue("7");
    const file = new File(["resume"], "candidate.pdf", { type: "application/pdf" });
    await selectFile(wrapper, file);
    await wrapper.get("form.resume-version-upload").trigger("submit");
    await flushPromises();

    expect(api.uploadResume).toHaveBeenCalledWith(file, 7, 1);
    expect(api.listResumes).toHaveBeenLastCalledWith({ jobId: 1 });
    expect(wrapper.text()).toContain("解析状态：parsed");
  });

  it("keeps a newly uploaded version inactive until a user switches it", async () => {
    const oldResume = { ...resume, id: 8, version_number: 1, original_filename: "candidate-v1.pdf", supersedes_resume_id: null };
    vi.mocked(api.listJobs).mockResolvedValue([job]);
    vi.mocked(api.listResumes)
      .mockResolvedValueOnce([oldResume])
      .mockResolvedValueOnce([oldResume, resume]);
    vi.mocked(api.listCandidateJobs).mockResolvedValue([{
      id: 31, candidate_id: 7, job_id: 1, status: "scored", active_resume_id: 8,
      latest_score_event_id: 51, review_reason_json: "{}", created_at: null, updated_at: null,
    }]);
    vi.mocked(api.uploadResume).mockResolvedValue(resume);
    const wrapper = mount(ResumesPage);
    await flushPromises();
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();
    await wrapper.get('[aria-label="选择简历候选人"]').setValue("7");
    const file = new File(["resume"], "candidate.pdf", { type: "application/pdf" });
    await selectFile(wrapper, file);
    await wrapper.get("form.resume-version-upload").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("candidate-v1.pdf");
    expect(wrapper.text()).toContain("当前使用");
    expect(wrapper.text()).toContain("candidate.pdf");
    expect(wrapper.text()).toContain("尚未启用");
    expect(api.setActiveResume).not.toHaveBeenCalled();
    expect(api.reEvaluateCandidateJob).not.toHaveBeenCalled();
  });

  it("switches the active resume without inventing a new score", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job]);
    vi.mocked(api.listResumes).mockResolvedValue([resume]);
    vi.mocked(api.listCandidateJobs)
      .mockResolvedValueOnce([{
        id: 31, candidate_id: 7, job_id: 1, status: "scored", active_resume_id: 8,
        latest_score_event_id: 51, review_reason_json: "{}", created_at: null, updated_at: null,
      }])
      .mockResolvedValueOnce([{
        id: 31, candidate_id: 7, job_id: 1, status: "scored", active_resume_id: 9,
        latest_score_event_id: 51, review_reason_json: "{}", created_at: null, updated_at: null,
      }]);
    vi.mocked(api.setActiveResume).mockResolvedValue({
      id: 31, candidate_id: 7, job_id: 1, status: "scored", active_resume_id: 9,
      latest_score_event_id: 51, review_reason_json: "{}", created_at: null, updated_at: null,
    });
    const wrapper = mount(ResumesPage);
    await flushPromises();
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();

    await wrapper.get('[aria-label="设 candidate.pdf 为当前版本"]').trigger("click");
    await flushPromises();

    expect(api.setActiveResume).toHaveBeenCalledWith(7, 1, 9);
    expect(api.reEvaluateCandidateJob).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("已切换当前版本，未自动重新评分");
  });

  it("allows re-evaluation directly from the selected JD and resume", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job]);
    vi.mocked(api.listResumes).mockResolvedValue([resume]);
    vi.mocked(api.listCandidateJobs).mockResolvedValue([{
      id: 31, candidate_id: 7, job_id: 1, status: "scored", active_resume_id: 8,
      latest_score_event_id: 51, review_reason_json: "{}", created_at: null, updated_at: null,
    }]);
    const wrapper = mount(ResumesPage);
    await flushPromises();
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();

    expect(wrapper.get('[aria-label="使用 candidate.pdf 重新评估"]').attributes("disabled")).toBeUndefined();
    expect(wrapper.text()).toContain("完整 JD 与所选简历版本");
    expect(wrapper.text()).not.toContain("关键资料");
  });

  it("manually re-evaluates the selected version and displays only the returned score", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job]);
    vi.mocked(api.listResumes).mockResolvedValue([resume]);
    vi.mocked(api.listCandidateJobs).mockResolvedValue([{
      id: 31, candidate_id: 7, job_id: 1, status: "scored", active_resume_id: 8,
      latest_score_event_id: 51, review_reason_json: "{}", created_at: null, updated_at: null,
    }]);
    vi.mocked(api.reEvaluateCandidateJob).mockResolvedValue({
      id: 52, candidate_id: 7, job_id: 1, candidate_job_id: 31, resume_id: 9, task_id: null,
      hard_filter_passed: true, hard_filter_reasons: [], score: 91, reason: "经验匹配",
      evidence: ["Vue 6 年"], missing_fields: [], estimated_fields: [], critical_fields: [],
      confidence: 0.88, decision: "eligible", model: "configured-model", created_at: "2026-09-23T08:00:00Z",
    });
    const wrapper = mount(ResumesPage);
    await flushPromises();
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();
    await wrapper.get('[aria-label="使用 candidate.pdf 重新评估"]').trigger("click");
    await flushPromises();

    expect(api.reEvaluateCandidateJob).toHaveBeenCalledWith(7, 1, 9);
    expect(wrapper.text()).toContain("91 分");
    expect(wrapper.text()).toContain("eligible");
    expect(wrapper.text()).toContain("Vue 6 年");
    expect(wrapper.text()).toContain("88%");
    expect(wrapper.text()).toContain("configured-model");
    expect(wrapper.text()).toContain("不会自动联系候选人");
  });

  it("clears the last upload feedback when the selected job changes", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job, { ...job, id: 2, name: "产品经理" }]);
    vi.mocked(api.uploadResume).mockResolvedValue(resume);
    const wrapper = mount(ResumesPage);
    await flushPromises();
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();
    await wrapper.get('[aria-label="选择简历候选人"]').setValue("7");
    const file = new File(["resume"], "candidate.pdf", { type: "application/pdf" });
    await selectFile(wrapper, file);
    await wrapper.get("form.resume-version-upload").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("解析状态：parsed");

    await wrapper.get('[aria-label="选择岗位产品经理"]').trigger("click");
    expect(wrapper.text()).not.toContain("解析状态：parsed");
  });

  it("shows retryable job and upload errors without fake resumes", async () => {
    vi.mocked(api.listJobs).mockRejectedValue(new Error("503 jobs unavailable"));
    const failed = mount(ResumesPage);
    await flushPromises();
    expect(failed.get('[role="alert"]').text()).toContain("加载岗位失败");
    expect(failed.text()).not.toContain("示例简历");

    vi.mocked(api.listJobs).mockResolvedValue([job]);
    vi.mocked(api.uploadResume).mockRejectedValue(new Error("500 upload failed"));
    const wrapper = mount(ResumesPage);
    await flushPromises();
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    await flushPromises();
    await wrapper.get('[aria-label="选择简历候选人"]').setValue("7");
    const file = new File(["resume"], "candidate.pdf", { type: "application/pdf" });
    await selectFile(wrapper, file);
    await wrapper.get("form.resume-version-upload").trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("上传简历失败");
    expect(wrapper.get('[aria-label="重新上传简历"]')).toBeTruthy();
  });
});
