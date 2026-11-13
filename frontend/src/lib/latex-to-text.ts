/**
 * Converts the LaTeX produced by the visual editor (MathLive) into the plain-text
 * syntax StepCheck's backend reads (e.g. "d/dx(x^2 sin(x))", "int[0, 2](x^2) dx").
 *
 * Only a fixed set of constructs is translated; anything else is refused with a
 * message, so nothing the editor can produce is silently dropped or guessed at.
 * This is a convenience layer only: the backend re-parses the text with its own
 * restricted grammar and remains the authority on what is valid.
 */

export type Conversion = { ok: true; text: string } | { ok: false; reason: string };

class Unsupported extends Error {}

type Tok = { kind: "num" | "letter" | "cmd" | "char"; value: string };
type Factor = { text: string; fraction?: boolean };

const SPACING = new Set([",", ";", ":", "!", " ", ">", "quad", "qquad", "thinspace", "medspace", "thickspace", "negthinspace"]);

const FUNCTIONS: Record<string, string> = {
  sin: "sin", cos: "cos", tan: "tan", sec: "sec", csc: "csc", cot: "cot",
  arcsin: "arcsin", arccos: "arccos", arctan: "arctan", ln: "ln", log: "log", exp: "exp",
};
const FUNCTION_NAMES = /^(sin|cos|tan|sec|csc|cot|arcsin|arccos|arctan|ln|log|exp|sqrt|abs|pi|d\/dx|int|lim)/;

const SYMBOLS: Record<string, string> = { pi: "pi", infty: "oo" };
const CLOSERS = (t: Tok) => (t.kind === "char" && (t.value === ")" || t.value === "}" || t.value === "]")) || (t.kind === "cmd" && t.value === "right");

// ------------------------------------------------------------------ tokenizing

function tokenize(latex: string): Tok[] {
  const out: Tok[] = [];
  let i = 0;
  while (i < latex.length) {
    const ch = latex[i];
    if (/\s/.test(ch)) {
      i++;
    } else if (ch === "\\") {
      const name = /^[A-Za-z]+/.exec(latex.slice(i + 1))?.[0];
      const value = name ?? latex[i + 1] ?? "";
      i += 1 + (name ? name.length : 1);
      if (SPACING.has(value)) continue;
      // The editor writes the constant e and the differential d as dedicated commands.
      if (value === "exponentialE") out.push({ kind: "letter", value: "e" });
      else if (value === "differentialD") out.push({ kind: "letter", value: "d" });
      else out.push({ kind: "cmd", value });
    } else if (/[0-9]/.test(ch) || (ch === "." && /[0-9]/.test(latex[i + 1] ?? ""))) {
      const m = /^[0-9]*\.[0-9]+|^[0-9]+/.exec(latex.slice(i))!;
      out.push({ kind: "num", value: m[0] });
      i += m[0].length;
    } else if (/[A-Za-z]/.test(ch)) {
      out.push({ kind: "letter", value: ch });
      i++;
    } else {
      out.push({ kind: "char", value: ch });
      i++;
    }
  }
  return unwrapUpright(out);
}

/** \mathrm{d} and \mathrm{e} (also \operatorname) are the plain letters d and e. */
function unwrapUpright(toks: Tok[]): Tok[] {
  const out: Tok[] = [];
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i];
    const letter = toks[i + 2];
    if (
      t.kind === "cmd" && (t.value === "mathrm" || t.value === "operatorname") &&
      toks[i + 1]?.value === "{" && letter?.kind === "letter" && (letter.value === "d" || letter.value === "e") &&
      toks[i + 3]?.value === "}"
    ) {
      out.push(letter);
      i += 3;
    } else {
      out.push(t);
    }
  }
  return out;
}

// --------------------------------------------------------- shape of finished text

/** Index of the bracket closing the one at `open`, or -1. */
function closing(s: string, open: number): number {
  let depth = 0;
  for (let i = open; i < s.length; i++) {
    if (s[i] === "(" || s[i] === "[") depth++;
    else if ((s[i] === ")" || s[i] === "]") && --depth === 0) return i;
  }
  return -1;
}

/** A number, a letter, a bracketed group or a function call, with an optional power: one unit for / and ^. */
function isSingleAtom(s: string): boolean {
  let rest = s;
  const head = /^(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+|[A-Za-z]+(?=\(|\^|$)|[A-Za-z](?![A-Za-z]))/.exec(rest);
  if (/^[A-Za-z]*\(/.test(rest) || rest.startsWith("(")) {
    const open = rest.indexOf("(");
    const end = closing(rest, open);
    if (end < 0) return false;
    rest = rest.slice(end + 1);
  } else if (head && !/^[0-9.]+[A-Za-z]/.test(rest)) {
    rest = rest.slice(head[0].length);
  } else {
    return false;
  }
  return rest === "" || /^\^-?(?:[A-Za-z0-9.]+|\(.*\))$/.test(rest);
}

/** True when the text has no sum, difference, equation or list at its top level. */
function isProduct(s: string): boolean {
  let depth = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === "(" || c === "[") depth++;
    else if (c === ")" || c === "]") depth--;
    else if (depth === 0 && "+±=,".includes(c)) return false;
    else if (depth === 0 && c === "-" && i > 0 && s[i - 1] !== "^") return false;
  }
  return true;
}

const parenthesise = (s: string) => `(${s})`;
const endsWithNumber = (s: string) => /(?:^|[^A-Za-z0-9.^])[0-9.]+$/.test(s);
const exponentText = (s: string) => (/^-?(?:[0-9.]+|[A-Za-z])$/.test(s) ? s : parenthesise(s));
/** "(x + 1)" -> "x + 1" when the brackets enclose the whole text. */
const stripOuterParens = (s: string) => (s.startsWith("(") && closing(s, 0) === s.length - 1 ? s.slice(1, -1) : s);

// --------------------------------------------------------------------- parser

const isChar = (t: Tok | undefined, v: string) => t?.kind === "char" && t.value === v;
const isCmd = (t: Tok | undefined, v: string) => t?.kind === "cmd" && t.value === v;
const isLetter = (t: Tok | undefined, v: string) => t?.kind === "letter" && t.value === v;

class Parser {
  private pos = 0;
  constructor(private readonly toks: Tok[]) {}

  private peek(offset = 0): Tok | undefined {
    return this.toks[this.pos + offset];
  }

  private next(): Tok {
    const tok = this.toks[this.pos++];
    if (!tok) throw new Unsupported("The expression ends unexpectedly.");
    return tok;
  }

  done(): boolean {
    return this.pos >= this.toks.length;
  }

  private atDx(): boolean {
    return isLetter(this.peek(), "d") && isLetter(this.peek(1), "x");
  }

  // ---------------------------------------------------------------- structure

  /** Everything up to a closing token, as one expression (operators included). */
  parseSum(closes: (t: Tok) => boolean, inIntegral = false): string {
    let out = "";
    let expectOperand = true; // true at the start and right after an operator
    for (;;) {
      const t = this.peek();
      if (!t || closes(t) || (inIntegral && this.atDx())) return out;
      const op = this.operator(t);
      if (op) {
        this.pos += op.length;
        out += op.text(expectOperand);
        expectOperand = true;
        continue;
      }
      if (!expectOperand) throw new Unsupported("Two expressions are next to each other without an operator.");
      out += this.parseTerm(closes, inIntegral);
      expectOperand = false;
    }
  }

  private operator(t: Tok): { length: number; text: (unary: boolean) => string } | null {
    if (t.kind === "char") {
      if (t.value === "+") return { length: 1, text: (u) => (u ? "+" : " + ") };
      if (t.value === "-" || t.value === "−") return { length: 1, text: (u) => (u ? "-" : " - ") };
      if (t.value === "=") return { length: 1, text: () => " = " };
      if (t.value === ",") return { length: 1, text: () => ", " };
      if (t.value === "/") return { length: 1, text: () => "/" };
      if (t.value === "*") return { length: 1, text: () => " * " };
      return null;
    }
    if (t.kind === "cmd") {
      if (t.value === "pm" || t.value === "mp") return { length: 1, text: (u) => (u ? "±" : " ± ") };
      if (t.value === "div") return { length: 1, text: () => "/" };
      if ((t.value === "text" || t.value === "mathrm") && this.isWordGroup("or")) return { length: 5, text: () => " or " };
    }
    return null;
  }

  /** True when the next tokens are \text{word}. */
  private isWordGroup(word: string): boolean {
    if (!isChar(this.peek(1), "{")) return false;
    for (let i = 0; i < word.length; i++) if (!isLetter(this.peek(2 + i), word[i])) return false;
    return isChar(this.peek(2 + word.length), "}");
  }

  private parseTerm(closes: (t: Tok) => boolean, inIntegral: boolean): string {
    const factors: Factor[] = [];
    const explicit: boolean[] = [];
    let pendingStar = false;
    for (;;) {
      const t = this.peek();
      if (!t || closes(t) || this.operator(t) !== null || (inIntegral && this.atDx())) break;
      if (isCmd(t, "cdot") || isCmd(t, "times")) {
        if (factors.length === 0 || pendingStar) throw new Unsupported("A multiplication sign needs something before it.");
        this.pos++;
        pendingStar = true;
        continue;
      }
      factors.push(this.parseFactor(inIntegral));
      explicit.push(pendingStar);
      pendingStar = false;
    }
    if (pendingStar) throw new Unsupported("A multiplication sign needs something after it.");
    if (factors.length === 0) throw new Unsupported("Something is missing in the expression.");

    const wrap = factors.length > 1; // a fraction among other factors must be bracketed
    let out = "";
    factors.forEach((f, i) => {
      const piece = f.fraction && wrap ? parenthesise(f.text) : f.text;
      if (i > 0) {
        const star = explicit[i] || /^[0-9.]/.test(piece) || (/x$/.test(out) && /^x/.test(piece));
        const tight =
          (endsWithNumber(out) && /^[A-Za-z(]/.test(piece) && !FUNCTION_NAMES.test(piece)) || (out.endsWith(")") && piece.startsWith("("));
        out += star ? " * " : tight ? "" : " ";
      }
      out += piece;
    });
    return out;
  }

  // ------------------------------------------------------------------ factors

  private parseFactor(inIntegral: boolean): Factor {
    const base = this.parsePrimary(inIntegral);
    if (isChar(this.peek(), "_")) throw new Unsupported("Subscripts aren't supported.");
    if (!isChar(this.peek(), "^")) return base;
    this.pos++;
    const exponent = this.parseExponent();
    const baseText = base.fraction || !isSingleAtom(base.text) ? parenthesise(base.text) : base.text;
    return { text: `${baseText}^${exponent}` };
  }

  private parseExponent(): string {
    const t = this.peek();
    let text: string;
    if (isChar(t, "{")) {
      text = this.parseGroup();
    } else if (t?.kind === "num" || t?.kind === "letter") {
      this.pos++;
      text = t.value;
    } else if (isChar(t, "-") && (this.peek(1)?.kind === "num" || this.peek(1)?.kind === "letter")) {
      text = "-" + this.peek(1)!.value;
      this.pos += 2;
    } else {
      throw new Unsupported("This power isn't supported.");
    }
    return exponentText(text);
  }

  private expectChar(v: string): void {
    if (!isChar(this.next(), v)) throw new Unsupported("Brackets don't match.");
  }

  private parseGroup(): string {
    this.expectChar("{");
    const text = this.parseSum((t) => isChar(t, "}"));
    this.expectChar("}");
    return text;
  }

  /** After an opening bracket: parse up to the matching close (plain, \right, or a bar). */
  private parseBracketed(open: string): string {
    const close = open === "(" ? ")" : open === "[" ? "]" : "|";
    const text = this.parseSum((t) => isChar(t, close) || isCmd(t, "right") || isCmd(t, "rbrack") || (close === "|" && isCmd(t, "vert")));
    const end = this.next();
    if (isCmd(end, "right")) {
      const delimiter = this.next();
      const ok = delimiter.value === close || (close === "|" && delimiter.value === "vert") || (close === "]" && delimiter.value === "rbrack");
      if (!ok) throw new Unsupported("Brackets don't match.");
    } else if (!(isChar(end, close) || isCmd(end, "rbrack") || isCmd(end, "vert"))) {
      throw new Unsupported("Brackets don't match.");
    }
    return text;
  }

  private parsePrimary(inIntegral: boolean): Factor {
    const t = this.next();
    if (t.kind === "num" || t.kind === "letter") {
      if (isLetter(t, "d") && isLetter(this.peek(), "x") && !inIntegral) {
        throw new Unsupported("Write derivatives as a fraction d over dx.");
      }
      return { text: t.value };
    }
    if (t.kind === "char") {
      if (t.value === "(") return { text: parenthesise(this.parseBracketed("(")) };
      if (t.value === "[") return this.evaluatedBracket(this.parseBracketed("["));
      if (t.value === "|") return { text: `abs(${this.parseBracketed("|")})` };
      if (t.value === "{") {
        this.pos--;
        return { text: parenthesise(this.parseGroup()) };
      }
      if (t.value === ")" || t.value === "]" || t.value === "}") throw new Unsupported("Brackets don't match.");
      throw new Unsupported(`'${t.value}' isn't supported.`);
    }
    return this.parseCommand(t.value, inIntegral);
  }

  private evaluatedBracket(inner: string): Factor {
    let lower: string | null = null;
    let upper: string | null = null;
    while (isChar(this.peek(), "_") || isChar(this.peek(), "^")) {
      const which = this.next().value;
      const bound = this.parseBound();
      if (which === "_") lower = bound;
      else upper = bound;
    }
    if (lower === null || upper === null) throw new Unsupported("Square brackets must be followed by the limits, as [F]ₐᵇ.");
    return { text: `[${inner}][${lower}, ${upper}]` };
  }

  private parseBound(): string {
    return isChar(this.peek(), "{") ? this.parseGroup() : this.parseExponent();
  }

  private parseCommand(name: string, inIntegral: boolean): Factor {
    if (name === "left") {
      const d = this.next();
      if (d.value === "(") return { text: parenthesise(this.parseBracketed("(")) };
      if (d.value === "|" || d.value === "vert") return { text: `abs(${this.parseBracketed("|")})` };
      if (d.value === "[" || d.value === "lbrack") return this.evaluatedBracket(this.parseBracketed("["));
      throw new Unsupported("This kind of bracket isn't supported.");
    }
    if (name === "lbrack") return this.evaluatedBracket(this.parseBracketed("["));
    if (name === "vert") return { text: `abs(${this.parseBracketed("|")})` };
    if (name === "frac" || name === "dfrac" || name === "tfrac") return this.parseFraction(inIntegral);
    if (name === "sqrt") {
      if (isChar(this.peek(), "[")) throw new Unsupported("Only square roots are supported.");
      return { text: `sqrt(${this.parseGroup()})` };
    }
    if (name in SYMBOLS) return { text: SYMBOLS[name] };
    if (name === "int") return this.parseIntegral();
    if (name === "lim") return this.parseLimit();
    if (name in FUNCTIONS) return this.parseFunction(FUNCTIONS[name], inIntegral);
    if (name === "placeholder") throw new Unsupported("Fill in the empty box first.");
    if (name === "pm") throw new Unsupported("± needs a number or letter before it.");
    throw new Unsupported(`'\\${name}' isn't supported.`);
  }

  /** The tokens of the {group} starting at `at`, flattened to a string, and the index after it. */
  private scanGroup(at: number): { sig: string; end: number } | null {
    if (!isChar(this.toks[at], "{")) return null;
    let depth = 0;
    let sig = "";
    for (let i = at; i < this.toks.length; i++) {
      const t = this.toks[i];
      if (isChar(t, "{")) depth++;
      else if (isChar(t, "}") && --depth === 0) return { sig, end: i + 1 };
      else sig += t.value;
    }
    return null;
  }

  private parseFraction(inIntegral: boolean): Factor {
    const top = this.scanGroup(this.pos);
    const bottom = top ? this.scanGroup(top.end) : null;
    if (top?.sig === "d" && bottom?.sig === "dx") {
      this.pos = bottom.end;
      return { text: `d/dx${this.parseOperand(inIntegral)}` };
    }
    const numerator = this.parseGroup();
    const denominator = this.parseGroup();
    const above = isProduct(numerator) ? numerator : parenthesise(numerator);
    const below = isSingleAtom(denominator) ? denominator : parenthesise(denominator);
    return { text: `${above}/${below}`, fraction: true };
  }

  /** What an operator applies to: a bracketed group, or the next product. */
  private parseOperand(inIntegral: boolean): string {
    const t = this.peek();
    if (!t) throw new Unsupported("An operator is missing its argument.");
    const bracketed = isChar(t, "(") || (isCmd(t, "left") && isChar(this.peek(1), "("));
    const body = this.parseTerm(CLOSERS, inIntegral);
    if (bracketed && isSingleAtom(body) && body.startsWith("(")) return body;
    return parenthesise(body);
  }

  private parseFunction(name: string, inIntegral: boolean): Factor {
    let power = "";
    if (isChar(this.peek(), "^")) {
      this.pos++;
      power = `^${stripOuterParens(this.parseExponent())}`;
    }
    return { text: `${name}${power}${this.parseOperand(inIntegral)}` };
  }

  private parseIntegral(): Factor {
    let lower: string | null = null;
    let upper: string | null = null;
    while (isChar(this.peek(), "_") || isChar(this.peek(), "^")) {
      const which = this.next().value;
      const bound = this.parseBound();
      if (which === "_") lower = bound;
      else upper = bound;
    }
    if ((lower === null) !== (upper === null)) throw new Unsupported("A definite integral needs both limits.");
    const body = this.parseSum(CLOSERS, true);
    if (!this.atDx()) throw new Unsupported("End the integral with dx.");
    this.pos += 2;
    if (!body) throw new Unsupported("The integral has nothing to integrate.");
    const inner = stripOuterParens(body);
    return lower === null ? { text: `int(${inner}) dx` } : { text: `int[${lower}, ${upper}](${inner}) dx` };
  }

  private parseLimit(): Factor {
    if (!isChar(this.peek(), "_")) throw new Unsupported("A limit needs x → a under 'lim'.");
    this.pos++;
    this.expectChar("{");
    const variable = this.next();
    const arrow = this.next();
    if (variable.value !== "x" || !(isCmd(arrow, "to") || isCmd(arrow, "rightarrow"))) {
      throw new Unsupported("Write limits as x → a.");
    }
    const point = this.parseSum((t) => isChar(t, "}"));
    this.expectChar("}");
    const body = this.parseSum(CLOSERS);
    if (!point || !body) throw new Unsupported("A limit needs the point and the expression.");
    return { text: `lim(x->${point}, ${body})` };
  }
}

/** Convert the visual editor's LaTeX to StepCheck's text syntax. Never throws. */
export function latexToText(latex: string): Conversion {
  const trimmed = latex.trim();
  if (!trimmed) return { ok: true, text: "" };
  try {
    const parser = new Parser(tokenize(trimmed));
    const text = parser.parseSum(() => false).replace(/\s+/g, " ").trim();
    if (!parser.done()) throw new Unsupported("Brackets don't match.");
    return { ok: true, text };
  } catch (e) {
    if (e instanceof Unsupported) return { ok: false, reason: e.message };
    return { ok: false, reason: "This can't be checked yet." };
  }
}
