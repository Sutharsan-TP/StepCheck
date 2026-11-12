import { MathText } from "@/components/math/MathText";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { VerifyResponse } from "@/lib/types";

import { solutionSetLatex, solutionSetText, valuesLatex } from "./format";

const FINAL_STATUS: Record<string, string> = {
  SOLVED: "Stated explicitly",
  NOT_ISOLATED: "Not stated yet — x isn't on its own",
  UNVERIFIABLE: "Couldn't be checked",
};

export function SolutionSummary({ verification }: { verification: VerifyResponse }) {
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
