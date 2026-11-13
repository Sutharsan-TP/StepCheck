/**
 * Calculator-style keys for entering maths, and how each key edits a text field.
 *
 * A key either inserts a template or moves/deletes. In a template, "|" marks where
 * the caret goes (for example "d/dx(|)" leaves the caret inside the brackets).
 * If text is selected when a template with "|" is inserted, the selection is
 * placed at the marker, so selecting x^2 and pressing sin gives sin(x^2).
 */

export type KeyAction = "backspace" | "left" | "right";
export type Key = { label: string; aria: string; insert?: string; action?: KeyAction; tone?: "operator" | "action" };
export type KeypadPage = "basic" | "functions" | "calculus";

const CARET = "|";

export const KEYPAD: Record<KeypadPage, Key[]> = {
  basic: [
    { label: "7", aria: "7", insert: "7" },
    { label: "8", aria: "8", insert: "8" },
    { label: "9", aria: "9", insert: "9" },
    { label: "÷", aria: "divide", insert: "/", tone: "operator" },
    { label: "(", aria: "open bracket", insert: "(" },
    { label: ")", aria: "close bracket", insert: ")" },
    { label: "4", aria: "4", insert: "4" },
    { label: "5", aria: "5", insert: "5" },
    { label: "6", aria: "6", insert: "6" },
    { label: "×", aria: "multiply", insert: "*", tone: "operator" },
    { label: "x", aria: "x", insert: "x" },
    { label: "x²", aria: "squared", insert: "^2" },
    { label: "1", aria: "1", insert: "1" },
    { label: "2", aria: "2", insert: "2" },
    { label: "3", aria: "3", insert: "3" },
    { label: "−", aria: "minus", insert: " - ", tone: "operator" },
    { label: "xⁿ", aria: "power", insert: "^(|)" },
    { label: "√", aria: "square root", insert: "sqrt(|)" },
    { label: "0", aria: "0", insert: "0" },
    { label: ".", aria: "decimal point", insert: "." },
    { label: "=", aria: "equals", insert: " = ", tone: "operator" },
    { label: "+", aria: "plus", insert: " + ", tone: "operator" },
    { label: "a/b", aria: "fraction", insert: "(|)/()" },
    { label: "π", aria: "pi", insert: "pi" },
    { label: "←", aria: "move left", action: "left", tone: "action" },
    { label: "→", aria: "move right", action: "right", tone: "action" },
    { label: "⌫", aria: "delete", action: "backspace", tone: "action" },
  ],
  functions: [
    { label: "sin", aria: "sine", insert: "sin(|)" },
    { label: "cos", aria: "cosine", insert: "cos(|)" },
    { label: "tan", aria: "tangent", insert: "tan(|)" },
    { label: "sin²", aria: "sine squared", insert: "sin^2(|)" },
    { label: "cos²", aria: "cosine squared", insert: "cos^2(|)" },
    { label: "sec", aria: "secant", insert: "sec(|)" },
    { label: "csc", aria: "cosecant", insert: "csc(|)" },
    { label: "cot", aria: "cotangent", insert: "cot(|)" },
    { label: "sin⁻¹", aria: "inverse sine", insert: "arcsin(|)" },
    { label: "cos⁻¹", aria: "inverse cosine", insert: "arccos(|)" },
    { label: "tan⁻¹", aria: "inverse tangent", insert: "arctan(|)" },
    { label: "ln", aria: "natural log", insert: "ln(|)" },
    { label: "log₁₀", aria: "log base 10", insert: "log(|)" },
    { label: "eˣ", aria: "e to the power", insert: "e^(|)" },
    { label: "e", aria: "e", insert: "e" },
    { label: "|x|", aria: "absolute value", insert: "abs(|)" },
    { label: "←", aria: "move left", action: "left", tone: "action" },
    { label: "→", aria: "move right", action: "right", tone: "action" },
    { label: "⌫", aria: "delete", action: "backspace", tone: "action" },
  ],
  calculus: [
    { label: "d/dx", aria: "derivative", insert: "d/dx(|)" },
    { label: "∫ dx", aria: "integral", insert: "int(|) dx" },
    { label: "∫ₐᵇ dx", aria: "definite integral", insert: "int[|, ]() dx" },
    { label: "lim", aria: "limit", insert: "lim(x->|, )" },
    { label: "[F]ₐᵇ", aria: "evaluate between limits", insert: "[|][, ]" },
    { label: "+ C", aria: "plus constant of integration", insert: " + C" },
    { label: "∞", aria: "infinity", insert: "oo" },
    { label: "→", aria: "tends to", insert: "->" },
    { label: ",", aria: "comma", insert: ", " },
    { label: "←", aria: "move left", action: "left", tone: "action" },
    { label: "→", aria: "move right", action: "right", tone: "action" },
    { label: "⌫", aria: "delete", action: "backspace", tone: "action" },
  ],
};

export type Edit = { value: string; caret: number };

/** Apply a key to a text field's value and selection; returns the new value and caret. */
export function applyKey(value: string, start: number, end: number, key: Key): Edit {
  const from = Math.max(0, Math.min(start, end, value.length));
  const to = Math.min(Math.max(start, end), value.length);
  if (key.action === "left") return { value, caret: from === to ? Math.max(0, from - 1) : from };
  if (key.action === "right") return { value, caret: from === to ? Math.min(value.length, to + 1) : to };
  if (key.action === "backspace") {
    if (from !== to) return { value: value.slice(0, from) + value.slice(to), caret: from };
    if (from === 0) return { value, caret: 0 };
    return { value: value.slice(0, from - 1) + value.slice(from), caret: from - 1 };
  }
  const template = key.insert ?? "";
  const marker = template.indexOf(CARET);
  const selected = value.slice(from, to);
  if (marker < 0) {
    return { value: value.slice(0, from) + template + value.slice(to), caret: from + template.length };
  }
  const inserted = template.slice(0, marker) + selected + template.slice(marker + 1);
  return {
    value: value.slice(0, from) + inserted + value.slice(to),
    caret: from + marker + selected.length,
  };
}
