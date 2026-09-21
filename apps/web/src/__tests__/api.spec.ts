import { afterEach, describe, expect, it, vi } from "vitest";

import { me } from "../api";

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
});
