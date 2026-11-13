import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { readInputMode, resetInputModeMemory, useInputMode } from "./preferences";

afterEach(() => {
  window.localStorage.clear();
  resetInputModeMemory();
  vi.restoreAllMocks();
});

describe("input mode preference", () => {
  it("defaults to the keypad", () => {
    expect(readInputMode()).toBe("keypad");
    expect(renderHook(() => useInputMode()).result.current[0]).toBe("keypad");
  });

  it("remembers the choice on this device and updates every component using it", () => {
    const a = renderHook(() => useInputMode());
    const b = renderHook(() => useInputMode());
    act(() => a.result.current[1]("visual"));
    expect(a.result.current[0]).toBe("visual");
    expect(b.result.current[0]).toBe("visual");
    expect(window.localStorage.getItem("stepcheck.inputMode.v1")).toBe("visual");
    resetInputModeMemory();
    expect(readInputMode()).toBe("visual"); // survives a reload
  });

  it("ignores a stored value it does not recognise", () => {
    window.localStorage.setItem("stepcheck.inputMode.v1", "hologram");
    expect(readInputMode()).toBe("keypad");
  });

  it("still switches for this page view when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => useInputMode());
    expect(result.current[0]).toBe("keypad");
    act(() => result.current[1]("visual"));
    expect(result.current[0]).toBe("visual");
  });

  it("follows a change made in another tab", () => {
    const { result } = renderHook(() => useInputMode());
    act(() => {
      window.localStorage.setItem("stepcheck.inputMode.v1", "visual");
      window.dispatchEvent(new StorageEvent("storage", { key: "stepcheck.inputMode.v1" }));
    });
    expect(result.current[0]).toBe("visual");
  });
});
