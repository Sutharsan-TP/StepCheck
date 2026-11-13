# StepCheck API contract

All endpoints are under `/api/v1`. Requests and responses are JSON.

## Errors

Every error response has the same shape:

```json
{ "error": { "code": "VERIFICATION_EXPIRED", "message": "…", "details": [] } }
```

| HTTP | `code` | When |
|---|---|---|
| 404 | `VERIFICATION_NOT_FOUND` | The `verification_id` is unknown. This includes ids lost in a server restart. |
| 410 | `VERIFICATION_EXPIRED` | The `verification_id` expired after 1 hour or was evicted because the store was full. |
| 422 | `INVALID_REQUEST` | The request didn't validate: a malformed UUID, an unknown field, a limit exceeded, or `progress` sent without a token. |
| 422 | `PROGRESS_TOKEN_INVALID` | `progress_token` doesn't match these steps and this progress. |
| 422 | `INVALID_PROGRESS` | `progress` failed re-verification on the server. |
| 422 | `CORRECTION_NOT_AVAILABLE` | `/correct` was called for a calculus problem. Corrections are algebra-only for now. |
| 400 | `INVALID_IMAGE`, `IMAGE_DIMENSIONS_UNSUPPORTED` | The upload is empty, corrupt, or smaller than 64 px or larger than 8000 px on a side. |
| 413 | `IMAGE_TOO_LARGE` | The upload is larger than 5 MB, or decodes to too many pixels. |
| 415 | `UNSUPPORTED_IMAGE_TYPE` | The file's contents aren't JPEG, PNG or WebP. The filename and declared type are ignored. |
| 429 | `RATE_LIMITED` | Too many requests from this client. A `Retry-After` header says how many seconds to wait. |
| 429 | `AI_RATE_LIMITED` | The AI provider is still rate-limiting after the server's retries. |
| 502 | `AI_PROVIDER_ERROR`, `AI_MALFORMED_RESPONSE` | The AI provider failed, timed out, or returned unusable output. |
| 503 | `AI_UNAVAILABLE` | No API key or model is configured, the credentials were rejected, or no model is available. |
| 500 | `INTERNAL_ERROR` | An unexpected server error. No internal details are included. |

### Rate limits

Each client IP has a per-endpoint token bucket. Defaults per minute: `/transcribe` 10, `/explain` 30, `/verify` 120, `/correct` 120. All four can be set through `RATE_LIMIT_*_PER_MINUTE`. Limits are kept in memory per server process. `X-Forwarded-For` is only used when `TRUST_PROXY=true`, reading the entry `TRUSTED_PROXY_HOPS` places from the right.

Requests that contain unknown fields are rejected. This means a client can't send its own correctness claims, such as `"status": "VALID"`.

Unsupported or unreadable math is **not** an HTTP error. `/verify` returns 200, and each step carries an `UNSUPPORTED` or `NEEDS_REVIEW` status.

## `GET /health`

Response: `{"status": "healthy", "service": "stepcheck-api"}`.

## `POST /verify`

Request:

```json
{
  "steps": ["2x + 5 = 15", "2x = 10", "x = 5"],
  "variable": "x",
  "domain": "REAL",
  "request_id": "optional"
}
```

Limits:
- 2 to 30 steps.
- At most 200 characters per step.

The response includes:

| Field | Meaning |
|---|---|
| `verification_id` | A UUID that identifies this verification. |
| `overall_status` | `CORRECT`, `INCORRECT`, `INCOMPLETE`, `UNSUPPORTED` or `NEEDS_REVIEW`. |
| `first_error_step` | The step number of the first incorrect step, if any. |
| `complete_answer_step` | The earliest step that states the complete answer, counted only if every step up to and including it is valid. |
| `steps[]` | Each step's status, its LaTeX, its normalized form and its solution set. |
| `transitions[]` | Each step-to-step check, with lost and extra solutions. |
| `correct_solution`, `submitted_solution`, `solution_complete`, `missing_solutions`, `extraneous_solutions` | Whether the final answer is correct and complete (equations). |
| `topic` | `ALGEBRA`, or a calculus topic: `DERIVATIVE`, `INTEGRAL`, `DEFINITE_INTEGRAL` or `LIMIT`. See [Calculus](#calculus). |
| `expected_answer`, `expected_answer_latex`, `missing_constant`, `notes` | Calculus only: the engine's own final answer, whether an indefinite integral lacks `+ C`, and remarks such as "equal for x > 0". |

### Calculus

The first line decides how the whole solution is read: if it uses `d/dx`, `int`, `∫` or `lim`, every step is checked by the calculus engine, otherwise by the equation engine.

| You write | Syntax | Also accepted |
|---|---|---|
| Derivative | `d/dx(x^2 sin(x))` | |
| Indefinite integral | `int(x^2) dx` | `∫ x^2 dx` |
| Definite integral | `int[0, 2](x^2) dx` | `∫[0, 2](x^2) dx` |
| Limit | `lim(x->0, sin(x)/x)` | `x→0` |
| Antiderivative evaluated between limits | `[x^3/3][0, 2]` | |
| Functions | `sin cos tan sec csc cot arcsin arccos arctan ln log exp abs sqrt`, always with brackets, and `sin^2(x)` | |
| Constants | `pi`, `e`, `oo` (infinity), `C` (the constant of integration) | `π`, `∞` |

A step may chain several expressions with `=`, for example `d/dx(sin(x^2)) = cos(x^2) d/dx(x^2)`.

How steps are judged:
- **Derivatives, definite integrals, limits.** A step must have the same value as the step before it, as a function of `x` or as a number. `FIRST_INVALID` is only reported when the engine finds a point where the values provably differ; that point is returned as `counterexample`.
- **Indefinite integrals.** A step must differ from the one before it by a constant only. StepCheck checks this by differentiating both, so no integration is needed to judge a step. A missing `+ C` in the final answer makes the result `INCOMPLETE`, with `missing_constant: true`.
- **Undecided steps.** If the engine can neither prove nor disprove equality, or a computation times out, the step is `NEEDS_REVIEW`. It is never guessed. Reason codes on `transitions[]`: `NOT_EQUAL`, `DIFFERS_BY_NON_CONSTANT`, `CANNOT_DECIDE`, `UNDEFINED` and `TIMEOUT`.
- **Evidence.** `transitions[]` also carry `expected_value_latex` and `found_value_latex`. For integrals these are the derivatives of the two sides.
- **Completeness.** The final line must contain no `d/dx`, `∫`, `lim` or `[F][a, b]`.
- **Limits of the service.** One variable `x`, the functions above, at most 4 calculus operators and 200 characters per step. Anything else comes back as `UNSUPPORTED` or `NEEDS_REVIEW`.

`/correct` is not available for calculus yet and returns `422 CORRECTION_NOT_AVAILABLE`. `/explain` works.

### Verification storage

- `/verify` stores the submitted steps and their result **in server memory**, keyed by `verification_id`.
- Each entry lives for **1 hour**.
- The store holds at most **1,000 entries**. When it's full, expired entries are removed first, then the oldest entries.
- **A server restart or redeploy clears all stored verifications.** Separate server instances don't share them either.
- Ids that were removed are reported as `VERIFICATION_EXPIRED`. Ids the server has never seen, including those lost in a restart, are reported as `VERIFICATION_NOT_FOUND`.
- Clients don't depend on storage: `/correct` also accepts the original steps directly.

## `POST /correct`

Request:

```json
{
  "verification_id": "uuid",
  "steps": ["…"],
  "variable": "x",
  "domain": "REAL",
  "mode": "GUIDED",
  "attempt": "2x = 10",
  "progress": ["…"],
  "progress_token": "…",
  "hint_level": 1
}
```

| Field | Rules |
|---|---|
| `verification_id` / `steps` | Send exactly one of the two. |
| `variable` / `domain` | Optional context. Only `"x"` and `"REAL"` are accepted. |
| `mode` | `"GUIDED"` or `"FULL"`. |
| `attempt` | GUIDED only. At most 200 characters. |
| `progress` | GUIDED only. At most 20 steps. Must be sent together with `progress_token`. |
| `progress_token` | GUIDED only. |
| `hint_level` | 1 to 3. |

Every correction step is checked by the same verifier that checks student work. A FULL correction is returned only if the whole corrected solution checks as `CORRECT` with a complete answer. If it doesn't, the response is `NEEDS_REVIEW` and no correction is suggested.

### FULL mode

`status` is one of `CORRECTED`, `COMPLETED`, `NO_CORRECTION_NEEDED` or `NEEDS_REVIEW`.

`full.action` says what the correction does:

| `action` | Meaning | What the response contains |
|---|---|---|
| `REPLACE_STEP` | A step was wrong. | `corrected_step` (the replacement for `original_step`) and `continuation`, the remaining steps. |
| `COMPLETE_SOLUTION` | Every step was valid, but the solution was unfinished. | `continuation`. |
| `REMOVE_REMAINING_STEPS` | The answer was already complete at `complete_answer_step`. | The complete solution unchanged, plus `removed_steps[]`. No replacement steps are made up. |
| `NONE` | Nothing to do. | — |

Each entry in `removed_steps[]` has a `kind`:
- `INCORRECT`: the step is wrong, or depends on a wrong step.
- `UNNECESSARY`: the step is valid but wasn't needed.
- `UNVERIFIABLE`: the step couldn't be checked.

Other fields:
- `corrected_solution[]`: the full solution. Each step's `source` is `STUDENT`, `CORRECTED` or `GENERATED`, and each step has an explanation.
- `final_solution`: the final answer.
- `verification`: the result of re-checking the corrected solution.
- `error_category`, `expected_rule`, `explanation` and `evidence`: what kind of mistake was made and why it is wrong.

Example of `REMOVE_REMAINING_STEPS`. The submitted steps are `2x + 5 = 15`, `2x = 10`, `x = 5`, `x = 10`. The response keeps steps 1–3 and lists step 4 as `INCORRECT`, with the message "already complete at step 3; remove step 4".

### GUIDED mode (stateless)

`status` is one of `NEEDS_ATTEMPT`, `ACCEPTED`, `REJECTED`, `NO_PROGRESS`, `ATTEMPT_UNREADABLE`, `SOLVED`, `ALREADY_COMPLETE`, `NO_CORRECTION_NEEDED` or `NEEDS_REVIEW`.

Hints:
- Levels 1 and 2 describe the idea and where to look, without giving the answer away.
- Level 3 sets `reveal_answer: true` and fills in `revealed_step`.

The server keeps **no session**. The guided loop works like this:

1. Send `{steps or verification_id, mode: "GUIDED"}`.
2. Send `attempt`, together with the `guided.progress` and `guided.progress_token` from the last response.
3. When an attempt is `ACCEPTED`, the next response's `guided.progress` includes that attempt, along with a new token. Send both back unchanged.
4. Repeat until the status is `SOLVED`.

On every request, the server:
- Re-checks the original steps and every progress step from the beginning. Each progress step must parse, must have the same solutions as the step before it, and must not repeat that step. No step may come after an answer that is already complete.
- Requires the HMAC `progress_token` to match these steps and this progress. This blocks progress the server never accepted and progress taken from a different solution.
- Ignores correctness claims from the client. Requests with unknown fields are rejected.

Tokens are signed with `PROGRESS_TOKEN_SECRET`. If that variable isn't set, a random secret is created when the server starts, so tokens stop working after a restart, just like stored verifications.

## `POST /transcribe`

Reads a photo of handwritten working. The request is `multipart/form-data` with a single field, `file`, which must be a JPEG, PNG or WebP of at most 5 MB.

The response always has `status: "REVIEW_REQUIRED"`. Transcription never triggers verification: the student must review the lines and confirm them, and the client then sends them to `/verify`.

```json
{
  "request_id": "uuid",
  "question": "2x + 5 = 15",
  "variable": "x",
  "status": "REVIEW_REQUIRED",
  "warnings": [],
  "image": { "width": 1400, "height": 600 },
  "steps": [
    {
      "step_number": 1,
      "expression": "2x + 5 = 15",
      "latex": "2 x + 5 = 15",
      "confidence": 0.97,
      "needs_review": false,
      "review_reasons": [],
      "parse_error_code": null
    }
  ]
}
```

The vision model is told to transcribe exactly: not to solve, correct, simplify, reorder or fill in steps. The server then checks every line itself:
- It runs each line through StepCheck's parser. A line that doesn't parse gets `needs_review` set, with the parser's message added to `review_reasons`.
- The LaTeX returned is the server's own rendering of the exact text.
- A line also needs review if its confidence is below 0.8 or the model flagged it as ambiguous.
- At most 30 lines are kept, and a variable other than `x` produces a warning.

## `POST /explain`

Request: `{"verification_id": "uuid"}` or `{"steps": [...]}`, with optional `variable` and `domain`. The client never sends a verification result. The server checks the steps itself every time.

Response:

| Field | Filled in by |
|---|---|
| `overall_status`, `first_error_step`, `error_category`, `expected_rule`, `corrected_step`, `suggested_next_step`, `correction_action` | Always the engine |
| `explanation`, `why_invalid`, `how_to_avoid`, `learning_tip` | The text model, or a deterministic template |
| `source` | Where the prose came from (see below) |
| `ai_status` | Why the template was used, when it was |

`source` is one of:
- `LLM`: AI-written prose that passed the server's checks.
- `TEMPLATE`: deterministic text, used when the AI is unavailable or its output was rejected. `ai_status` then holds a code such as `AI_UNAVAILABLE` or `REJECTED_BY_GUARD`.
- `ENGINE`: no AI was called at all. This happens for correct, unsupported or unverifiable work, and whenever no verified correction exists.

AI-written prose is rejected when it calls the work correct although the engine found a mistake, or when it contains a number that isn't in the verified facts.

For calculus, `error_category` names the rule that was misapplied, for example `PRODUCT_RULE_ERROR`, `CHAIN_RULE_ERROR`, `INTEGRAL_POWER_RULE_ERROR`, `LIMITS_SWAPPED` or `MISSING_CONSTANT`. `corrected_step`, `suggested_next_step` and `correction_action` are `null`. The engine finds the category by re-evaluating the last trusted step with one common wrong rule at a time and checking whether it reproduces the student's step; if none does, the category is `GENERAL_ERROR`.

## Offline AI stub (local demos and tests only)

`STEPCHECK_STUB_AI=true` replaces OpenRouter with a deterministic in-process stub.
- `/transcribe` recognises the bundled samples in `examples/handwritten_samples/` and returns their exact lines, with the last line flagged for review. Any other image comes back as unreadable.
- `/explain` restates the engine's facts as plain prose.

Never enable it in production.
