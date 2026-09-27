import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  createScreeningTask,
  me,
  previewCandidateMerge,
  suggestCriticalFields,
} from "../api";

describe("authenticated API requests", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("dispatches the unauthorized event from a real 401 response", async () => {
    sessionStorage.setItem("access_token", "expired-access");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(
      JSON.stringify({ detail: "unauthorized" }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    ));
    const listener = vi.fn();
    window.addEventListener("resume-screening:unauthorized", listener, { once: true });

    await expect(me()).rejects.toThrow("unauthorized");

    expect(listener).toHaveBeenCalledOnce();
  });

  it("sends confirmed critical fields when creating a screening task", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ id: 8 }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));

    await createScreeningTask({
      job_id: 3,
      assigned_agent_run_id: 7,
      requested_count: 20,
      critical_fields: [{ key: "portfolio", label: "作品集" }],
      critical_fields_source: { confirmed: true, source: "manual" },
    });

    expect(fetch).toHaveBeenCalledWith("/api/screening-tasks", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        job_id: 3,
        assigned_agent_run_id: 7,
        requested_count: 20,
        critical_fields: [{ key: "portfolio", label: "作品集" }],
        critical_fields_source: { confirmed: true, source: "manual" },
      }),
    }));
  });

  it("requests critical-field suggestions for a persisted job", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      suggestions: [{ key: "portfolio", label: "作品集", reason: "岗位要求提供作品" }],
      model: "configured-model",
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));

    await suggestCriticalFields(7);

    expect(fetch).toHaveBeenCalledWith(
      "/api/jobs/7/critical-fields/suggest",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("preserves structured merge conflicts in ApiError", async () => {
    const detail = { message: "merge blocked", conflicts: [{ entity_type: "task", reason: "running" }] };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail }), {
      status: 409,
      headers: { "Content-Type": "application/json" },
    }));

    await expect(previewCandidateMerge({
      source_candidate_id: 1,
      target_candidate_id: 2,
      field_choices: {},
    })).rejects.toMatchObject({ status: 409, detail });
  });
});
