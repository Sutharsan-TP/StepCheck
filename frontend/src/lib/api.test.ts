import { describe, expect, it, vi } from "vitest";

import verifyDemo2 from "@/test/fixtures/verify-demo2.json";
import { mockFetch } from "@/test/fetch";

import { ApiError, correct, describeError, explain, verify, wakeBackend } from "./api";

const STEPS = ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"];

describe("api client", () => {
  it("posts steps to /verify and returns the parsed response", async () => {
    const calls = mockFetch({ body: verifyDemo2 });
    const result = await verify(STEPS);
    expect(result.first_error_step).toBe(3);
    expect(calls[0].url).toMatch(/\/api\/v1\/verify$/);
    expect(calls[0].body).toEqual({ steps: STEPS, variable: "x", domain: "REAL" });
  });

  it("maps structured errors to ApiError, including Retry-After", async () => {
    mockFetch({ status: 429, body: { error: { code: "RATE_LIMITED", message: "Too many requests." } }, headers: { "Retry-After": "12" } });
    const error = await verify(STEPS).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 429, code: "RATE_LIMITED", retryAfter: 12 });
    expect(describeError(error)).toBe("Too many requests. (try again in 12s)");
  });

  it("handles non-JSON error bodies", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>Bad gateway</html>", { status: 502 })));
    const error = await verify(STEPS).catch((e) => e);
    expect(error).toMatchObject({ status: 502, code: "HTTP_ERROR" });
  });

  it("reports network failures without leaking internals", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const error = await verify(STEPS).catch((e) => e);
    expect(error).toMatchObject({ code: "NETWORK_ERROR" });
    expect(describeError(error)).toMatch(/could not be reached/);
  });

  it.each(["VERIFICATION_NOT_FOUND", "VERIFICATION_EXPIRED"])(
    "falls back to sending the steps when the stored verification is gone (%s)",
    async (code) => {
      const calls = mockFetch(
        { status: code === "VERIFICATION_EXPIRED" ? 410 : 404, body: { error: { code, message: "gone" } } },
        { body: { mode: "FULL", status: "CORRECTED" } },
      );
      await correct({ verificationId: "abc", steps: STEPS }, { mode: "FULL" });
      expect(calls[0].body).toEqual({ verification_id: "abc", mode: "FULL" });
      expect(calls[1].body).toEqual({ steps: STEPS, mode: "FULL" });
    },
  );

  it("does not retry other errors", async () => {
    const calls = mockFetch({ status: 503, body: { error: { code: "AI_UNAVAILABLE", message: "x" } } });
    await expect(explain({ verificationId: "abc", steps: STEPS })).rejects.toMatchObject({ code: "AI_UNAVAILABLE" });
    expect(calls).toHaveLength(1);
  });

  it("pings /health to wake the backend and ignores failures", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("offline"));
    vi.stubGlobal("fetch", fetchMock);
    expect(() => wakeBackend()).not.toThrow();
    await Promise.resolve();
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/v1\/health$/);
  });
});
