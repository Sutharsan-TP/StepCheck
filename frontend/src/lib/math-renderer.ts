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

/** Index of the bracket that closes the one at `open` (any of ( [ ), or -1. */
function matchBracket(text: string, open: number): number {
  const pairs: Record<string, string> = { "(": ")", "[": "]" };
  const close = pairs[text[open]];
  let depth = 0;
  for (let i = open; i < text.length; i++) {
    if (text[i] === text[open]) depth++;
    else if (text[i] === close && --depth === 0) return i;
  }
  return -1;
}

/** Split at the first comma that is not inside brackets. */
function splitTopLevelComma(text: string): [string, string] | null {
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "(" || text[i] === "[") depth++;
    else if (text[i] === ")" || text[i] === "]") depth--;
    else if (text[i] === "," && depth === 0) return [text.slice(0, i), text.slice(i + 1)];
  }
  return null;
}

const FUNCTION = /^(arcsin|arccos|arctan|asin|acos|atan|sin|cos|tan|sec|csc|cot|ln|log|exp)(?![a-wyz])/;
const FUNCTION_LATEX: Record<string, string> = {
  arcsin: "\\arcsin", arccos: "\\arccos", arctan: "\\arctan", asin: "\\arcsin", acos: "\\arccos", atan: "\\arctan",
  sin: "\\sin", cos: "\\cos", tan: "\\tan", sec: "\\sec", csc: "\\csc", cot: "\\cot", ln: "\\ln", log: "\\log_{10}", exp: "\\exp",
};

/** After a calculus operator's closing bracket: skip an optional " dx" and return the new index. */
function skipDx(text: string, after: number): number {
  const m = /^\s*dx\b/.exec(text.slice(after + 1));
  return m ? after + m[0].length : after;
}

/**
 * Best-effort conversion of typed steps (e.g. "x^2 - sqrt(13) = 0", "d/dx(x^2 sin(x))")
 * to LaTeX for the live preview only. The backend's LaTeX is authoritative once verified.
 */
export function textToLatex(input: string): string {
  const text = input
    .replace(/[⁰¹²³⁴⁵⁶⁷⁸⁹]+/g, (m) => "^" + [...m].map((c) => SUPERSCRIPTS[c]).join(""))
    .replace(/\*\*/g, "^")
    .replace(/\+\/-/g, "±");
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    const prevIsLetter = i > 0 && /[A-Za-z]/.test(text[i - 1]);
    if (text.startsWith("d/dx(", i)) {
      const close = matchBracket(text, i + 4);
      if (close > 0) {
        out += `\\frac{d}{dx}\\left(${textToLatex(text.slice(i + 5, close))}\\right)`;
        i = close;
        continue;
      }
    }
    if (!prevIsLetter && (text.startsWith("int[", i) || text.startsWith("∫[", i))) {
      const open = text.indexOf("[", i);
      const boundsEnd = matchBracket(text, open);
      const bounds = boundsEnd > 0 ? splitTopLevelComma(text.slice(open + 1, boundsEnd)) : null;
      const bodyOpen = boundsEnd > 0 ? boundsEnd + 1 + (/^\s*/.exec(text.slice(boundsEnd + 1))?.[0].length ?? 0) : -1;
      const bodyClose = bodyOpen > 0 && text[bodyOpen] === "(" ? matchBracket(text, bodyOpen) : -1;
      if (bounds && bodyClose > 0) {
        out += `\\int_{${textToLatex(bounds[0].trim())}}^{${textToLatex(bounds[1].trim())}} ${textToLatex(text.slice(bodyOpen + 1, bodyClose))} \\, dx`;
        i = skipDx(text, bodyClose);
        continue;
      }
    }
    if (!prevIsLetter && (text.startsWith("int(", i) || text.startsWith("∫(", i))) {
      const open = text.indexOf("(", i);
      const close = matchBracket(text, open);
      if (close > 0) {
        out += `\\int ${textToLatex(text.slice(open + 1, close))} \\, dx`;
        i = skipDx(text, close);
        continue;
      }
    }
    if (!prevIsLetter && text.startsWith("lim(", i)) {
      const close = matchBracket(text, i + 3);
      const parts = close > 0 ? splitTopLevelComma(text.slice(i + 4, close)) : null;
      if (parts) {
        const approach = parts[0].replace("->", "→").split("→");
        const point = textToLatex((approach[1] ?? "").trim());
        out += `\\lim_{x \\to ${point}} ${textToLatex(parts[1].trim())}`;
        i = close;
        continue;
      }
    }
    if (ch === "[") {
      const close = matchBracket(text, i);
      const boundsEnd = close > 0 && text[close + 1] === "[" ? matchBracket(text, close + 1) : -1;
      const bounds = boundsEnd > 0 ? splitTopLevelComma(text.slice(close + 2, boundsEnd)) : null;
      if (bounds) {
        out += `\\left[${textToLatex(text.slice(i + 1, close))}\\right]_{${textToLatex(bounds[0].trim())}}^{${textToLatex(bounds[1].trim())}}`;
        i = boundsEnd;
        continue;
      }
    }
    if (!prevIsLetter && text.startsWith("abs(", i)) {
      const close = matchBracket(text, i + 3);
      if (close > 0) {
        out += `\\left|${textToLatex(text.slice(i + 4, close))}\\right|`;
        i = close;
        continue;
      }
    }
    if (!prevIsLetter) {
      const fn = FUNCTION.exec(text.slice(i));
      if (fn) {
        out += `${FUNCTION_LATEX[fn[1]]} `;
        i += fn[1].length - 1;
        continue;
      }
      if (/^pi(?![A-Za-z])/.test(text.slice(i))) {
        out += "\\pi ";
        i += 1;
        continue;
      }
      if (/^oo(?![A-Za-z])/.test(text.slice(i))) {
        out += "\\infty ";
        i += 1;
        continue;
      }
    }
    if (text.startsWith("->", i)) {
      out += " \\to ";
      i += 1;
      continue;
    }
    if (ch === "∫") {
      out += "\\int ";
      continue;
    }
    if (ch === "∞" || ch === "π" || ch === "→") {
      out += { "∞": "\\infty ", "π": "\\pi ", "→": " \\to " }[ch];
      continue;
    }
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
