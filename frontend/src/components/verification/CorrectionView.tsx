import { ShieldCheck } from "lucide-react";

import { MathText } from "@/components/math/MathText";
import { Alert } from "@/components/ui/alert";
import { textToLatex } from "@/lib/math-renderer";
import type { CorrectResponse, CorrectionStepOut, VerifyResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

import { categoryLabel, solutionSetLatex, solutionSetText } from "./format";
import { StatusBadge } from "./status";

const SOURCE_BADGE: Record<CorrectionStepOut["source"], { label: string; className: string }> = {
  STUDENT: { label: "Your step", className: "border-valid/40 bg-valid-soft text-valid" },
  CORRECTED: { label: "Corrected", className: "border-corrected/40 bg-corrected-soft text-corrected" },
  GENERATED: { label: "Next step", className: "border-border bg-muted-surface text-muted-strong" },
};

function stepLatex(step: { latex: string | null; text: string }) {
  return step.latex ?? textToLatex(step.text);
}

export function CorrectionView({ correction, verification }: { correction: CorrectResponse; verification: VerifyResponse }) {
  const full = correction.full;
  if (!full || correction.status === "NEEDS_REVIEW") {
    return <Alert tone="warning" title="No verified correction available">{correction.message}</Alert>;
  }
  if (correction.status === "NO_CORRECTION_NEEDED") {
    return <Alert tone="success" title={correction.message} />;
  }
  const removed = new Map(full.removed_steps.map((r) => [r.step_number, r]));
  const category = categoryLabel(full.error_category);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <p className="font-medium text-foreground">{correction.message}</p>
        {category && (
          <p className="text-sm text-muted-strong">
            <span className="font-medium">{category}.</span> {full.explanation}
          </p>
        )}
        {full.evidence && <p className="text-sm text-muted">{full.evidence}</p>}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-label="Your work" className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-muted-strong">Your work</h3>
          <ol className="flex flex-col gap-2">
            {verification.steps.map((step) => {
              const r = removed.get(step.step);
              return (
                <li
                  key={step.step}
                  className={cn(
                    "flex items-center justify-between gap-3 rounded-md border bg-card px-3 py-2",
                    step.status === "FIRST_INVALID" ? "border-invalid/50" : "border-border",
                  )}
                >
                  <span className={cn("flex min-w-0 items-center gap-3", r && "line-through decoration-invalid opacity-70")}>
                    <span className="w-5 shrink-0 text-right text-xs text-muted tabular-nums">{step.step}</span>
                    {step.latex ? <MathText latex={step.latex} label={step.input} /> : <code className="text-sm">{step.input}</code>}
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-1">
                    <StatusBadge status={step.status} />
                    {r && <span className="text-xs text-invalid">Remove</span>}
                  </span>
                </li>
              );
            })}
          </ol>
        </section>

        <section aria-label="Verified correction" className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-muted-strong">Verified correction</h3>
          <ol className="flex flex-col gap-2">
            {full.corrected_solution.map((step) => {
              const badge = SOURCE_BADGE[step.source];
              return (
                <li
                  key={step.step_number}
                  data-source={step.source}
                  className={cn(
                    "flex flex-col gap-1 rounded-md border px-3 py-2",
                    step.source === "CORRECTED" ? "border-corrected/50 bg-corrected-soft" : "border-border bg-card",
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="flex min-w-0 items-center gap-3">
                      <span className="w-5 shrink-0 text-right text-xs text-muted tabular-nums">{step.step_number}</span>
                      <MathText latex={stepLatex(step)} label={step.text} />
                    </span>
                    <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium", badge.className)}>
                      {badge.label}
                    </span>
                  </div>
                  {step.explanation && (
                    <p className="pl-8 text-xs text-muted-strong">
                      {step.rule_name && <span className="font-medium">{step.rule_name}. </span>}
                      {step.explanation}
                    </p>
                  )}
                </li>
              );
            })}
          </ol>
          {full.removed_steps.length > 0 && (
            <ul className="flex flex-col gap-1 text-xs text-muted-strong">
              {full.removed_steps.map((r) => (
                <li key={r.step_number}>
                  Step {r.step_number} removed — {r.reason}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {full.final_solution && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-valid/40 bg-valid-soft px-4 py-3">
          <div>
            <p className="text-xs text-muted">Final answer</p>
            <MathText latex={solutionSetLatex(full.final_solution)} label={solutionSetText(full.final_solution)} className="text-lg" />
          </div>
          {full.verification && (
            <p className="flex items-center gap-1.5 text-sm text-valid">
              <ShieldCheck className="size-4" aria-hidden />
              Every step re-checked by StepCheck
              {full.verification.solution_complete ? " · all solutions found" : ""}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
