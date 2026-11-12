"use client";

import { Bot, Cpu } from "lucide-react";

import { MathText } from "@/components/math/MathText";
import { Alert } from "@/components/ui/alert";
import { textToLatex } from "@/lib/math-renderer";
import type { ExplainResponse } from "@/lib/types";

import { categoryLabel } from "./format";

const SOURCE = {
  LLM: { label: "Explained by AI from StepCheck's verified result", Icon: Bot },
  TEMPLATE: { label: "Explained by StepCheck (AI explanation unavailable)", Icon: Cpu },
  ENGINE: { label: "From StepCheck's verification engine", Icon: Cpu },
} as const;

export function ExplainPanel({ explanation }: { explanation: ExplainResponse }) {
  const e = explanation;
  const source = SOURCE[e.source];
  const category = categoryLabel(e.error_category);
  return (
    <div className="flex flex-col gap-4" data-source={e.source}>
      <p className="flex items-center gap-2 text-xs text-muted">
        <source.Icon className="size-3.5" aria-hidden /> {source.label}
      </p>
      {category && (
        <p className="text-sm">
          <span className="text-muted">Type of mistake: </span>
          <span className="font-medium text-foreground">{category}</span>
          {e.first_error_step && <span className="text-muted"> · step {e.first_error_step}</span>}
        </p>
      )}
      <p className="text-foreground">{e.explanation}</p>
      {e.why_invalid && (
        <section className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold">Why it&apos;s not valid</h3>
          <p className="text-sm text-muted-strong">{e.why_invalid}</p>
        </section>
      )}
      {e.expected_rule && (
        <p className="rounded-md border border-border bg-muted-surface px-3 py-2 text-sm">
          <span className="font-medium">Rule: </span>
          {e.expected_rule}
        </p>
      )}
      {(e.corrected_step || e.suggested_next_step) && (
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          {e.corrected_step && (
            <div className="rounded-md border border-corrected/40 bg-corrected-soft px-3 py-2">
              <dt className="text-xs text-muted">Correct version of this step</dt>
              <dd>
                <MathText latex={textToLatex(e.corrected_step)} label={e.corrected_step} />
              </dd>
            </div>
          )}
          {e.suggested_next_step && (
            <div className="rounded-md border border-border px-3 py-2">
              <dt className="text-xs text-muted">Then continue with</dt>
              <dd>
                <MathText latex={textToLatex(e.suggested_next_step)} label={e.suggested_next_step} />
              </dd>
            </div>
          )}
        </dl>
      )}
      {e.how_to_avoid && (
        <section className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold">How to avoid it next time</h3>
          <p className="text-sm text-muted-strong">{e.how_to_avoid}</p>
        </section>
      )}
      {e.learning_tip && (
        <Alert tone="info" title="Tip">
          {e.learning_tip}
        </Alert>
      )}
    </div>
  );
}
