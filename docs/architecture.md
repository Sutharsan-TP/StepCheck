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
| `services/` | `openrouter_client`, `vision_service`, `explanation_service`, `image_service`, `rate_limiter`, `verification_store`, `progress_token`, `stub_ai` | Calls to the AI provider, image safety, rate limiting, storage and signed tokens. |
| `api/` | `routes/*`, `schemas/*` (Pydantic) | The HTTP contract. Every error has the same shape: `{"error": {"code", "message"}}`. |

### Frontend (`frontend/src`)

- `lib/api-schema.ts` is generated from the backend's OpenAPI schema (`npm run gen:api`). `npm run check:api` fails if it has fallen behind the backend.
- `lib/api.ts` is a typed client. If a stored verification has expired or was lost in a restart, it resends the steps instead.
- `lib/session.ts` keeps the current work in `sessionStorage` so it survives a refresh. It reads it in a way that avoids hydration errors.
- `components/editor`, `components/upload`, and `components/verification` hold the screens: the timeline, the explanation, guided, correction and compare panels.

## How a step is judged

1. **Parse.** Each step is first checked against a character allow-list and size limits, then parsed with a Lark LALR grammar into an intermediate representation (IR). The IR is validated — only `x` and `sqrt` are allowed, there are limits on nesting and exponents, and division by `x` is rejected. SymPy objects are then built by hand from it. `eval`, `sympify` and `parse_expr` are never called.
2. **Normalize.** The equation is rewritten as `LHS − RHS = 0`. It must be a polynomial in `x` of degree at most 2, with real coefficients.
3. **Solve exactly.** The result is a solution set: `ALL_REAL`, `EMPTY`, or a finite set of exact values (fractions and square roots). Whether two values are equal is decided exactly, with `minimal_polynomial`, never by floating-point comparison.
4. **Compare.** A step is valid only if its solution set is exactly the solution set of the step before it. The first step that changes the set is `FIRST_INVALID`, and every later step is `DOWNSTREAM_DEPENDENT`.
5. **Completeness** is checked separately. A step is a *complete answer* when it states its solutions explicitly (for example `x = 2 or x = 3`) and they are exactly the original problem's solutions. The verifier, the completeness checker and the correction engine all use this same definition (`is_complete_answer`).

If a step is unsupported or unreadable, StepCheck reports `UNSUPPORTED` or `NEEDS_REVIEW` and does not guess.

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

- **Backend** (pytest, no network): the parser, the solver, equivalence checks, first-error detection, 32 curated cases, the correction engine (including "follow every hint until solved" walkthroughs), consistency between the engines, storage, tokens, rate limits, the AI client, and the transcription and explanation services, all against mocked transports.
- **Frontend unit and component tests** (Vitest and Testing Library): use fixtures recorded from the real backend.
- **End to end** (Playwright): runs the real backend with `STEPCHECK_STUB_AI=true`, a deterministic offline stand-in for OpenRouter, and drives every demo flow in Chromium.
