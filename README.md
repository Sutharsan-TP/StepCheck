# StepCheck

StepCheck checks each line of a student's algebra or calculus working. It finds the first step that is wrong, explains why it's invalid, and helps the student fix it — by guiding them with hints, or by showing a fully verified correction.

> **Design rule:** a deterministic symbolic engine (SymPy and a restricted grammar) decides what is mathematically correct. AI only reads handwriting and helps phrase explanations, and it can never change a verdict.

| Area | Status |
|---|---|
| Math engine: first-error detection and answer completeness | Done |
| Correction engine (FULL and GUIDED modes) | Done, for algebra |
| Calculus: derivatives, integrals, definite integrals and limits | Done: checking, mistake diagnosis and explanations. Corrections are not available yet. |
| Entering maths: keypad or visual editor, switchable | Done |
| AI: handwriting transcription and explanations through OpenRouter | Done, tested with mocks. Needs a key to run against real models. |
| Frontend: landing page, workspace, transcription review, results, corrections | Done |
| Deployment (Render and Vercel) | Configured: [`render.yaml`](render.yaml) and [docs/deployment.md](docs/deployment.md) |

## What it supports

- One variable, `x`, over the real numbers.
- Linear and quadratic equations: expanding, combining like terms, doing the same operation to both sides, factoring, the quadratic formula (`±`), and the square-root property.
- Exact answers, including fractions and square roots.
- Equations that hold for every `x`, and equations with no real solution.

Anything else returns `UNSUPPORTED` or `NEEDS_REVIEW` and is never guessed. That includes cubics, other variables, trigonometry in equations, logarithms in equations, inequalities, dividing by an expression with `x` in it, and square roots of `x`.

### Calculus

If the first line uses a calculus operator, the whole solution is checked as calculus:

- **Derivatives**, `d/dx(x^2 sin(x))`: every step must have the same value as the one before.
- **Indefinite integrals**, `int(2x) dx`: steps may differ by a constant, and the final answer needs `+ C`.
- **Definite integrals**, `int[0, 2](x^2) dx`, with `[x^3/3][0, 2]` for evaluating between limits.
- **Limits**, `lim(x->0, sin(x)/x)`, including L'Hôpital steps.

The functions are `sin cos tan sec csc cot arcsin arccos arctan ln log exp abs sqrt`, and the constants are `pi`, `e` and `oo`. StepCheck names the rule that was misapplied (product, quotient or chain rule, a swapped limit, a missing `+ C`, and so on). If it can neither prove nor disprove that two steps are equal, or a computation takes too long, the step is `NEEDS_REVIEW`, never a guess. Guided hints and corrected solutions are algebra-only for now.

### Entering maths

The workspace has two input modes, switchable at any time and remembered on this device:

- **Keypad:** a text box with a calculator-style keypad (Basic, Functions and Calculus pages) and a live preview.
- **Visual editor:** real fractions, powers and integral signs, with an on-screen keyboard that has a calculus page.

## Repository layout

```
backend/    FastAPI + SymPy + Lark. app/core is the math engine (no AI); app/services holds AI, images, limits and storage.
frontend/   Next.js 16 + React 19 + Tailwind 4 + KaTeX.
examples/   Curated solutions (also used by the tests) and synthetic handwritten samples.
scripts/    generate_samples.py, which creates the synthetic handwriting images.
docs/       architecture.md, api-contract.md, demo.md
```

## Running locally

You need Python 3.12 and Node.js 22 or 24 (LTS).

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env          # optional: edit settings
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

API docs are at http://localhost:8000/docs.

### Frontend

```powershell
cd frontend
npm install
copy .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                          # http://localhost:3000
```

### Demo without an API key

Start the backend with the offline AI stub, which never makes a network call:

```powershell
$env:STEPCHECK_STUB_AI="true"; .venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Then upload any image from `examples/handwritten_samples/` on the **Upload photo** tab.

## Configuration (`backend/.env`)

| Variable | Purpose |
|---|---|
| `CORS_ORIGINS`, `CORS_ORIGIN_REGEX` | Comma-separated frontend origins (default `http://localhost:3000`), plus an optional pattern for extra origins such as Vercel preview URLs. |
| `OPENROUTER_API_KEY` | Needed for real transcription and AI explanations. Kept on the backend only. |
| `OPENROUTER_VISION_MODEL`, `OPENROUTER_TEXT_MODEL`, `OPENROUTER_FALLBACK_MODEL` | Model names. None are hardcoded. Use models you've tested for JSON output, and for images in the vision model. |
| `OPENROUTER_TIMEOUT_SECONDS`, `OPENROUTER_MAX_RETRIES` | AI call timeout and number of retries. |
| `PROGRESS_TOKEN_SECRET` | Signs guided-correction progress. Set a long random value. If it's unset, a new secret is generated at startup and progress tokens stop working after a restart. |
| `CALC_JOB_TIMEOUT_SECONDS`, `CALC_WORKERS` | Time limit for one calculus comparison (default 4) and the number of calculus worker processes (default 1). |
| `RATE_LIMIT_*_PER_MINUTE`, `TRUST_PROXY`, `TRUSTED_PROXY_HOPS` | Per-client rate limits; whether to trust `X-Forwarded-For`, and how many proxies sit in front of the app (Render: 2). |
| `STEPCHECK_STUB_AI` | `true` only for local demos and tests. |

**What needs an OpenRouter key:**
- `/transcribe`: without a key it returns `503 AI_UNAVAILABLE`.
- AI-written explanations: without a key, `/explain` falls back to deterministic template text.

Verification and corrections never need a key. Once a key is set, check the configured models with:

```powershell
cd backend; .venv\Scripts\python scripts\smoke_openrouter.py   # makes real, billable requests
```

**Storage:** verification results are kept in server memory for 1 hour, up to 1,000 entries. A restart clears them. The frontend handles this by resending the steps.

## Tests

```powershell
cd backend;  .venv\Scripts\python -m pytest     # math engine, corrections, AI services (mocked), API
cd frontend; npm run check:api                  # generated types match the backend's OpenAPI schema
cd frontend; npm run lint; npm run typecheck; npm run test
cd frontend; npx playwright install chromium; npm run e2e   # real backend + offline AI stub, in Chromium
```

None of the automated tests call a real AI service.

## More

- [docs/architecture.md](docs/architecture.md): components, how a step is judged, trust boundaries, safety measures.
- [docs/api-contract.md](docs/api-contract.md): endpoints, error codes, the guided-correction protocol, storage.
- [docs/demo.md](docs/demo.md): a demo script under three minutes.
- [docs/deployment.md](docs/deployment.md): deploying to Render and Vercel, and checking the live site.
