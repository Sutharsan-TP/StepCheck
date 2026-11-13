# StepCheck architecture

StepCheck checks a student's equation-solving work line by line, finds the first step that is wrong, and helps the student fix it. Its main design rule:

> **A deterministic symbolic engine decides what is mathematically correct.** Language models only read handwriting and phrase explanations. Neither the AI nor the browser can override what the engine decided.

## Components

```
 Browser (Next.js 16, React 19)                      FastAPI backend (Python 3.12)
 ┌─────────────────────────────┐   JSON / multipart   ┌───────────────────────────────────────────┐
 │ /            landing        │ ───────────────────▶ │ /api/v1/verify     ─▶ core (math engine)  │
 │ /workspace   type or upload │                      │ /api/v1/correct    ─▶ core (corrections)  │
 │   ↳ transcription review    │ ◀─────────────────── │ /api/v1/transcribe ─▶ image + vision AI   │
 │ /results     timeline +     │                      │ /api/v1/explain    ─▶ core + text AI      │
 │   explain / guide / correct │                      │ rate limiting · in-memory verification store│
 │   / compare                 │                      └──────────────┬────────────────────────────┘
 └─────────────────────────────┘                                     │ HTTPS (key kept on the server)
                                                                     ▼
                                                               OpenRouter (vision + text models)
```

### Backend (`backend/app`)

| Layer | Modules | Responsibility |
|---|---|---|
| `core/` (no AI, no HTTP) | `equation_parser`, `polynomial_validator`, `solution_solver`, `equivalence_checker`, `first_error_detector`, `exact` | Parse steps with a restricted grammar and turn each into an exact real solution set. Compare consecutive sets, locate the first error, and check whether the final answer is complete. |
| | `step_generator`, `diagnosis`, `correction_engine`, `forms`, `rendering` | Name the kind of mistake. Repair the first invalid step and generate the rest of the solution. Every generated step is checked again by the same engine. |
| `core/calculus/` | `calc_parser`, `calc_equivalence`, `calc_verifier`, `calc_diagnosis`, `sandbox`, with `core/checking.py` as the single entry point | The same job for derivatives, integrals and limits. A step is judged by its value, or for indefinite integrals by its derivative. SymPy runs in a separate worker process that is killed if it overruns its time limit. |
| `services/` | `openrouter_client`, `vision_service`, `explanation_service`, `image_service`, `rate_limiter`, `verification_store`, `progress_token`, `stub_ai` | Calls to the AI provider, image safety, rate limiting, storage and signed tokens. |
| `api/` | `routes/*`, `schemas/*` (Pydantic) | The HTTP contract. Every error has the same shape: `{"error": {"code", "message"}}`. |

### Frontend (`frontend/src`)

- `lib/api-schema.ts` is generated from the backend's OpenAPI schema (`npm run gen:api`). `npm run check:api` fails if it has fallen behind the backend.
- `lib/api.ts` is a typed client. If a stored verification has expired or was lost in a restart, it resends the steps instead.
- `lib/session.ts` keeps the current work in `sessionStorage` so it survives a refresh. It reads it in a way that avoids hydration errors.
- `components/editor` has two ways to enter maths, which the student can switch between and which is remembered on their device (`lib/preferences.ts`):
  - **Keypad:** a text box with a calculator-style keypad (`lib/keypad.ts`). Keys insert templates such as `d/dx(|)` and place the caret inside them.
  - **Visual editor:** MathLive, loaded only when chosen. `lib/latex-to-text.ts` converts its LaTeX to the text syntax with a strict whitelist and refuses anything it doesn't recognise.
  Both produce the same text, and the backend parses that text again itself.
- `components/upload`, and `components/verification` hold the screens: the timeline, the explanation, guided, correction and compare panels.

## How a step is judged

1. **Parse.** Each step is first checked against a character allow-list and size limits, then parsed with a Lark LALR grammar into an intermediate representation (IR). The IR is validated — only `x` and `sqrt` are allowed, there are limits on nesting and exponents, and division by `x` is rejected. SymPy objects are then built by hand from it. `eval`, `sympify` and `parse_expr` are never called.
2. **Normalize.** The equation is rewritten as `LHS − RHS = 0`. It must be a polynomial in `x` of degree at most 2, with real coefficients.
3. **Solve exactly.** The result is a solution set: `ALL_REAL`, `EMPTY`, or a finite set of exact values (fractions and square roots). Whether two values are equal is decided exactly, with `minimal_polynomial`, never by floating-point comparison.
4. **Compare.** A step is valid only if its solution set is exactly the solution set of the step before it. The first step that changes the set is `FIRST_INVALID`, and every later step is `DOWNSTREAM_DEPENDENT`.
5. **Completeness** is checked separately. A step is a *complete answer* when it states its solutions explicitly (for example `x = 2 or x = 3`) and they are exactly the original problem's solutions. The verifier, the completeness checker and the correction engine all use this same definition (`is_complete_answer`).

If a step is unsupported or unreadable, StepCheck reports `UNSUPPORTED` or `NEEDS_REVIEW` and does not guess.

### Calculus

Calculus follows the same pipeline with a second grammar (`calc_parser`) and a different notion of equality:

1. **Parse** with a separate restricted grammar: a whitelist of functions, limits on size, nesting, exponents and the number of operators. Operators stay unevaluated, so the verifier can see what is left to do.
2. **Compare** consecutive steps. *Equal* is only claimed when SymPy proves the difference is zero. *Unequal* is only claimed when high-precision evaluation at a sample point, where both sides are real and finite, gives a clearly non-zero difference, and that point is kept as the counterexample. Anything else is `NEEDS_REVIEW`.
3. **Indefinite integrals** are compared through their derivatives: if `d/dx` of the difference is zero, the steps differ by a constant. `+ C` is checked separately in the final answer.
4. **Diagnose** the mistake by re-evaluating the last trusted step with one common wrong rule at a time (product rule as f′g′, chain rule without the inner derivative, and so on). If a wrong rule reproduces the student's step, that rule is named; otherwise the category is `GENERAL_ERROR`. The verdict never depends on this step.

**Why a separate process.** Some inputs make SymPy run for minutes and a thread cannot be stopped. Every calculus computation runs in a worker process (`core/calculus/sandbox.py`) with a hard limit of about 4 s per comparison and 15 s per request. On overrun the worker is killed and replaced and the step is `NEEDS_REVIEW`. Start-up of a worker is not counted against those limits. The server starts the worker when it boots. It is one process; it measured about 60 MB on Windows after loading SymPy and running a few jobs, and will be somewhat larger on Linux.

## Trust boundaries

| Source | Trusted for | Never trusted for |
|---|---|---|
| Symbolic engine | Whether the maths is correct | — |
| Vision model | A first draft of what was written | Anything that hasn't been checked. Every line is parsed again, low-confidence or unreadable lines are flagged, and the student must confirm before anything is verified. |
| Text model | Wording | Status, error category, corrected step, next step (all filled in by the engine). Its text is discarded if it calls the work correct when it isn't, or contains a number that isn't in the verified facts. |
| Browser | Showing results | Correctness. Requests with unknown fields such as `status` are rejected. Guided-correction progress is checked again on every request and must carry a server-signed HMAC token. |

## Safety and reliability

- **Uploads.** Files are limited to 5 MB and handled entirely in memory. The format is detected from the file's bytes, and only JPEG, PNG and WebP are accepted. Image dimensions are limited and decompression bombs are rejected. Images are re-encoded to strip EXIF data. Nothing is written to disk or logged.
- **AI calls.** The OpenRouter client uses structured JSON output and retries with backoff on 429, 5xx and timeouts. It switches to a fallback model if the main model is unavailable, and retries once if the output is malformed. Every failure becomes a structured error (429, 502 or 503). The API key is never logged or returned to the browser.
- **If the AI is down.** Explanations fall back to deterministic templates. Transcription returns `AI_UNAVAILABLE`.
- **Rate limits.** Each endpoint has a per-client token bucket, with a `Retry-After` header on 429. `X-Forwarded-For` is only trusted when `TRUST_PROXY=true`, and then only the entry added by the outermost trusted proxy (`TRUSTED_PROXY_HOPS` from the right); entries the client sent itself are ignored.
- **Storage.** Verification results are kept in memory for 1 hour, up to 1,000 entries. Expired entries are evicted first, then the oldest. A server restart clears them, so `/correct` and `/explain` also accept the steps directly.
- **Internal errors.** Unexpected exceptions are logged on the server and returned as `INTERNAL_ERROR` without a stack trace.

## Testing

- **Backend** (pytest, no network): the parser, the solver, equivalence checks, first-error detection, 32 curated algebra cases and 41 curated calculus cases, the calculus parser, equality checker, sandbox (including killing a runaway job), diagnosis and explanations, the correction engine (including "follow every hint until solved" walkthroughs), consistency between the engines, storage, tokens, rate limits, the AI client, and the transcription and explanation services, all against mocked transports.
- **Frontend unit and component tests** (Vitest and Testing Library): use fixtures recorded from the real backend.
- **End to end** (Playwright): runs the real backend with `STEPCHECK_STUB_AI=true`, a deterministic offline stand-in for OpenRouter, and drives every demo flow in Chromium.
