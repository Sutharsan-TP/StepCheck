import { describe, expect, it } from "vitest";

import { applyKey, KEYPAD, type Key } from "./keypad";

const key = (insert: string): Key => ({ label: insert, aria: insert, insert });
const action = (a: Key["action"]): Key => ({ label: "", aria: "", action: a });

describe("applyKey", () => {
  it("inserts plain text at the caret", () => {
    expect(applyKey("2 = 4", 1, 1, key("x"))).toEqual({ value: "2x = 4", caret: 2 });
  });

  it("puts the caret inside a template", () => {
    expect(applyKey("", 0, 0, key("d/dx(|)"))).toEqual({ value: "d/dx()", caret: 5 });
    expect(applyKey("", 0, 0, key("int[|, ]() dx"))).toEqual({ value: "int[, ]() dx", caret: 4 });
    expect(applyKey("", 0, 0, key("lim(x->|, )"))).toEqual({ value: "lim(x->, )", caret: 7 });
  });

  it("wraps the selection in a template", () => {
    expect(applyKey("2 x^2", 2, 5, key("sin(|)"))).toEqual({ value: "2 sin(x^2)", caret: 9 });
  });

  it("replaces the selection with plain text", () => {
    expect(applyKey("x + 1", 4, 5, key("2"))).toEqual({ value: "x + 2", caret: 5 });
  });

  it("deletes and moves", () => {
    expect(applyKey("x^2", 3, 3, action("backspace"))).toEqual({ value: "x^", caret: 2 });
    expect(applyKey("x^2", 0, 0, action("backspace"))).toEqual({ value: "x^2", caret: 0 });
    expect(applyKey("x^2", 1, 3, action("backspace"))).toEqual({ value: "x", caret: 1 });
    expect(applyKey("x^2", 2, 2, action("left"))).toEqual({ value: "x^2", caret: 1 });
    expect(applyKey("x^2", 3, 3, action("right"))).toEqual({ value: "x^2", caret: 3 });
  });

  it("every template has at most one caret marker", () => {
    for (const page of Object.values(KEYPAD)) {
      for (const k of page) {
        expect((k.insert ?? "").split("|").length).toBeLessThanOrEqual(2);
        expect(k.aria).not.toBe("");
      }
    }
  });
});
