import { ChevronDown } from "lucide-react";

import { MathText } from "@/components/math/MathText";
import type { StepOut, TransitionOut, VerifyResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

import { REASON_LABELS, solutionSetLatex, valuesLatex } from "./format";
import { STEP_STATUS, StatusBadge, toneClasses } from "./status";

function StepDetails({ step, transition }: { step: StepOut; transition?: TransitionOut }) {
  const reason = transition?.reason_code;
  // Indefinite integrals are compared through their derivatives (antiderivatives differ by a constant).
  const integral = reason === "DIFFERS_BY_NON_CONSTANT";
  return (
    <div className="flex flex-col gap-2 text-sm text-muted-strong">
      {step.error && <p>{step.error.message}</p>}
      {reason && REASON_LABELS[reason] && <p>{REASON_LABELS[reason]}</p>}
      {transition && transition.lost_solutions.length > 0 && (
        <p className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-invalid">Lost:</span>
          <MathText latex={valuesLatex(transition.lost_solutions)} />
        </p>
      )}
      {transition && transition.extraneous_solutions.length > 0 && (
        <p className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-invalid">Added:</span>
          <MathText latex={valuesLatex(transition.extraneous_solutions)} />
        </p>
      )}
      {transition?.found_value_latex && (
        <p className="flex flex-wrap items-center gap-2">
          <span className="text-muted">{integral ? "Differentiating this step gives:" : "This step works out to:"}</span>
          <MathText latex={transition.found_value_latex} />
        </p>
      )}
      {transition?.expected_value_latex && (
        <p className="flex flex-wrap items-center gap-2">
          <span className="text-muted">{integral ? "It should give back the integrand:" : "It should equal:"}</span>
          <MathText latex={transition.expected_value_latex} />
        </p>
      )}
      {transition?.counterexample && (
        <p className="text-xs text-muted">For example, the two differ at {transition.counterexample}.</p>
      )}
      {transition?.note && <p className="text-xs text-muted">Note: {transition.note}.</p>}
      {step.solution_set && (
        <p className="flex flex-wrap items-center gap-2">
          <span className="text-muted">Solutions of this line:</span>
          <MathText latex={solutionSetLatex(step.solution_set)} />
        </p>
      )}
      {transition && step.status === "DOWNSTREAM_DEPENDENT" && (
        <p className="text-xs text-muted">
          Follows from the step before it: {transition.locally_valid ? "yes" : "no"} · Matches the original problem:{" "}
          {transition.matches_original ? "yes" : "no"}
        </p>
      )}
      {transition?.compared_to_step && transition.compared_to_step !== transition.from_step && (
        <p className="text-xs text-muted">Compared with step {transition.compared_to_step}, the last step StepCheck could check.</p>
      )}
    </div>
  );
}

export function StepTimeline({ verification }: { verification: VerifyResponse }) {
  const byTarget = new Map(verification.transitions.map((t) => [t.to_step, t]));
  return (
    <ol className="relative flex flex-col" aria-label="Step-by-step results">
      {verification.steps.map((step, index) => {
        const meta = STEP_STATUS[step.status];
        const tone = toneClasses[meta.tone];
        const transition = byTarget.get(step.step);
        const hasDetails = Boolean(step.error || transition?.reason_code || step.solution_set);
        const emphasised = step.status === "FIRST_INVALID";
        return (
          <li key={step.step} className="relative flex gap-4 pb-3" data-status={step.status}>
            <div className="flex flex-col items-center">
              <span className={cn("mt-4 size-3 rounded-full ring-4 ring-background", tone.dot)} aria-hidden />
              {index < verification.steps.length - 1 && <span className="w-px flex-1 bg-border" aria-hidden />}
            </div>
            <details
              open={emphasised}
              className={cn(
                "group min-w-0 flex-1 rounded-lg border bg-card",
                emphasised ? cn(tone.border, "border-2") : "border-border",
              )}
            >
              <summary
                className={cn(
                  "flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-4 py-3",
                  "focus-visible:outline-2 focus-visible:outline-primary",
                  !hasDetails && "cursor-default",
                )}
              >
                <span className="flex min-w-0 items-center gap-3">
                  <span className="w-12 shrink-0 text-xs text-muted">{index === 0 ? "Problem" : `Step ${step.step}`}</span>
                  {step.latex ? (
                    <MathText
                      latex={step.latex}
                      label={step.input}
                      className={cn("min-w-0 overflow-x-auto", step.status === "DOWNSTREAM_DEPENDENT" && "opacity-70")}
                    />
                  ) : (
                    <code className="min-w-0 truncate font-mono text-sm text-foreground">{step.input}</code>
                  )}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <StatusBadge status={step.status} />
                  {hasDetails && (
                    <ChevronDown className="size-4 text-muted transition-transform group-open:rotate-180" aria-hidden />
                  )}
                </span>
              </summary>
              {hasDetails && (
                <div className="border-t border-border px-4 py-3">
                  <StepDetails step={step} transition={transition} />
                </div>
              )}
            </details>
          </li>
        );
      })}
    </ol>
  );
}
