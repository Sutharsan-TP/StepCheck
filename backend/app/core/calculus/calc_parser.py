"""Restricted parser for calculus steps.

Same safety model as ``equation_parser``: raw text -> character whitelist and
normalisation -> Lark LALR parse -> validated IR -> SymPy objects built by hand.
Untrusted input never reaches ``eval``, ``sympify`` or ``parse_expr``.

A step is one expression, or several joined by '=' (each must equal the rest of
the chain). Operators stay unevaluated so the verifier can see what is left to do:

    d/dx(x^2 sin(x))          derivative
    int(x^2) dx, ∫ x^2 dx     indefinite integral
    int[0, 2](x^2) dx         definite integral
    lim(x->0, sin(x)/x)       limit
    [x^3/3][0, 2]             evaluated antiderivative, F(2) - F(0)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

import sympy as sp
from lark import Lark, Token, Tree
from lark.exceptions import UnexpectedCharacters, UnexpectedInput, UnexpectedToken

from app.core.equation_parser import MAX_DEPTH, MAX_NODES, MAX_NUMBER_DIGITS, X, Node, _identifier_error, preprocess
from app.utils.errors import ErrorCode, MathInputError

C = sp.Symbol("C", real=True)  # the constant of integration

MAX_OPERATORS = 4  # calculus operators per step
MAX_INTEGER_EXPONENT = 20
MAX_FUNCTION_POWER = 6
MAX_POWER_NESTING = 3


class Topic(str, Enum):
    DERIVATIVE = "DERIVATIVE"
    INTEGRAL = "INTEGRAL"
    DEFINITE_INTEGRAL = "DEFINITE_INTEGRAL"
    LIMIT = "LIMIT"


_GRAMMAR = r"""
    start: sum (EQUAL sum)*

    ?sum: product
        | sum PLUS product   -> add
        | sum MINUS product  -> sub

    ?product: unary
        | product STAR unary   -> mul
        | product SLASH unary  -> div

    ?unary: implicit
        | MINUS unary  -> neg
        | PLUS unary   -> pos

    ?implicit: power
        | power jpower+  -> imul

    ?power: atom
        | atom CARET exponent  -> pow

    ?jpower: jatom
        | jatom CARET exponent  -> pow

    ?exponent: atom
        | MINUS atom  -> neg

    ?atom: NUMBER  -> number
        | jatom

    ?jatom: VAR                                         -> var
        | CONST                                         -> const
        | NAME                                          -> name
        | LPAR sum RPAR                                 -> paren
        | FUNC LPAR sum RPAR                            -> func
        | FUNC CARET NUMBER LPAR sum RPAR               -> funcpow
        | SQRT LPAR sum RPAR                            -> sqrt
        | DDX LPAR sum RPAR                             -> deriv
        | INT sum DX                                    -> integral
        | INT LSQB sum COMMA sum RSQB sum DX            -> defint
        | LIM LPAR VAR ARROW sum COMMA sum RPAR         -> limit
        | LSQB sum RSQB LSQB sum COMMA sum RSQB         -> evalat

    EQUAL: "="
    PLUS: "+"
    MINUS: "-"
    STAR: "*"
    SLASH: "/"
    CARET: "^"
    LPAR: "("
    RPAR: ")"
    LSQB: "["
    RSQB: "]"
    COMMA: ","
    ARROW.6: "->"
    DDX.6: "d/dx"
    DX.5: /dx\b/
    INT.5: /int\b/
    LIM.5: /lim\b/
    SQRT.5: "sqrt"
    FUNC.4: /(arcsin|arccos|arctan|asin|acos|atan|sin|cos|tan|sec|csc|cot|ln|log|exp|abs)(?![a-wyzA-Z])/
    CONST.3: /pi|oo|e|C/
    VAR.2: "x"
    NAME: /[A-Za-z]+/
    NUMBER: /\d+(\.\d+)?|\.\d+/

    %ignore " "
"""

_PARSER = Lark(_GRAMMAR, parser="lalr", lexer="basic", maybe_placeholders=False)

_ALLOWED_CHARS = re.compile(r"^[0-9A-Za-z +\-*/^().,=\[\]>]*$")
_TOPIC_HINT = re.compile(r"d/dx|∫|\bint\s*[\[(]|\bint\b.*\bdx\b|\blim\s*\(")
_OPERATOR_KINDS = {"deriv": Topic.DERIVATIVE, "integral": Topic.INTEGRAL, "defint": Topic.DEFINITE_INTEGRAL, "limit": Topic.LIMIT}

_FUNCTIONS = {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "sec": sp.sec, "csc": sp.csc, "cot": sp.cot,
    "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
    "arcsin": sp.asin, "arccos": sp.acos, "arctan": sp.atan,
    "ln": sp.log, "log": lambda a: sp.log(a, 10), "exp": sp.exp, "abs": sp.Abs,
}
_CANONICAL_FUNCTION = {"arcsin": "asin", "arccos": "acos", "arctan": "atan"}
_CONSTANTS = {"pi": sp.pi, "e": sp.E, "oo": sp.oo, "C": C}


def looks_like_calculus(raw: str) -> bool:
    """Cheap routing check: does this problem line use a calculus operator?"""
    return bool(_TOPIC_HINT.search(raw or ""))


def guess_topic(raw: str) -> Topic:
    """Best guess for a problem line that could not be parsed (used only for labelling)."""
    text = raw or ""
    if "d/dx" in text:
        return Topic.DERIVATIVE
    if re.search(r"\blim\b", text):
        return Topic.LIMIT
    if re.search(r"(∫|\bint)\s*\[", text):
        return Topic.DEFINITE_INTEGRAL
    return Topic.INTEGRAL


# --------------------------------------------------------------------------- IR


@dataclass
class CalcStatement:
    """One step: a chain of expressions that should all be equal."""

    text: str
    links: list[Node] = field(default_factory=list)

    @property
    def latex(self) -> str:
        return " = ".join(to_latex(n) for n in self.links)

    @property
    def topic(self) -> Topic | None:
        for link in self.links:
            found = _first_operator(link)
            if found is not None:
                return found
        return None

    @property
    def evaluated(self) -> bool:
        """True when the last expression has no derivative, integral, limit or [F][a, b] left."""
        return not _has_operator(self.links[-1])

    @property
    def has_constant(self) -> bool:
        return _mentions_constant(self.links[-1])

    def expressions(self) -> list[sp.Expr]:
        return [node_to_sympy(n) for n in self.links]


def _first_operator(node: Node) -> Topic | None:
    if node.kind in _OPERATOR_KINDS:
        return _OPERATOR_KINDS[node.kind]
    for child in node.children:
        found = _first_operator(child)
        if found is not None:
            return found
    return None


def _has_operator(node: Node) -> bool:
    return node.kind in _OPERATOR_KINDS or node.kind == "evalat" or any(_has_operator(c) for c in node.children)


def _mentions_constant(node: Node) -> bool:
    return (node.kind == "const" and node.value == "C") or any(_mentions_constant(c) for c in node.children)


# ---------------------------------------------------------------- preprocessing


def preprocess_calculus(raw: str) -> str:
    text = preprocess(raw)
    text = text.replace("∫", " int ").replace("→", "->").replace("∞", "oo").replace("π", "pi")
    text = text.replace("√", "sqrt")
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------- parsing


def parse_calculus(raw: str) -> CalcStatement:
    """Parse one calculus step into a validated IR. Raises MathInputError on any problem."""
    text = preprocess_calculus(raw)
    if not _ALLOWED_CHARS.match(text):
        bad = sorted({ch for ch in text if not _ALLOWED_CHARS.match(ch)})
        raise MathInputError(
            ErrorCode.INVALID_CHARACTER, f"Unsupported character(s): {' '.join(repr(b) for b in bad)}."
        )
    if "==" in text:
        raise MathInputError(ErrorCode.SYNTAX_ERROR, "Use a single '=' between expressions.")
    try:
        tree = _PARSER.parse(text)
    except UnexpectedInput as exc:
        raise _syntax_error(exc) from None

    counter = _Counter()
    links = [_to_ir(child, counter, 1) for child in tree.children if not isinstance(child, Token)]
    statement = CalcStatement(text=text, links=links)
    for link in links:
        _validate(link, inside_bound=False)
    statement.expressions()  # build once so value errors (e.g. division by zero) surface now
    return statement


def _syntax_error(exc: UnexpectedInput) -> MathInputError:
    column = getattr(exc, "column", None)
    where = f" near position {column}" if isinstance(column, int) and column > 0 else ""
    if isinstance(exc, UnexpectedToken):
        tok = exc.token
        if tok.type == "NAME":
            return _identifier_error(str(tok))
        if tok.type == "$END":
            if "DX" in exc.accepts:
                return MathInputError(ErrorCode.SYNTAX_ERROR, "End the integral with 'dx', e.g. int(x^2) dx.")
            return MathInputError(ErrorCode.SYNTAX_ERROR, "The expression ends unexpectedly.")
        if tok.type == "VAR" and exc.state is not None and "LPAR" in exc.accepts:
            return MathInputError(
                ErrorCode.SYNTAX_ERROR, f"Put the function's argument in parentheses{where}, e.g. sin(x)."
            )
        return MathInputError(ErrorCode.SYNTAX_ERROR, f"Unexpected '{tok}'{where}.")
    if isinstance(exc, UnexpectedCharacters):
        return MathInputError(ErrorCode.SYNTAX_ERROR, f"Unexpected character{where}.")
    return MathInputError(ErrorCode.SYNTAX_ERROR, "The expression could not be read.")


class _Counter:
    def __init__(self) -> None:
        self.nodes = 0
        self.operators = 0

    def bump(self, depth: int) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise MathInputError(ErrorCode.TOO_COMPLEX, "The expression is too long to verify.")
        if depth > MAX_DEPTH:
            raise MathInputError(ErrorCode.TOO_COMPLEX, "The expression is nested too deeply.")

    def operator(self) -> None:
        self.operators += 1
        if self.operators > MAX_OPERATORS:
            raise MathInputError(ErrorCode.TOO_COMPLEX, "Too many derivatives, integrals or limits in one step.")


_BINARY = {"add", "sub", "mul", "div"}
_UNARY = {"neg", "pos"}


def _subtrees(tree: Tree) -> list[Tree]:
    return [c for c in tree.children if not isinstance(c, Token)]


def _to_ir(tree: Tree, counter: _Counter, depth: int) -> Node:
    counter.bump(depth)
    kind = tree.data
    kids = tree.children
    sub = [_to_ir(t, counter, depth + 1) for t in _subtrees(tree)] if kind not in ("number", "funcpow") else []

    if kind == "number":
        literal = str(kids[0])
        int_part, _, frac_part = literal.partition(".")
        if len(int_part) > MAX_NUMBER_DIGITS or len(frac_part) > MAX_NUMBER_DIGITS:
            raise MathInputError(ErrorCode.TOO_COMPLEX, f"The number {literal} is too large.")
        return Node("num", value=literal)
    if kind == "var":
        return Node("var", value="x")
    if kind == "const":
        return Node("const", value=str(kids[0]))
    if kind == "name":
        raise _identifier_error(str(kids[0]))
    if kind in ("paren", "sqrt") or kind in _UNARY:
        return Node(kind, sub)
    if kind == "div" and sub[1].kind == "imul":
        raise MathInputError(
            ErrorCode.AMBIGUOUS_EXPRESSION,
            "Ambiguous division such as '1/2x': add parentheses or '*', e.g. '(1/2)x', '1/2 * x' or '1/(2x)'.",
        )
    if kind in _BINARY or kind == "imul":
        return Node(kind, sub)
    if kind == "pow":
        node = Node("pow", sub)
        if _power_nesting(node) > MAX_POWER_NESTING:
            raise MathInputError(ErrorCode.NESTED_POWER, "Powers are nested too deeply.")
        return node
    if kind == "func":
        name = str(kids[0])
        return Node("func", sub, value=_CANONICAL_FUNCTION.get(name, name))
    if kind == "funcpow":
        name, power = str(kids[0]), str(kids[2])
        if "." in power or int(power) > MAX_FUNCTION_POWER:
            raise MathInputError(
                ErrorCode.EXPONENT_TOO_LARGE, f"Write powers of functions as whole numbers up to {MAX_FUNCTION_POWER}."
            )
        arg = _to_ir(kids[4], counter, depth + 1)
        func = Node("func", [arg], value=_CANONICAL_FUNCTION.get(name, name))
        return Node("pow", [func, Node("num", value=power)])
    if kind in ("deriv", "integral", "defint", "limit", "evalat"):
        counter.operator()
        if kind == "limit":
            # The VAR token is the limit variable: only x is supported.
            return Node("limit", sub)
        return Node(kind, sub)
    raise MathInputError(ErrorCode.SYNTAX_ERROR, "The expression could not be read.")


def _power_nesting(node: Node) -> int:
    inner = max((_power_nesting(c) for c in node.children), default=0)
    return inner + (1 if node.kind == "pow" else 0)


def _contains_x(node: Node) -> bool:
    return node.kind == "var" or any(_contains_x(c) for c in node.children)


def _small_constant(node: Node) -> bool:
    """Numbers up to MAX_INTEGER_EXPONENT, pi and e, combined with + - * / and sqrt (no powers)."""
    k = node.kind
    if k == "num":
        return float(node.value) <= MAX_INTEGER_EXPONENT
    if k == "const":
        return node.value in ("pi", "e")
    if k in ("paren", "neg", "pos", "sqrt", "add", "sub", "mul", "imul", "div"):
        return all(_small_constant(c) for c in node.children)
    return False


def _validate(node: Node, inside_bound: bool) -> None:
    """Semantic checks the grammar cannot express."""
    k = node.kind
    if k == "pow" and not _contains_x(node.children[1]) and not _small_constant(node.children[1]):
        # Constant exponents are built eagerly by SymPy, so 9^(9^9) would hang the server.
        raise MathInputError(
            ErrorCode.EXPONENT_TOO_LARGE,
            f"Constant exponents must be simple numbers no larger than {MAX_INTEGER_EXPONENT}.",
        )
    if k == "defint":
        lower, upper, _ = node.children
        if _contains_x(lower) or _contains_x(upper):
            raise MathInputError(ErrorCode.AMBIGUOUS_EXPRESSION, "Integration limits cannot contain x.")
    if k == "evalat":
        _, lower, upper = node.children
        if _contains_x(lower) or _contains_x(upper):
            raise MathInputError(ErrorCode.AMBIGUOUS_EXPRESSION, "Evaluation limits cannot contain x.")
    if k == "limit":
        point = node.children[0]
        if _contains_x(point):
            raise MathInputError(ErrorCode.AMBIGUOUS_EXPRESSION, "The limit point cannot contain x.")
    if k == "const" and node.value == "C" and inside_bound:
        raise MathInputError(ErrorCode.AMBIGUOUS_EXPRESSION, "C cannot appear in a limit or bound.")
    bound_children = {"defint": (0, 1), "evalat": (1, 2), "limit": (0,)}.get(k, ())
    for i, child in enumerate(node.children):
        _validate(child, inside_bound or i in bound_children)


# ------------------------------------------------------------------ IR -> SymPy


def node_to_sympy(node: Node) -> sp.Expr:
    """Exact SymPy object for a validated IR node. Calculus operators stay unevaluated."""
    k = node.kind
    c = node.children
    if k == "num":
        return sp.Rational(node.value)
    if k == "var":
        return X
    if k == "const":
        return _CONSTANTS[node.value]
    if k in ("paren", "pos"):
        return node_to_sympy(c[0])
    if k == "neg":
        return -node_to_sympy(c[0])
    if k == "add":
        return node_to_sympy(c[0]) + node_to_sympy(c[1])
    if k == "sub":
        return node_to_sympy(c[0]) - node_to_sympy(c[1])
    if k == "mul":
        return node_to_sympy(c[0]) * node_to_sympy(c[1])
    if k == "imul":
        out: sp.Expr = sp.Integer(1)
        for f in c:
            out = out * node_to_sympy(f)
        return out
    if k == "div":
        denominator = node_to_sympy(c[1])
        if denominator == 0:
            raise MathInputError(ErrorCode.DIVISION_BY_ZERO, "Division by zero.")
        return node_to_sympy(c[0]) / denominator
    if k == "pow":
        return node_to_sympy(c[0]) ** node_to_sympy(c[1])
    if k == "sqrt":
        return sp.sqrt(node_to_sympy(c[0]))
    if k == "func":
        return _FUNCTIONS[node.value](node_to_sympy(c[0]))
    if k == "deriv":
        return sp.Derivative(node_to_sympy(c[0]), X)
    if k == "integral":
        return sp.Integral(node_to_sympy(c[0]), X)
    if k == "defint":
        return sp.Integral(node_to_sympy(c[2]), (X, node_to_sympy(c[0]), node_to_sympy(c[1])))
    if k == "limit":
        point = node_to_sympy(c[0])
        body = node_to_sympy(c[1])
        if point in (sp.oo, -sp.oo):
            return sp.Limit(body, X, point)
        return sp.Limit(body, X, point, dir="+-")
    if k == "evalat":
        antiderivative = node_to_sympy(c[0])
        lower, upper = node_to_sympy(c[1]), node_to_sympy(c[2])
        return antiderivative.subs(X, upper) - antiderivative.subs(X, lower)
    raise MathInputError(ErrorCode.SYNTAX_ERROR, "The expression could not be read.")


# ------------------------------------------------------------------------ LaTeX


_FUNCTION_LATEX = {
    "sin": r"\sin", "cos": r"\cos", "tan": r"\tan", "sec": r"\sec", "csc": r"\csc", "cot": r"\cot",
    "asin": r"\arcsin", "acos": r"\arccos", "atan": r"\arctan", "ln": r"\ln", "log": r"\log_{10}",
    "exp": r"\exp",
}
_CONST_LATEX = {"pi": r"\pi", "e": "e", "oo": r"\infty", "C": "C"}


def to_latex(node: Node) -> str:
    k = node.kind
    c = node.children
    if k == "num":
        return node.value or ""
    if k == "var":
        return "x"
    if k == "const":
        return _CONST_LATEX[node.value]
    if k == "paren":
        return rf"\left({to_latex(c[0])}\right)"
    if k == "add":
        return f"{to_latex(c[0])} + {to_latex(c[1])}"
    if k == "sub":
        return f"{to_latex(c[0])} - {to_latex(c[1])}"
    if k == "mul":
        return rf"{to_latex(c[0])} \cdot {to_latex(c[1])}"
    if k == "imul":
        return " ".join(to_latex(f) for f in c)
    if k == "div":
        return rf"\frac{{{to_latex(c[0].unwrap())}}}{{{to_latex(c[1].unwrap())}}}"
    if k == "neg":
        return f"-{to_latex(c[0])}"
    if k == "pos":
        return f"+{to_latex(c[0])}"
    if k == "pow":
        base, exponent = c
        if base.kind == "func" and exponent.kind == "num":
            return rf"{_FUNCTION_LATEX.get(base.value, base.value)}^{{{exponent.value}}}\left({to_latex(base.children[0])}\right)"
        return f"{{{to_latex(base)}}}^{{{to_latex(exponent.unwrap())}}}"
    if k == "sqrt":
        return rf"\sqrt{{{to_latex(c[0].unwrap())}}}"
    if k == "func":
        if node.value == "abs":
            return rf"\left|{to_latex(c[0].unwrap())}\right|"
        return rf"{_FUNCTION_LATEX[node.value]}\left({to_latex(c[0].unwrap())}\right)"
    if k == "deriv":
        return rf"\frac{{d}}{{dx}}\left({to_latex(c[0].unwrap())}\right)"
    if k == "integral":
        return rf"\int {_integrand_latex(c[0])} \, dx"
    if k == "defint":
        return rf"\int_{{{to_latex(c[0])}}}^{{{to_latex(c[1])}}} {_integrand_latex(c[2])} \, dx"
    if k == "limit":
        return rf"\lim_{{x \to {to_latex(c[0])}}} {to_latex(c[1])}"
    if k == "evalat":
        return rf"\left[{to_latex(c[0].unwrap())}\right]_{{{to_latex(c[1])}}}^{{{to_latex(c[2])}}}"
    return ""


def _integrand_latex(node: Node) -> str:
    """Keep parentheses only around sums, e.g. (x^2 + 1) dx but x dx."""
    inner = node.unwrap()
    if inner.kind in ("add", "sub"):
        return rf"\left({to_latex(inner)}\right)"
    return to_latex(inner)


def to_text(node: Node) -> str:
    """Plain-text rendering of the IR (re-parseable by ``parse_calculus``)."""
    k = node.kind
    c = node.children
    if k in ("num", "const"):
        return node.value or ""
    if k == "var":
        return "x"
    if k == "paren":
        return f"({to_text(c[0])})"
    if k == "add":
        return f"{to_text(c[0])} + {to_text(c[1])}"
    if k == "sub":
        return f"{to_text(c[0])} - {to_text(c[1])}"
    if k == "mul":
        return f"{to_text(c[0])} * {to_text(c[1])}"
    if k == "imul":
        return " ".join(to_text(f) for f in c)
    if k == "div":
        return f"{to_text(c[0])}/{to_text(c[1])}"
    if k == "neg":
        return f"-{to_text(c[0])}"
    if k == "pos":
        return f"+{to_text(c[0])}"
    if k == "pow":
        return f"{to_text(c[0])}^{to_text(c[1])}"
    if k == "sqrt":
        return f"sqrt({to_text(c[0].unwrap())})"
    if k == "func":
        return f"{node.value}({to_text(c[0].unwrap())})"
    if k == "deriv":
        return f"d/dx({to_text(c[0].unwrap())})"
    if k == "integral":
        return f"int({to_text(c[0].unwrap())}) dx"
    if k == "defint":
        return f"int[{to_text(c[0])}, {to_text(c[1])}]({to_text(c[2].unwrap())}) dx"
    if k == "limit":
        return f"lim(x->{to_text(c[0])}, {to_text(c[1])})"
    if k == "evalat":
        return f"[{to_text(c[0].unwrap())}][{to_text(c[1])}, {to_text(c[2])}]"
    return ""
