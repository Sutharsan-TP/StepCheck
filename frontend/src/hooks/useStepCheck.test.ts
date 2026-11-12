import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import verifyDemo2 from "@/test/fixtures/verify-demo2.json";
import { mockFetch } from "@/test/fetch";

import { useStepCheck } from "./useStepCheck";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

describe("useStepCheck", () => {
  it("clears the verifying flag after a successful check", async () => {
    // Cache Components keeps the workspace mounted after navigating to /results,
    // so a flag left set would show "Checking…" when the student comes back.
    mockFetch({ body: verifyDemo2 });
    const { result } = renderHook(() => useStepCheck());

    await act(() => result.current.verifySteps(["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"]));

    expect(push).toHaveBeenCalledWith("/results");
    expect(result.current.verifying).toBe(false);
  });

  it("clears the verifying flag and reports the error when the check fails", async () => {
    mockFetch({ status: 422, body: { error: { code: "INVALID_INPUT", message: "Bad step." } } });
    const { result } = renderHook(() => useStepCheck());

    await act(() => result.current.verifySteps(["2x = ", "x = 1"]));

    expect(result.current.verifying).toBe(false);
    expect(result.current.error).toBeTruthy();
  });
});
