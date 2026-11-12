"use client";

import { ArrowDown, ArrowUp, Plus, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";

import { MathText } from "@/components/math/MathText";
import { Button } from "@/components/ui/button";
import { EXAMPLES } from "@/lib/examples";
import { textToLatex } from "@/lib/math-renderer";
import { cn, MAX_STEP_LENGTH, MAX_STEPS, MIN_STEPS } from "@/lib/utils";

export type Row = { id: string; text: string };

let nextId = 0;
export const makeRows = (steps: string[]): Row[] => steps.map((text) => ({ id: `row-${nextId++}`, text }));

export function stepProblems(rows: Row[]): string | null {
  const filled = rows.filter((r) => r.text.trim());
  if (filled.length < MIN_STEPS) return `Enter at least ${MIN_STEPS} steps: the problem and at least one step of working.`;
  if (rows.some((r) => r.text.length > MAX_STEP_LENGTH)) return `Each step can be at most ${MAX_STEP_LENGTH} characters.`;
  return null;
}

export function StepEditor({
  initialSteps,
  onSubmit,
  submitting,
  submitLabel = "Check my steps",
  showExamples = true,
}: {
  initialSteps?: string[];
  onSubmit: (steps: string[]) => void;
  submitting?: boolean;
  submitLabel?: string;
  showExamples?: boolean;
}) {
  const [rows, setRows] = useState<Row[]>(() => makeRows(initialSteps?.length ? initialSteps : ["", ""]));
  const [touched, setTouched] = useState(false);
  const problem = stepProblems(rows);

  const update = (id: string, text: string) => setRows((rs) => rs.map((r) => (r.id === id ? { ...r, text } : r)));
  const remove = (id: string) => setRows((rs) => (rs.length > 1 ? rs.filter((r) => r.id !== id) : rs));
  const add = () => setRows((rs) => (rs.length < MAX_STEPS ? [...rs, ...makeRows([""])] : rs));
  const move = (index: number, delta: -1 | 1) =>
    setRows((rs) => {
      const target = index + delta;
      if (target < 0 || target >= rs.length) return rs;
      const copy = [...rs];
      [copy[index], copy[target]] = [copy[target], copy[index]];
      return copy;
    });

  function submit() {
    setTouched(true);
    if (problem) return;
    onSubmit(rows.map((r) => r.text.trim()).filter(Boolean));
  }

  return (
    <div className="flex flex-col gap-4">
      {showExamples && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="flex items-center gap-1 text-muted">
            <Sparkles className="size-4" aria-hidden /> Try an example:
          </span>
          {EXAMPLES.map((ex) => (
            <button
              key={ex.id}
              type="button"
              onClick={() => setRows(makeRows(ex.steps))}
              className="rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-strong hover:border-primary/50 hover:text-foreground"
              title={ex.description}
            >
              {ex.title}
            </button>
          ))}
        </div>
      )}

      <ol className="flex flex-col gap-2" aria-label="Solution steps">
        {rows.map((row, index) => {
          const tooLong = row.text.length > MAX_STEP_LENGTH;
          return (
            <li key={row.id} className="rounded-lg border border-border bg-card p-3">
              <div className="flex items-start gap-3">
                <span className="mt-2 w-14 shrink-0 text-xs font-medium text-muted">
                  {index === 0 ? "Problem" : `Step ${index + 1}`}
                </span>
                <div className="flex min-w-0 flex-1 flex-col gap-2">
                  <input
                    value={row.text}
                    onChange={(e) => update(row.id, e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        if (index === rows.length - 1) add();
                      }
                    }}
                    placeholder={index === 0 ? "e.g. 2x + 5 = 15" : "e.g. 2x = 10"}
                    aria-label={index === 0 ? "Problem" : `Step ${index + 1}`}
                    aria-invalid={tooLong}
                    spellCheck={false}
                    autoComplete="off"
                    className={cn(
                      "h-10 w-full rounded-md border bg-background px-3 font-mono text-sm text-foreground",
                      "focus:outline-2 focus:outline-primary",
                      tooLong ? "border-invalid" : "border-border",
                    )}
                  />
                  <div className="flex min-h-6 items-center justify-between gap-2">
                    {row.text.trim() ? (
                      <MathText latex={textToLatex(row.text)} className="min-w-0 overflow-x-auto text-foreground" />
                    ) : (
                      <span className="text-xs text-muted">Preview appears here</span>
                    )}
                    <span className={cn("shrink-0 text-xs tabular-nums", tooLong ? "text-invalid" : "text-muted")}>
                      {row.text.length}/{MAX_STEP_LENGTH}
                    </span>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-0.5">
                  <Button variant="ghost" size="sm" onClick={() => move(index, -1)} disabled={index === 0} aria-label={`Move step ${index + 1} up`}>
                    <ArrowUp className="size-4" aria-hidden />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => move(index, 1)} disabled={index === rows.length - 1} aria-label={`Move step ${index + 1} down`}>
                    <ArrowDown className="size-4" aria-hidden />
                  </Button>
                  <Button variant="danger" size="sm" onClick={() => remove(row.id)} disabled={rows.length === 1} aria-label={`Delete step ${index + 1}`}>
                    <Trash2 className="size-4" aria-hidden />
                  </Button>
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="secondary" onClick={add} disabled={rows.length >= MAX_STEPS}>
          <Plus className="size-4" aria-hidden /> Add step
        </Button>
        <Button size="lg" onClick={submit} disabled={submitting}>
          {submitting ? "Checking…" : submitLabel}
        </Button>
      </div>
      {touched && problem && (
        <p role="alert" className="text-sm text-invalid">
          {problem}
        </p>
      )}
      <p className="text-xs text-muted">
        Write powers as <code>x^2</code>, roots as <code>sqrt(13)</code>, use <code>±</code> or <code>+/-</code>, and{" "}
        <code>or</code> between answers (e.g. <code>x = 2 or x = 3</code>).
      </p>
    </div>
  );
}
