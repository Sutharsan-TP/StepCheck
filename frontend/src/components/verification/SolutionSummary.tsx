import { MathText } from "@/components/math/MathText";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { VerifyResponse } from "@/lib/types";

import { isCalculus, solutionSetLatex, solutionSetText, TOPIC_LABELS, valuesLatex } from "./format";

const FINAL_STATUS: Record<string, string> = {
  SOLVED: "Stated explicitly",
  NOT_ISOLATED: "Not stated yet — x isn't on its own",
  UNVERIFIABLE: "Couldn't be checked",
};

const CALCULUS_FINAL_STATUS: Record<string, string> = {
  SOLVED: "Fully evaluated",
  NOT_ISOLATED: "Not finished — a d/dx, ∫ or lim is still there",
  UNVERIFIABLE: "Couldn't be checked",
};

export function SolutionSummary({ verification }: { verification: VerifyResponse }) {
  return isCalculus(verification.topic) ? <CalculusSummary verification={verification} /> : <AlgebraSummary verification={verification} />;
}

function CalculusSummary({ verification: v }: { verification: VerifyResponse }) {
  const last = v.steps[v.steps.length - 1];
  const complete = v.solution_complete === null ? "Unknown" : v.solution_complete ? "Yes" : v.missing_constant ? "No — add + C" : "No";
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{TOPIC_LABELS[v.topic ?? "ALGEBRA"]}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <div className="flex flex-col gap-1">
          <span className="text-muted">Correct answer</span>
          {v.expected_answer_latex ? (
            <MathText latex={v.expected_answer_latex} label={v.expected_answer ?? undefined} className="text-base" />
          ) : (
            <span className="text-muted-strong">Not available — StepCheck couldn&apos;t work this one out.</span>
          )}
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-muted">Your final answer</span>
          {v.final_answer_status === "SOLVED" && last.latex ? (
            <MathText latex={last.latex} label={last.input} className="text-base" />
          ) : (
            <span className="text-muted-strong">{CALCULUS_FINAL_STATUS[v.final_answer_status]}</span>
          )}
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 border-t border-border pt-3">
          <dt className="text-muted">Answer</dt>
          <dd className="text-foreground">{CALCULUS_FINAL_STATUS[v.final_answer_status]}</dd>
          <dt className="text-muted">Complete</dt>
          <dd className={v.missing_constant ? "text-invalid" : "text-foreground"}>{complete}</dd>
        </dl>
        {v.notes && v.notes.length > 0 && (
          <ul className="flex flex-col gap-1 text-xs text-muted">
            {v.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function AlgebraSummary({ verification }: { verification: VerifyResponse }) {
  const v = verification;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Solution</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <div className="flex flex-col gap-1">
          <span className="text-muted">Correct solution</span>
          {v.correct_solution_set ? (
            <MathText
              latex={solutionSetLatex(v.correct_solution_set)}
              label={solutionSetText(v.correct_solution_set)}
              className="text-base"
            />
          ) : (
            <span className="text-muted-strong">Not available — the problem couldn&apos;t be checked.</span>
          )}
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-muted">Your final answer</span>
          {v.submitted_solution_set ? (
            <MathText latex={solutionSetLatex(v.submitted_solution_set)} label={solutionSetText(v.submitted_solution_set)} className="text-base" />
          ) : (
            <span className="text-muted-strong">{FINAL_STATUS[v.final_answer_status]}</span>
          )}
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 border-t border-border pt-3">
          <dt className="text-muted">Answer</dt>
          <dd className="text-foreground">{FINAL_STATUS[v.final_answer_status]}</dd>
          <dt className="text-muted">Complete</dt>
          <dd className="text-foreground">
            {v.solution_complete === null ? "Unknown" : v.solution_complete ? "All solutions found" : "Not complete"}
          </dd>
          {v.missing_solutions && v.missing_solutions.length > 0 && (
            <>
              <dt className="text-invalid">Missing</dt>
              <dd>
                <MathText latex={valuesLatex(v.missing_solutions)} />
              </dd>
            </>
          )}
          {v.extraneous_solutions && v.extraneous_solutions.length > 0 && (
            <>
              <dt className="text-invalid">Not solutions</dt>
              <dd>
                <MathText latex={valuesLatex(v.extraneous_solutions)} />
              </dd>
            </>
          )}
        </dl>
      </CardContent>
    </Card>
  );
}
