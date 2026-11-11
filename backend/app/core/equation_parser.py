"""Restricted equation parser.

Pipeline: raw text -> character whitelist + normalisation -> Lark LALR parse
-> validated intermediate representation (IR) -> SymPy objects built by hand.

Untrusted input never reaches ``eval``, ``sympify`` or ``parse_expr``. The only
identifiers accepted are the variable ``x`` and the function ``sqrt``; every
other construct is rejected with a structured :class:`MathInputError`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import product as cartesian

import sympy as sp
from lark import Lark, Token, Tree
from lark.exceptions import UnexpectedCharacters, UnexpectedInput, UnexpectedToken

from app.core.exact import is_zero, sign
from app.core.types import SolutionSet
from app.utils.errors import ErrorCode, MathInputError

X = sp.Symbol("x", real=True)
VARIABLE_NAME = "x"

MAX_INPUT_LENGTH = 200
MAX_NODES = 150
MAX_DEPTH = 20
MAX_NUMBER_DIGITS = 12
MAX_EXPONENT = 6
MAX_POWER_NESTING = 2
MAX_DEGREE_BOUND = 6
MAX_PLUS_MINUS = 2

_KNOWN_FUNCTIONS = {
    "sin", "cos", "tan", "sec", "csc", "cot", "arcsin", "arccos", "arctan",
    "sinh", "cosh", "tanh", "log", "ln", "lg", "exp", "abs", "floor", "ceil",
}

_GRAMMAR = r"""
    start: clause ((OR | COMMA) clause)*

    clause: sum EQUAL sum   -> equation
          | sum             -> bare

    ?sum: product
        | sum PLUS product   -> add
        | sum MINUS product  -> sub
        | sum PM product     -> addpm

    ?product: unary
        | product STAR unary   -> mul
        | product SLASH unary  -> div

    ?unary: implicit
        | MINUS unary  -> neg
        | PLUS unary   -> pos
        | PM unary     -> pm

    ?implicit: power
        | power jpower+  -> imul

    ?power: atom
        | atom CARET exponent  -> pow

    ?jpower: jatom
        | jatom CARET exponent  -> pow

    ?atom: NUMBER  -> number
        | jatom

    ?jatom: VAR                   -> var
        | NAME                    -> name
        | LPAR sum RPAR           -> paren
        | SQRT LPAR sum RPAR      -> sqrt_paren
        | ROOT atom               -> sqrt_bare

    exponent: NUMBER
        | MINUS NUMBER
        | LPAR NUMBER RPAR
        | LPAR MINUS NUMBER RPAR

    OR: "or"
    COMMA: ","
    EQUAL: "="
    PLUS: "+"
    MINUS: "-"
    PM: "±"
    STAR: "*"
    SLASH: "/"
    CARET: "^"
    LPAR: "("
    RPAR: ")"
    SQRT: "sqrt"
    ROOT: "√"
    VAR: "x"
    NAME: /[A-Za-z]+/
    NUMBER: /\d+(\.\d+)?|\.\d+/

    %ignore " "
"""

_PARSER = Lark(_GRAMMAR, parser="lalr", lexer="basic", maybe_placeholders=False)

_ALLOWED_CHARS = re.compile(r"^[0-9A-Za-z +\-*/^().,=±√]*$")
_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_SUPERSCRIPT_RUN = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+")

_EMPTY_LITERALS = {
    "no solution", "no solutions", "no real solution", "no real solutions",
    "no real roots", "∅", "{}", "x ∈ ∅", "x∈∅",
}
_ALL_REAL_LITERALS = {
    "all real numbers", "all reals", "all real x", "infinitely many solutions",
    "x ∈ ℝ", "x∈ℝ", "ℝ",
}


# --------------------------------------------------------------------------- IR


@dataclass
class Node:
    kind: str
    children: list["Node"] = field(default_factory=list)
    value: str | None = None  # number literal, identifier, or exponent text

    def contains_var(self) -> bool:
        if self.kind == "var":
            return True
        return any(c.contains_var() for c in self.children)

    def unwrap(self) -> "Node":
        node = self
        while node.kind == "paren":
            node = node.children[0]
        return node


@dataclass
class Clause:
    lhs: Node
    rhs: Node


@dataclass
class ParsedStatement:
    """A step: either a disjunction of equations or an explicit solution-set literal."""

    text: str
    clauses: list[Clause] = field(default_factory=list)
    literal: SolutionSet | None = None

    @property
    def latex(self) -> str:
        if self.literal is not None:
            return r"x \in \mathbb{R}" if self.literal.kind.value == "ALL_REAL" else r"\varnothing"
        return r" \quad\text{or}\quad ".join(
            f"{to_latex(c.lhs)} = {to_latex(c.rhs)}" for c in self.clauses
        )

    @property
    def solved_form(self) -> bool:
        """True when the step states solutions explicitly (x = c, c = x, or constant truth)."""
        if self.literal is not None:
            return True
        for c in self.clauses:
            lhs, rhs = c.lhs.unwrap(), c.rhs.unwrap()
            if lhs.kind == "var" and not rhs.contains_var():
                continue
            if rhs.kind == "var" and not lhs.contains_var():
                continue
            if not lhs.contains_var() and not rhs.contains_var():
                continue
            return False
        return True


# ---------------------------------------------------------------- preprocessing


def preprocess(raw: str) -> str:
    if raw is None or not raw.strip():
        raise MathInputError(ErrorCode.EMPTY_INPUT, "The step is empty.")
    if len(raw) > MAX_INPUT_LENGTH:
        raise MathInputError(
            ErrorCode.INPUT_TOO_LONG, f"A step may contain at most {MAX_INPUT_LENGTH} characters."
        )
    text = raw.strip()
    for dash in ("−", "–", "—", "‐", "‑"):
        text = text.replace(dash, "-")
    for times in ("×", "·", "∙", "⋅"):
        text = text.replace(times, "*")
    text = text.replace("÷", "/").replace("**", "^").replace("+/-", "±").replace("∓", "±")
    text = _SUPERSCRIPT_RUN.sub(lambda m: "^" + m.group(0).translate(_SUPERSCRIPTS), text)
    text = re.sub(r"\s+", " ", text)
    return text


def _match_literal(text: str) -> SolutionSet | None:
    key = text.lower().rstrip(".").strip()
    if key in _EMPTY_LITERALS:
        return SolutionSet.empty()
    if key in _ALL_REAL_LITERALS:
        return SolutionSet.all_real()
    return None


# ---------------------------------------------------------------------- parsing


def parse_statement(raw: str) -> ParsedStatement:
    """Parse one step into a validated IR. Raises MathInputError on any problem."""
    text = preprocess(raw)
    literal = _match_literal(text)
    if literal is not None:
        return ParsedStatement(text=text, literal=literal)

    if not _ALLOWED_CHARS.match(text):
        bad = sorted({ch for ch in text if not _ALLOWED_CHARS.match(ch)})
        raise MathInputError(
            ErrorCode.INVALID_CHARACTER,
            f"Unsupported character(s): {' '.join(repr(b) for b in bad)}.",
        )
    if re.search(r"\band\b", text, flags=re.IGNORECASE):
        raise MathInputError(
            ErrorCode.UNSUPPORTED_CONNECTIVE,
            "Use 'or' to list several solutions (for example 'x = 2 or x = 3').",
        )
    if "==" in text:
        raise MathInputError(ErrorCode.SYNTAX_ERROR, "Use a single '=' sign.")

    try:
        tree = _PARSER.parse(text)
    except UnexpectedInput as exc:
        raise _syntax_error(exc, text) from None

    counter = _Counter()
    clauses: list[Clause] = []
    for child in tree.children:
        if isinstance(child, Token):
            continue  # separator
        if child.data == "equation":
            lhs = _to_ir(child.children[0], counter, 1)
            rhs = _to_ir(child.children[2], counter, 1)
            clauses.append(Clause(lhs, rhs))
        else:  # bare value, only allowed as "x = 2 or 3" shorthand
            value = _to_ir(child.children[0], counter, 1)
            if not clauses:
                raise MathInputError(
                    ErrorCode.MISSING_EQUALS, "Each step must be an equation containing '='."
                )
            prev = clauses[-1]
            if prev.lhs.unwrap().kind != "var" or prev.rhs.contains_var() or value.contains_var():
                raise MathInputError(
                    ErrorCode.AMBIGUOUS_EXPRESSION,
                    "A bare value can only follow 'x = value' (for example 'x = 2 or 3').",
                )
            clauses.append(Clause(Node("var", value=VARIABLE_NAME), value))
    return ParsedStatement(text=text, clauses=clauses)


def _syntax_error(exc: UnexpectedInput, text: str) -> MathInputError:
    column = getattr(exc, "column", None)
    where = f" near position {column}" if isinstance(column, int) and column > 0 else ""
    if isinstance(exc, UnexpectedToken):
        tok = exc.token
        clauses = re.split(r",|\bor\b", text)
        if tok.type == "EQUAL" and any(c.count("=") > 1 for c in clauses):
            return MathInputError(
                ErrorCode.CHAINED_EQUALS, "Write one equation per step (only one '=' per equation)."
            )
        if tok.type == "$END":
            return MathInputError(ErrorCode.SYNTAX_ERROR, "The expression ends unexpectedly.")
        if tok.type == "NUMBER":
            return MathInputError(
                ErrorCode.SYNTAX_ERROR,
                f"Unexpected number '{tok}'{where}. Use '*' for multiplication or '^' for powers.",
            )
        return MathInputError(ErrorCode.SYNTAX_ERROR, f"Unexpected '{tok}'{where}.")
    if isinstance(exc, UnexpectedCharacters):
        return MathInputError(ErrorCode.SYNTAX_ERROR, f"Unexpected character{where}.")
    return MathInputError(ErrorCode.SYNTAX_ERROR, "The expression could not be read.")


class _Counter:
    def __init__(self) -> None:
        self.nodes = 0
        self.plus_minus = 0

    def bump(self, depth: int) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise MathInputError(ErrorCode.TOO_COMPLEX, "The expression is too long to verify.")
        if depth > MAX_DEPTH:
            raise MathInputError(ErrorCode.TOO_COMPLEX, "The expression is nested too deeply.")


_BINARY = {"add", "sub", "addpm", "mul", "div"}
_UNARY = {"neg", "pos", "pm"}


def _to_ir(tree: Tree | Token, counter: _Counter, depth: int) -> Node:
    counter.bump(depth)
    kind = tree.data
    kids = [c for c in tree.children]

    if kind == "number":
        literal = str(kids[0])
        int_part, _, frac_part = literal.partition(".")
        if len(int_part) > MAX_NUMBER_DIGITS or len(frac_part) > MAX_NUMBER_DIGITS:
            raise MathInputError(ErrorCode.TOO_COMPLEX, f"The number {literal} is too large.")
        return Node("num", value=literal)
    if kind == "var":
        return Node("var", value=VARIABLE_NAME)
    if kind == "name":
        raise _identifier_error(str(kids[0]))
    if kind == "paren":
        return Node("paren", [_to_ir(kids[1], counter, depth + 1)])
    if kind == "sqrt_paren":
        return Node("sqrt", [_to_ir(kids[2], counter, depth + 1)], value="paren")
    if kind == "sqrt_bare":
        arg = _to_ir(kids[1], counter, depth + 1)
        # "√(3)" is delimited; only "√3" can swallow a following factor ambiguously.
        return Node("sqrt", [arg], value="paren" if arg.kind == "paren" else "bare")
    if kind in _BINARY:
        left = _to_ir(kids[0], counter, depth + 1)
        right = _to_ir(kids[2], counter, depth + 1)
        if kind == "addpm":
            _count_pm(counter)
        if kind == "div" and right.kind == "imul":
            raise MathInputError(
                ErrorCode.AMBIGUOUS_EXPRESSION,
                "Ambiguous division such as '1/2x': add parentheses, e.g. '(1/2)x' or '1/(2x)'.",
            )
        return Node(kind, [left, right])
    if kind in _UNARY:
        if kind == "pm":
            _count_pm(counter)
        return Node(kind, [_to_ir(kids[1], counter, depth + 1)])
    if kind == "imul":
        factors = [_to_ir(k, counter, depth + 1) for k in kids]
        for f in factors[:-1]:
            if f.kind == "sqrt" and f.value == "bare":
                raise MathInputError(
                    ErrorCode.AMBIGUOUS_EXPRESSION,
                    "Ambiguous square root: use parentheses, e.g. '√(3)x' or '√(3x)'.",
                )
        names = [f.unwrap().kind for f in factors]
        if names.count("var") > 1 and all(n == "var" for n in names):
            raise MathInputError(
                ErrorCode.AMBIGUOUS_EXPRESSION, "Write 'x^2' or 'x*x' instead of 'xx'."
            )
        return Node("imul", factors)
    if kind == "pow":
        base = _to_ir(kids[0], counter, depth + 1)
        exponent = _exponent(kids[2])
        node = Node("pow", [base], value=str(exponent))
        if _power_nesting(node) > MAX_POWER_NESTING:
            raise MathInputError(ErrorCode.NESTED_POWER, "Nested powers are not supported.")
        return node
    raise MathInputError(ErrorCode.SYNTAX_ERROR, "The expression could not be read.")


def _count_pm(counter: _Counter) -> None:
    counter.plus_minus += 1
    if counter.plus_minus > MAX_PLUS_MINUS:
        raise MathInputError(ErrorCode.TOO_COMPLEX, "Too many '±' signs in one step.")


def _identifier_error(name: str) -> MathInputError:
    lower = name.lower()
    if name == "X":
        return MathInputError(
            ErrorCode.UNKNOWN_IDENTIFIER, "Use a lowercase 'x' for the variable."
        )
    if lower in _KNOWN_FUNCTIONS:
        return MathInputError(
            ErrorCode.UNSUPPORTED_FUNCTION, f"The function '{name}' is not supported."
        )
    if lower == "sqrt":
        return MathInputError(ErrorCode.SYNTAX_ERROR, "Write square roots as sqrt(...).")
    if len(name) == 1 or (set(name) - {"x"} and "x" in name):
        return MathInputError(
            ErrorCode.MULTIPLE_VARIABLES,
            f"Only the variable x is supported (found '{name}').",
        )
    if set(name) == {"x"}:
        return MathInputError(
            ErrorCode.AMBIGUOUS_EXPRESSION, "Write 'x^2' or 'x*x' instead of 'xx'."
        )
    return MathInputError(ErrorCode.UNKNOWN_IDENTIFIER, f"Unknown name '{name}'.")


def _exponent(tree: Tree) -> int:
    tokens = [str(t) for t in tree.children if isinstance(t, Token) and t.type in ("NUMBER", "MINUS")]
    negative = "-" in tokens
    number = tokens[-1]
    if "." in number:
        frac = Fraction(number)
        if frac.denominator != 1:
            raise MathInputError(ErrorCode.NON_INTEGER_EXPONENT, "Exponents must be whole numbers.")
    if len(number.split(".")[0]) > 3:
        raise MathInputError(ErrorCode.EXPONENT_TOO_LARGE, "The exponent is too large.")
    value = int(Fraction(number))
    if negative and value != 0:
        raise MathInputError(ErrorCode.NEGATIVE_EXPONENT, "Negative exponents are not supported.")
    if value > MAX_EXPONENT:
        raise MathInputError(
            ErrorCode.EXPONENT_TOO_LARGE, f"Exponents larger than {MAX_EXPONENT} are not supported."
        )
    return value


def _power_nesting(node: Node) -> int:
    inner = max((_power_nesting(c) for c in node.children), default=0)
    return inner + (1 if node.kind == "pow" else 0)


# ------------------------------------------------------------------------ LaTeX


def to_latex(node: Node) -> str:
    k = node.kind
    c = node.children
    if k == "num":
        return node.value or ""
    if k == "var":
        return "x"
    if k == "paren":
        return rf"\left({to_latex(c[0])}\right)"
    if k == "sqrt":
        return rf"\sqrt{{{to_latex(c[0].unwrap())}}}"
    if k == "add":
        return f"{to_latex(c[0])} + {to_latex(c[1])}"
    if k == "sub":
        return f"{to_latex(c[0])} - {to_latex(c[1])}"
    if k == "addpm":
        return rf"{to_latex(c[0])} \pm {to_latex(c[1])}"
    if k == "mul":
        return rf"{to_latex(c[0])} \cdot {to_latex(c[1])}"
    if k == "div":
        return rf"\frac{{{to_latex(c[0].unwrap())}}}{{{to_latex(c[1].unwrap())}}}"
    if k == "neg":
        return f"-{to_latex(c[0])}"
    if k == "pos":
        return f"+{to_latex(c[0])}"
    if k == "pm":
        return rf"\pm {to_latex(c[0])}"
    if k == "pow":
        return f"{{{to_latex(c[0])}}}^{{{node.value}}}"
    if k == "imul":
        return " ".join(to_latex(f) for f in c)
    return ""


def to_text(node: Node) -> str:
    """Plain-text rendering of the IR in the student's own form (re-parseable)."""
    k = node.kind
    c = node.children
    if k == "num":
        return node.value or ""
    if k == "var":
        return "x"
    if k == "paren":
        return f"({to_text(c[0])})"
    if k == "sqrt":
        return f"sqrt({to_text(c[0].unwrap())})"
    if k == "add":
        return f"{to_text(c[0])} + {to_text(c[1])}"
    if k == "sub":
        return f"{to_text(c[0])} - {to_text(c[1])}"
    if k == "addpm":
        return f"{to_text(c[0])} ± {to_text(c[1])}"
    if k == "mul":
        return f"{to_text(c[0])} * {to_text(c[1])}"
    if k == "div":
        return f"{to_text(c[0])}/{to_text(c[1])}"
    if k == "neg":
        return f"-{to_text(c[0])}"
    if k == "pos":
        return f"+{to_text(c[0])}"
    if k == "pm":
        return f"±{to_text(c[0])}"
    if k == "pow":
        return f"{to_text(c[0])}^{node.value}"
    if k == "imul":
        return "".join(to_text(f) for f in c)
    return ""


def node_to_sympy(node: Node) -> sp.Expr:
    """Exact SymPy value of a ±-free IR node (validated like any other input)."""
    values = _to_sympy(node)
    if len(values) != 1:
        raise MathInputError(ErrorCode.AMBIGUOUS_EXPRESSION, "Unexpected '±' in this expression.")
    return values[0]


def has_plus_minus(node: Node) -> bool:
    return node.kind in ("pm", "addpm") or any(has_plus_minus(ch) for ch in node.children)


# ---------------------------------------------------------- IR -> SymPy (exact)


def clause_equations(clause: Clause) -> list[tuple[sp.Expr, sp.Expr]]:
    """Convert a clause to one or more exact (lhs, rhs) SymPy pairs (± expands to branches)."""
    for side in (clause.lhs, clause.rhs):
        if _degree_bound(side) > MAX_DEGREE_BOUND:
            raise MathInputError(
                ErrorCode.DEGREE_TOO_HIGH, "Only linear and quadratic equations are supported."
            )
    lhs_branches = _to_sympy(clause.lhs)
    rhs_branches = _to_sympy(clause.rhs)
    return [(lhs, rhs) for lhs, rhs in cartesian(lhs_branches, rhs_branches)]


def _degree_bound(node: Node) -> int:
    k = node.kind
    if k == "num" or k == "sqrt":
        return 0
    if k == "var":
        return 1
    if k in ("mul", "imul"):
        return sum(_degree_bound(c) for c in node.children)
    if k == "div":
        return _degree_bound(node.children[0])
    if k == "pow":
        return _degree_bound(node.children[0]) * int(node.value or 0)
    return max((_degree_bound(c) for c in node.children), default=0)


def _to_sympy(node: Node) -> list[sp.Expr]:
    k = node.kind
    c = node.children
    if k == "num":
        return [sp.Rational(node.value)]
    if k == "var":
        return [X]
    if k in ("paren", "pos"):
        return _to_sympy(c[0])
    if k == "neg":
        return [-v for v in _to_sympy(c[0])]
    if k == "pm":
        vals = _to_sympy(c[0])
        return [s * v for v in vals for s in (1, -1)]
    if k == "add":
        return [a + b for a, b in cartesian(_to_sympy(c[0]), _to_sympy(c[1]))]
    if k == "sub":
        return [a - b for a, b in cartesian(_to_sympy(c[0]), _to_sympy(c[1]))]
    if k == "addpm":
        return [
            r for a, b in cartesian(_to_sympy(c[0]), _to_sympy(c[1])) for r in (a + b, a - b)
        ]
    if k == "mul":
        return [a * b for a, b in cartesian(_to_sympy(c[0]), _to_sympy(c[1]))]
    if k == "imul":
        results: list[sp.Expr] = [sp.Integer(1)]
        for f in c:
            results = [r * v for r, v in cartesian(results, _to_sympy(f))]
        return results
    if k == "div":
        if c[1].contains_var():
            raise MathInputError(
                ErrorCode.DIVISION_BY_VARIABLE,
                "Dividing by an expression containing x is not supported.",
            )
        out = []
        for a, b in cartesian(_to_sympy(c[0]), _to_sympy(c[1])):
            if is_zero(b):
                raise MathInputError(ErrorCode.DIVISION_BY_ZERO, "Division by zero.")
            out.append(a / b)
        return out
    if k == "pow":
        n = int(node.value or 0)
        return [sp.expand(v**n) if v.free_symbols else v**n for v in _to_sympy(c[0])]
    if k == "sqrt":
        if c[0].contains_var():
            raise MathInputError(
                ErrorCode.RADICAL_OF_VARIABLE, "Square roots of expressions containing x are not supported."
            )
        out = []
        for v in _to_sympy(c[0]):
            if sign(v) < 0:
                raise MathInputError(
                    ErrorCode.COMPLEX_VALUE,
                    "The square root of a negative number is not a real number.",
                )
            out.append(sp.sqrt(v))
        return out
    raise MathInputError(ErrorCode.SYNTAX_ERROR, "The expression could not be read.")
