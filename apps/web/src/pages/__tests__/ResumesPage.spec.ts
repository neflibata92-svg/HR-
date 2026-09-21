import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import type { Job, Resume } from "../../api";
import ResumesPage from "../ResumesPage.vue";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return { ...actual, listJobs: vi.fn(), uploadResume: vi.fn() };
});

const job: Job = {
  id: 1, name: "高级前端工程师", jd_text: "前端岗位", score_threshold: 80,
  greet_template: "您好", boss_entry_url: "", hourly_greet_limit: 20,
  min_action_delay_ms: 1500, max_action_delay_ms: 4000, enabled: true,
  created_at: "2026-09-20T08:00:00Z",
};

const resume: Resume = {
  id: 9, candidate_id: null, file_path: "/data/resume.pdf", parsed_text: "",
  source: "upload", parse_status: "parsed", created_at: "2026-09-21T09:00:00Z",
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
  beforeEach(() => vi.resetAllMocks());

  it("keeps the original resume library structure after selecting a real job", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job]);
    const wrapper = mount(ResumesPage);
    await flushPromises();

    expect(wrapper.text()).toContain("RESUME LIBRARY.");
    expect(wrapper.text()).toContain("STEP 01 / 选择一个岗位");
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    expect(wrapper.findAll("[data-testid^='resume-stat-']")).toHaveLength(3);
    expect(wrapper.findAll("[data-testid^='resume-stat-']").every((node) => node.text().includes("—"))).toBe(true);
    for (const label of ["按姓名筛选简历", "按分数筛选简历", "按标签筛选简历", "按状态筛选简历"]) {
      expect(wrapper.get(`[aria-label="${label}"]`).attributes("disabled")).toBeDefined();
    }
    expect(wrapper.text()).toContain("简历列表及岗位关联暂未接入");
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
    expect(wrapper.get('[aria-label="选择简历文件"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("后端尚不支持简历列表及岗位关联");
  });

  it("shows an honest empty state when no enabled jobs are available", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([{ ...job, enabled: false }]);
    const wrapper = mount(ResumesPage);
    await flushPromises();

    expect(wrapper.text()).toContain("暂无可用岗位");
    expect(wrapper.text()).not.toContain("请先选择岗位");
    expect(wrapper.find('[aria-label="选择简历文件"]').exists()).toBe(false);
  });

  it("uploads a selected file and displays the real parse status", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job]);
    vi.mocked(api.uploadResume).mockResolvedValue(resume);
    const wrapper = mount(ResumesPage);
    await flushPromises();
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");

    await wrapper.get("form").trigger("submit");
    expect(api.uploadResume).not.toHaveBeenCalled();

    const file = new File(["resume"], "candidate.pdf", { type: "application/pdf" });
    await selectFile(wrapper, file);
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(api.uploadResume).toHaveBeenCalledWith(file);
    expect(wrapper.text()).toContain("解析状态：parsed");
  });

  it("clears the last upload feedback when the selected job changes", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job, { ...job, id: 2, name: "产品经理" }]);
    vi.mocked(api.uploadResume).mockResolvedValue(resume);
    const wrapper = mount(ResumesPage);
    await flushPromises();
    await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
    const file = new File(["resume"], "candidate.pdf", { type: "application/pdf" });
    await selectFile(wrapper, file);
    await wrapper.get("form").trigger("submit");
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
    const file = new File(["resume"], "candidate.pdf", { type: "application/pdf" });
    await selectFile(wrapper, file);
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("上传简历失败");
    expect(wrapper.get('[aria-label="重新上传简历"]').exists()).toBe(true);
  });
});
