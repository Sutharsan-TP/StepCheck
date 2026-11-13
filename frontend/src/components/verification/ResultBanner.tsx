import type { VerifyResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

import { isCalculus } from "./format";
import { OVERALL_STATUS, toneClasses } from "./status";

/** The banner's one-line summary; calculus work is about values, not solutions of an equation. */
function summaryFor(v: VerifyResponse): string {
  if (!isCalculus(v.topic)) return OVERALL_STATUS[v.overall_status].summary;
  if (v.overall_status === "INCORRECT") return "A step changes the value of the expression.";
  if (v.overall_status === "INCOMPLETE") {
    return v.missing_constant
      ? "Every step is valid — add + C to finish the indefinite integral."
      : "Every step is valid, but there's still something left to evaluate.";
  }
  return OVERALL_STATUS[v.overall_status].summary;
}

export function ResultBanner({ verification }: { verification: VerifyResponse }) {
  const meta = OVERALL_STATUS[verification.overall_status];
  const tone = toneClasses[meta.tone];
  const firstError = verification.first_error_step;
  const extra =
    verification.complete_answer_step && verification.complete_answer_step < verification.steps.length
      ? `Your answer was already complete at step ${verification.complete_answer_step}.`
      : null;

  return (
    <section
      aria-label="Overall result"
      data-overall={verification.overall_status}
      className={cn("flex flex-col gap-3 rounded-lg border p-5 sm:flex-row sm:items-center sm:justify-between", tone.soft, tone.border)}
    >
      <div className="flex items-start gap-3">
        <meta.Icon className={cn("mt-0.5 size-7 shrink-0", tone.text)} aria-hidden />
        <div>
          <h2 className="font-serif text-2xl font-semibold text-foreground">{meta.label}</h2>
          <p className="text-muted-strong">{summaryFor(verification)}</p>
          {extra && <p className="mt-1 text-sm text-muted-strong">{extra}</p>}
        </div>
      </div>
      <dl className="grid shrink-0 grid-cols-2 gap-x-6 gap-y-1 text-sm">
        <dt className="text-muted">First incorrect step</dt>
        <dd className="font-medium text-foreground">{firstError ? `Step ${firstError}` : "None"}</dd>
        <dt className="text-muted">Answer complete</dt>
        <dd className="font-medium text-foreground">
          {verification.solution_complete === null ? "Unknown" : verification.solution_complete ? "Yes" : "No"}
        </dd>
      </dl>
    </section>
  );
}
