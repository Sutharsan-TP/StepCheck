import { describe, expect, it } from "vitest";

import { renderLatex, textToLatex } from "./math-renderer";

describe("textToLatex", () => {
  it.each([
    ["x^2 - 5x + 6 = 0", "x^{2} - 5x + 6 = 0"],
    ["x² = 9", "x^{2} = 9"],
    ["x = (5 ± sqrt(13))/2", "x = (5  \\pm  \\sqrt{13})/2"],
    ["x = 2 or x = 3", "x = 2 \\quad\\text{or}\\quad  x = 3"],
    ["2*x = 4", "2 \\cdot x = 4"],
    ["(x+1)^(2) = 4", "(x+1)^{2} = 4"],
    ["x = √13", "x = \\sqrt{13}"],
    ["x = sqrt(sqrt(16))", "x = \\sqrt{\\sqrt{16}}"],
  ])("%s", (input, expected) => {
    expect(textToLatex(input)).toBe(expected);
  });

  it("escapes characters that would be LaTeX commands", () => {
    expect(textToLatex("\\href{x}")).not.toContain("\\href");
    expect(textToLatex("{x}")).toBe("\\{x\\}");
  });
});

describe("renderLatex", () => {
  it("renders valid LaTeX", () => {
    expect(renderLatex("x^{2}")).toContain("katex");
  });

  it("never throws on invalid input and never trusts links", () => {
    expect(() => renderLatex("\\frac{")).not.toThrow();
    expect(renderLatex("\\href{javascript:alert(1)}{x}")).not.toContain("javascript:");
  });
});
