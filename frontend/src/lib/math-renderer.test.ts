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

  it.each([
    ["d/dx(x^2 sin(x))", "\\frac{d}{dx}\\left(x^{2} \\sin (x)\\right)"],
    ["int(x^2) dx", "\\int x^{2} \\, dx"],
    ["∫(cos(x)) dx", "\\int \\cos (x) \\, dx"],
    ["int[0, pi](sin(x)) dx", "\\int_{0}^{\\pi } \\sin (x) \\, dx"],
    ["lim(x->0, sin(x)/x)", "\\lim_{x \\to 0} \\sin (x)/x"],
    ["lim(x->oo, 1/x)", "\\lim_{x \\to \\infty } 1/x"],
    ["[x^3/3][0, 2]", "\\left[x^{3}/3\\right]_{0}^{2}"],
    ["abs(x) + ln(x) + C", "\\left|x\\right| + \\ln (x) + C"],
    ["e^(2x) + log(x)", "e^{2x} + \\log_{10} (x)"],
    ["arctan(x) + exp(x)", "\\arctan (x) + \\exp (x)"],
  ])("calculus: %s", (input, expected) => {
    expect(textToLatex(input)).toBe(expected);
  });

  it("previews unfinished calculus input without throwing", () => {
    for (const partial of ["d/dx(", "int[0, ", "lim(x->", "[x][0", "int(x"]) {
      expect(() => renderLatex(textToLatex(partial))).not.toThrow();
    }
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
