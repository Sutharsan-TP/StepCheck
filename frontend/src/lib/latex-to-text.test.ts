import { describe, expect, it } from "vitest";

import { latexToText } from "./latex-to-text";
import { textToLatex } from "./math-renderer";

const text = (latex: string) => {
  const result = latexToText(latex);
  if (!result.ok) throw new Error(`refused: ${result.reason}`);
  return result.text;
};

describe("latexToText: algebra", () => {
  it.each([
    ["2x+5=15", "2x + 5 = 15"],
    ["x^{2}-5x+6=0", "x^2 - 5x + 6 = 0"],
    ["x=-3", "x = -3"],
    ["x=\\frac{5\\pm\\sqrt{13}}{2}", "x = (5 ± sqrt(13))/2"],
    ["x=2\\text{or}x=3", "x = 2 or x = 3"],
    ["(x-2)(x-3)=0", "(x - 2)(x - 3) = 0"],
    ["\\left(x+1\\right)^{2}=4", "(x + 1)^2 = 4"],
    ["\\frac{x}{3}=4", "x/3 = 4"],
    ["\\frac{1}{2}x=3", "(1/2) x = 3"],
    ["3\\cdot x=6", "3 * x = 6"],
    ["x^{-1}", "x^-1"],
    ["1.5x", "1.5x"],
    ["x\\cdot x", "x * x"],
  ])("%s", (latex, expected) => {
    expect(text(latex)).toBe(expected);
  });
});

describe("latexToText: calculus", () => {
  it.each([
    ["\\frac{d}{dx}\\left(x^{2}\\sin\\left(x\\right)\\right)", "d/dx(x^2 sin(x))"],
    ["\\frac{\\mathrm{d}}{\\mathrm{d}x}x^{3}", "d/dx(x^3)"],
    ["\\int x^{2}\\,dx", "int(x^2) dx"],
    ["\\int\\left(2x+1\\right)\\,\\mathrm{d}x", "int(2x + 1) dx"],
    ["\\int_{0}^{2}x^{2}\\,dx", "int[0, 2](x^2) dx"],
    ["\\int_{0}^{\\pi}\\sin\\left(x\\right)dx", "int[0, pi](sin(x)) dx"],
    ["\\lim_{x\\to0}\\frac{\\sin x}{x}", "lim(x->0, sin(x)/x)"],
    ["\\lim_{x\\to\\infty}\\frac{1}{x}", "lim(x->oo, 1/x)"],
    ["\\left[\\frac{x^{3}}{3}\\right]_{0}^{2}", "[x^3/3][0, 2]"],
    ["\\frac{x^{3}}{3}+C", "x^3/3 + C"],
    ["e^{2x}", "e^(2x)"],
    ["\\sin^{2}\\left(x\\right)+\\cos^{2}x", "sin^2(x) + cos^2(x)"],
    ["\\ln\\left(x\\right)+\\log x", "ln(x) + log(x)"],
    ["\\arctan\\left(x\\right)", "arctan(x)"],
    ["\\left|x\\right|", "abs(x)"],
    ["\\sqrt{x+1}", "sqrt(x + 1)"],
    ["2\\pi+\\infty", "2 pi + oo"],
    ["2x\\sin x", "2x sin(x)"],
    ["\\frac{d}{dx}\\left(x^{2}\\right)=2x", "d/dx(x^2) = 2x"],
  ])("%s", (latex, expected) => {
    expect(text(latex)).toBe(expected);
  });

  it("treats an integral's dx as its end, not as a product", () => {
    expect(text("\\int x\\,dx+1")).toBe("int(x) dx + 1");
  });
});

describe("latexToText: refusals", () => {
  it.each([
    ["\\sum_{i=1}^{n}i", /isn't supported/],
    ["\\begin{matrix}1\\end{matrix}", /isn't supported/],
    ["x_{1}", /Subscripts/],
    ["\\sqrt[3]{x}", /Only square roots/],
    ["\\int x", /End the integral with dx/],
    ["\\int_{0}x\\,dx", /both limits/],
    ["\\lim_{y\\to0}y", /x → a/],
    ["\\left[x\\right]", /followed by the limits/],
    ["\\placeholder{}+1", /empty box/],
    ["\\frac{d}{dx}", /missing its argument/],
    ["(x+1", /ends unexpectedly|don't match/],
    ["x+1)", /don't match/],
    ["\\text{hello}", /isn't supported/],
    ["\\href{x}{y}", /isn't supported/],
    ["x\\cdot", /needs something after/],
    ["x^{", /ends unexpectedly|isn't supported/],
  ])("%s", (latex, reason) => {
    const result = latexToText(latex);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(reason);
  });

  it("returns an empty step for an empty field", () => {
    expect(latexToText("  ")).toEqual({ ok: true, text: "" });
  });

  it("never throws, whatever the field contains", () => {
    for (const junk of ["\\", "{", "}}}", "^^", "\\left", "\\right)", "\\frac{1}", "\\int_^", "\\lim_{", "$$", "\u0000"]) {
      expect(() => latexToText(junk)).not.toThrow();
    }
  });
});

describe("round trip with the typed-text preview", () => {
  const norm = (s: string) => s.replace(/\s+/g, "").replace(/\(\((.*?)\)\)/g, "($1)");
  it.each([
    "2x + 5 = 15",
    "x^2 - 5x + 6 = 0",
    "d/dx(x^2 sin(x))",
    "int(x^2) dx",
    "int[0, 2](x^2) dx",
    "lim(x->0, sin(x)/x)",
    "[x^3/3][0, 2]",
    "x^3/3 + C",
    "d/dx(sin(x^2)) = 2x cos(x^2)",
    "sin(x)^2 + cos(x)^2",
  ])("%s", (original) => {
    const back = text(textToLatex(original));
    expect(norm(back)).toBe(norm(original));
  });
});
