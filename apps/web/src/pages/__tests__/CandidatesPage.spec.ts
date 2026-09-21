import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import type { Candidate, UserMe } from "../../api";
import CandidatesPage from "../CandidatesPage.vue";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return { ...actual, listCandidates: vi.fn(), markExchange: vi.fn() };
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
  age: 29,
  years_of_experience: 6,
  job_segments_json: "[]",
  source: "boss",
  created_at: "2026-09-20T08:00:00Z",
};

function mountPage() {
  return mount(CandidatesPage, {
    props: { user },
    global: { stubs: { teleport: true } },
  });
}

describe("CandidatesPage", () => {
  beforeEach(() => vi.resetAllMocks());

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
      expect(wrapper.get(`[aria-label="${label}"]`).attributes("disabled")).toBeDefined();
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
