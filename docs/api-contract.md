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
| 500 | `INTERNAL_ERROR` | An unexpected server error. No internal details are included. |

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
| `correct_solution`, `submitted_solution`, `solution_complete`, `missing_solutions`, `extraneous_solutions` | Whether the final answer is correct and complete. |

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
