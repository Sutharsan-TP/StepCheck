"use client";

import { CheckCircle2, Eye, HelpCircle, Loader2, Send, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { MathText } from "@/components/math/MathText";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { correct, describeError, type WorkRef } from "@/lib/api";
import { textToLatex } from "@/lib/math-renderer";
import type { CorrectResponse } from "@/lib/types";
import { cn, MAX_STEP_LENGTH } from "@/lib/utils";

import { categoryLabel, solutionSetLatex } from "./format";

type Feedback = { tone: "success" | "error" | "warning"; title: string; body?: string | null };

/**
 * Interactive guided correction. The server keeps no session: every request sends the
 * accepted `progress` and its signed `progress_token` exactly as the server returned them,
 * and the server re-verifies all of it. Nothing here decides correctness.
 */
export function GuidedPanel({ work }: { work: WorkRef }) {
  const [response, setResponse] = useState<CorrectResponse | null>(null);
  const [hintLevel, setHintLevel] = useState(1);
  const [attempt, setAttempt] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const guided = response?.guided;
  const progress = guided?.progress ?? [];
  const token = guided?.progress_token;

  async function send(options: { attempt?: string; hint_level: number }) {
    setBusy(true);
    setError(null);
    try {
      const next = await correct(work, {
        mode: "GUIDED",
        hint_level: options.hint_level,
        attempt: options.attempt,
        progress,
        progress_token: progress.length ? token : undefined,
      });
      return next;
    } catch (e) {
      setError(describeError(e));
      return null;
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    let ignore = false;
    correct(work, { mode: "GUIDED", hint_level: 1 })
      .then((first) => !ignore && setResponse(first))
      .catch((e) => !ignore && setError(describeError(e)))
      .finally(() => !ignore && setBusy(false));
    return () => {
      ignore = true;
    };
  }, [work]);

  async function moreHelp() {
    const level = Math.min(3, hintLevel + 1);
    const next = await send({ hint_level: level });
    if (next) {
      setHintLevel(level);
      setResponse(next);
    }
  }

  async function submit() {
    const text = attempt.trim();
    if (!text) return;
    const next = await send({ attempt: text, hint_level: hintLevel });
    if (!next) return;
    const fb = next.guided?.attempt_feedback;
    switch (next.status) {
      case "ACCEPTED":
        setFeedback({ tone: "success", title: "Correct!", body: "That step is valid. Keep going." });
        setAttempt("");
        setHintLevel(1);
        break;
      case "SOLVED":
        setFeedback({ tone: "success", title: "Solved!", body: next.message });
        setAttempt("");
        break;
      case "REJECTED":
        setFeedback({ tone: "error", title: "Not quite", body: fb?.message ?? next.message });
        break;
      case "NO_PROGRESS":
        setFeedback({ tone: "warning", title: "That's the same equation", body: "It's valid, but it doesn't move the solution forward." });
        break;
      case "ATTEMPT_UNREADABLE":
        setFeedback({ tone: "warning", title: "StepCheck couldn't read that", body: fb?.message ?? next.message });
        break;
      default:
        setFeedback({ tone: "warning", title: next.message });
    }
    setResponse(next);
  }

  if (!response) {
    return busy ? (
      <p className="flex items-center gap-2 text-sm text-muted" role="status">
        <Loader2 className="size-4 animate-spin" aria-hidden /> Preparing guided correction…
      </p>
    ) : (
      <Alert tone="error" title="Guided correction is unavailable">
        {error}
      </Alert>
    );
  }

  const status = response.status;
  if (status === "NO_CORRECTION_NEEDED" || status === "NEEDS_REVIEW" || status === "ALREADY_COMPLETE") {
    return (
      <div className="flex flex-col gap-3">
        <Alert tone={status === "NEEDS_REVIEW" ? "warning" : "success"} title={response.message} />
        {guided?.removed_steps && guided.removed_steps.length > 0 && (
          <ul className="flex flex-col gap-1 text-sm">
            {guided.removed_steps.map((r) => (
              <li key={r.step_number} className="flex items-center gap-2">
                <span className="text-muted">Remove step {r.step_number}:</span>
                <span className="line-through decoration-invalid">
                  <MathText latex={textToLatex(r.text)} label={r.text} />
                </span>
                <span className="text-xs text-muted">— {r.reason}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  const solved = status === "SOLVED";
  const category = categoryLabel(guided?.error_category);

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-2">
        <p className="text-xs font-medium tracking-wide text-muted uppercase">
          {guided?.phase === "FIX_ERROR" ? `Fix step ${guided.step_number}` : solved ? "Finished" : `Write step ${guided?.step_number}`}
        </p>
        <div className="rounded-md border border-border bg-muted-surface px-4 py-3">
          <p className="text-xs text-muted">Continue from</p>
          {guided?.current_step && <MathText latex={textToLatex(guided.current_step)} label={guided.current_step} className="text-lg" />}
        </div>
        {guided?.phase === "FIX_ERROR" && guided.error_step && progress.length === 0 && (
          <p className="text-sm text-muted-strong">
            You wrote{" "}
            <span className="line-through decoration-invalid">
              <MathText latex={textToLatex(guided.error_step)} label={guided.error_step} />
            </span>
            {category && <> — {category.toLowerCase()}.</>} {guided.explanation}
          </p>
        )}
      </section>

      {progress.length > 0 && (
        <section aria-label="Your corrected steps" className="flex flex-col gap-1">
          <p className="text-xs text-muted">Your corrected steps so far</p>
          <ol className="flex flex-col gap-1">
            {progress.map((p, i) => (
              <li key={`${i}-${p}`} className="flex items-center gap-2 text-sm">
                <CheckCircle2 className="size-4 text-valid" aria-hidden />
                <MathText latex={textToLatex(p)} label={p} />
              </li>
            ))}
          </ol>
        </section>
      )}

      {feedback && (
        <Alert tone={feedback.tone} title={feedback.title}>
          {feedback.body}
        </Alert>
      )}

      {solved ? (
        <div className="rounded-lg border border-valid/40 bg-valid-soft px-4 py-3">
          <p className="flex items-center gap-2 font-medium text-foreground">
            <CheckCircle2 className="size-5 text-valid" aria-hidden /> Verified final answer
          </p>
          <MathText latex={solutionSetLatex(guided?.final_solution)} className="text-lg" />
        </div>
      ) : (
        <>
          {guided?.hint && (
            <section aria-live="polite" className="flex flex-col gap-2 rounded-md border border-primary/30 bg-primary-soft px-4 py-3">
              <p className="flex items-center justify-between text-xs text-muted">
                <span className="flex items-center gap-1.5 font-medium text-primary">
                  <HelpCircle className="size-3.5" aria-hidden />
                  {guided.reveal_answer ? "Answer" : `Hint ${guided.hint_level} of ${guided.max_hint_level}`}
                </span>
                {guided.expected_rule && <span className="hidden sm:inline">{guided.expected_rule}</span>}
              </p>
              {guided.reveal_answer && guided.revealed_step ? (
                <>
                  <MathText latex={textToLatex(guided.revealed_step)} label={guided.revealed_step} className="text-lg" />
                  {guided.revealed_explanation && <p className="text-sm text-muted-strong">{guided.revealed_explanation}</p>}
                </>
              ) : (
                <p className="text-sm text-foreground">{guided.hint}</p>
              )}
            </section>
          )}

          <form
            className="flex flex-col gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <label htmlFor="guided-attempt" className="text-sm font-medium">
              Your next step
            </label>
            <div className="flex gap-2">
              <input
                id="guided-attempt"
                value={attempt}
                onChange={(e) => setAttempt(e.target.value)}
                maxLength={MAX_STEP_LENGTH}
                placeholder="Type your corrected step"
                spellCheck={false}
                autoComplete="off"
                className="h-10 min-w-0 flex-1 rounded-md border border-border bg-background px-3 font-mono text-sm focus:outline-2 focus:outline-primary"
              />
              <Button type="submit" disabled={busy || !attempt.trim()}>
                {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Send className="size-4" aria-hidden />}
                Check
              </Button>
            </div>
            {attempt.trim() && <MathText latex={textToLatex(attempt)} className="text-sm text-muted-strong" />}
          </form>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" size="sm" onClick={moreHelp} disabled={busy || hintLevel >= 3}>
              {hintLevel >= 2 ? <Eye className="size-4" aria-hidden /> : <HelpCircle className="size-4" aria-hidden />}
              {hintLevel >= 2 ? "Show me this step" : "Give me another hint"}
            </Button>
            {guided?.attempt_feedback && !guided.attempt_feedback.valid && guided.attempt_feedback.lost_solutions.length > 0 && (
              <span className={cn("flex items-center gap-1 text-xs text-invalid")}>
                <XCircle className="size-3.5" aria-hidden />
                Your step loses x = {guided.attempt_feedback.lost_solutions.join(", x = ")}
              </span>
            )}
          </div>
        </>
      )}

      {error && (
        <Alert tone="error" title="Couldn't reach StepCheck">
          {error}
        </Alert>
      )}
    </div>
  );
}
