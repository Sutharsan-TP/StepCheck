import katex from "katex";

/** Render LaTeX to HTML. Never throws: invalid input renders as an inline error. */
export function renderLatex(latex: string, displayMode = false): string {
  return katex.renderToString(latex, {
    displayMode,
    throwOnError: false,
    strict: "ignore",
    trust: false, // no \href, \url or other commands that could inject behaviour
    output: "html",
  });
}

const SUPERSCRIPTS: Record<string, string> = {
  "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
};

/** Index of the parenthesis that closes the one at `open`, or -1. */
function matchParen(text: string, open: number): number {
  let depth = 0;
  for (let i = open; i < text.length; i++) {
    if (text[i] === "(") depth++;
    else if (text[i] === ")" && --depth === 0) return i;
  }
  return -1;
}

/**
 * Best-effort conversion of typed steps (e.g. "x^2 - sqrt(13) = 0") to LaTeX for
 * the live preview only. The backend's LaTeX is authoritative once verified.
 */
export function textToLatex(input: string): string {
  const text = input
    .replace(/[⁰¹²³⁴⁵⁶⁷⁸⁹]+/g, (m) => "^" + [...m].map((c) => SUPERSCRIPTS[c]).join(""))
    .replace(/\*\*/g, "^")
    .replace(/\+\/-/g, "±");
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (text.startsWith("sqrt(", i)) {
      const close = matchParen(text, i + 4);
      if (close > 0) {
        out += `\\sqrt{${textToLatex(text.slice(i + 5, close))}}`;
        i = close;
        continue;
      }
    }
    if (ch === "√") {
      out += "\\sqrt{}";
      if (text[i + 1] === "(") {
        const close = matchParen(text, i + 1);
        if (close > 0) {
          out = out.slice(0, -1) + `${textToLatex(text.slice(i + 2, close))}}`;
          i = close;
          continue;
        }
      }
      const num = /^\d+/.exec(text.slice(i + 1));
      if (num) {
        out = out.slice(0, -1) + `${num[0]}}`;
        i += num[0].length;
      }
      continue;
    }
    if (ch === "^") {
      if (text[i + 1] === "(") {
        const close = matchParen(text, i + 1);
        if (close > 0) {
          out += `^{${textToLatex(text.slice(i + 2, close))}}`;
          i = close;
          continue;
        }
      }
      const exp = /^-?\d+/.exec(text.slice(i + 1));
      if (exp) {
        out += `^{${exp[0]}}`;
        i += exp[0].length;
        continue;
      }
    }
    if (ch === "*" || ch === "×" || ch === "·") out += " \\cdot ";
    else if (ch === "±") out += " \\pm ";
    else if (ch === "÷") out += " \\div ";
    else if (ch === "−") out += "-";
    else if (ch === "{" || ch === "}" || ch === "\\" || ch === "%" || ch === "#" || ch === "&" || ch === "$" || ch === "_" || ch === "~") {
      out += `\\${ch === "\\" ? "backslash " : ch}`;
    } else out += ch;
  }
  return out.replace(/\bor\b/g, "\\quad\\text{or}\\quad ");
}
