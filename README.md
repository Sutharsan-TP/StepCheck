# StepCheck

StepCheck checks each step of a student's equation-solving work. It finds the first step that is wrong, shows which later steps rely on that mistake, and reports whether the final answer includes every solution.

Correctness is decided by a deterministic symbolic engine (SymPy + a restricted Lark grammar). AI is used only to transcribe handwriting and to write explanations. It never decides whether a step is correct.

## Status

- **Milestone 1 (math engine + `/verify` API): done**
- Milestone 2 (OpenRouter transcription and explanations): not started
- Milestone 3 (Next.js frontend): not started
- Milestone 4 (deployment): not started

## Supported mathematics

- Equations in a single variable `x`, solved over the real numbers.
- Linear and quadratic equations with integer, rational or decimal coefficients. Decimals are treated as exact fractions.
- Square roots of constants, `±`, factored forms, and answers written as `x = a or x = b`.
- Steps written as `no solution` or `all real numbers`.

Anything outside this scope returns `UNSUPPORTED` or `NEEDS_REVIEW` and never a guessed answer. That includes higher-degree equations, other variables, functions, division by `x`, and square roots of expressions containing `x`.

## How verification works

1. Each step is parsed with a restricted grammar. The parser never uses `eval`, `sympify` or `parse_expr`.
2. Each step is rewritten as `LHS − RHS = 0`, checked to have degree at most 2, and solved exactly. Its solution set is `ALL_REAL`, `EMPTY`, or a finite set of exact values.
3. A step is valid only if its solution set equals the solution set of the previous step. The first step that changes the solution set is marked `FIRST_INVALID`, and every step after it is `DOWNSTREAM_DEPENDENT`.
4. A separate check decides whether the final line states the full solution set of the original equation.

## Running the backend (Windows)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

- Health check: `GET http://localhost:8000/api/v1/health`
- Verification: `POST http://localhost:8000/api/v1/verify`, for example with `{"steps": ["2x + 5 = 15", "2x = 10", "x = 5"]}`
- Curated examples: `examples/`
