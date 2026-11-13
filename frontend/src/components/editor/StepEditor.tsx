"use client";

import { ArrowDown, ArrowUp, Calculator, Plus, Sparkles, Trash2 } from "lucide-react";
import { Fragment, useLayoutEffect, useRef, useState } from "react";

import { MathText } from "@/components/math/MathText";
import { Button } from "@/components/ui/button";
import { EXAMPLES } from "@/lib/examples";
import { applyKey, type Key } from "@/lib/keypad";
import { latexToText } from "@/lib/latex-to-text";
import { textToLatex } from "@/lib/math-renderer";
import { useInputMode, type InputMode } from "@/lib/preferences";
import { cn, MAX_STEP_LENGTH, MAX_STEPS, MIN_STEPS } from "@/lib/utils";

import { MathKeypad } from "./MathKeypad";
import { VisualMathField } from "./VisualMathField";

const MODES: { value: InputMode; label: string }[] = [
  { value: "keypad", label: "Keypad" },
  { value: "visual", label: "Visual editor" },
];

export type Row = { id: string; text: string };

let nextId = 0;
export const makeRows = (steps: string[]): Row[] => steps.map((text) => ({ id: `row-${nextId++}`, text }));

export function stepProblems(rows: Row[]): string | null {
  const filled = rows.filter((r) => r.text.trim());
  if (filled.length < MIN_STEPS) return `Enter at least ${MIN_STEPS} steps: the problem and at least one step of working.`;
  if (rows.some((r) => r.text.length > MAX_STEP_LENGTH)) return `Each step can be at most ${MAX_STEP_LENGTH} characters.`;
  return null;
}

/** A slim strip between steps (like adding a cell in a notebook): always visible, a full-width target. */
function InsertButton({ label, onClick, disabled }: { label: string; onClick: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={disabled ? `At most ${MAX_STEPS} steps` : label}
      className={cn(
        "group flex h-7 w-full items-center gap-2 text-muted transition-colors",
        "hover:text-primary focus-visible:text-primary focus-visible:outline-2 focus-visible:outline-primary",
        "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-muted",
      )}
    >
      <span className="h-px flex-1 bg-border group-hover:bg-primary/50 group-focus-visible:bg-primary/50" aria-hidden />
      <span className="flex items-center gap-1 rounded-full border border-border bg-card px-2 py-0.5 text-xs group-hover:border-primary/50">
        <Plus className="size-3" aria-hidden /> Add step
      </span>
      <span className="h-px flex-1 bg-border group-hover:bg-primary/50 group-focus-visible:bg-primary/50" aria-hidden />
    </button>
  );
}

const stepLabel = (index: number) => (index === 0 ? "Problem" : `Step ${index + 1}`);
const GROUPS = ["Algebra", "Calculus"] as const;

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
  const [activeId, setActiveId] = useState<string | null>(null);
  const [keypadOpen, setKeypadOpen] = useState(true);
  const [mode, setMode] = useInputMode();
  // Steps the visual editor holds but StepCheck can't read yet, by row id, with the reason.
  const [visualErrors, setVisualErrors] = useState<Record<string, string>>({});
  const inputs = useRef(new Map<string, HTMLInputElement>());
  const pendingCaret = useRef<{ id: string; caret: number } | null>(null);
  const visual = mode === "visual";
  // An unreadable visual step is empty in `rows`, so report it before "enter at least 2 steps".
  const problem =
    visual && Object.keys(visualErrors).length > 0
      ? "Fix the steps marked in red before checking: StepCheck can't read them yet."
      : stepProblems(rows);

  function changeMode(next: InputMode) {
    setVisualErrors({});
    setMode(next);
  }

  function onVisualEdit(id: string, latex: string) {
    const result = latexToText(latex);
    setVisualErrors((errors) => {
      const next = { ...errors };
      delete next[id];
      return result.ok ? next : { ...next, [id]: result.reason };
    });
    if (result.ok) update(id, result.text);
  }

  // After a keypad edit, put focus and the caret back where the key left them.
  useLayoutEffect(() => {
    const pending = pendingCaret.current;
    if (!pending) return;
    pendingCaret.current = null;
    const input = inputs.current.get(pending.id);
    input?.focus();
    input?.setSelectionRange(pending.caret, pending.caret);
  });

  const update = (id: string, text: string) => setRows((rs) => rs.map((r) => (r.id === id ? { ...r, text } : r)));
  const remove = (id: string) => setRows((rs) => (rs.length > 1 ? rs.filter((r) => r.id !== id) : rs));
  // Insert an empty step so that it ends up at `index` (0 = above the first step), and move to it.
  const insertAt = (index: number) => {
    if (rows.length >= MAX_STEPS) return;
    const fresh = makeRows([""]);
    setRows((rs) => [...rs.slice(0, index), ...fresh, ...rs.slice(index)]);
    setActiveId(fresh[0].id);
    pendingCaret.current = { id: fresh[0].id, caret: 0 };
  };
  const add = () => insertAt(rows.length);
  const move = (index: number, delta: -1 | 1) =>
    setRows((rs) => {
      const target = index + delta;
      if (target < 0 || target >= rs.length) return rs;
      const copy = [...rs];
      [copy[index], copy[target]] = [copy[target], copy[index]];
      return copy;
    });

  // The keypad types into the last focused step, or the last step if none has been focused.
  const activeRow = rows.find((r) => r.id === activeId) ?? rows[rows.length - 1];
  const targetIndex = rows.indexOf(activeRow);

  function pressKey(key: Key) {
    const input = inputs.current.get(activeRow.id);
    const start = input?.selectionStart ?? activeRow.text.length;
    const end = input?.selectionEnd ?? start;
    const edit = applyKey(activeRow.text, start, end, key);
    update(activeRow.id, edit.value);
    pendingCaret.current = { id: activeRow.id, caret: edit.caret };
  }

  function submit() {
    setTouched(true);
    if (problem) return;
    onSubmit(rows.map((r) => r.text.trim()).filter(Boolean));
  }

  return (
    <div className="flex flex-col gap-4">
      {showExamples && (
        <div className="flex flex-col gap-2 text-sm">
          <span className="flex items-center gap-1 text-muted">
            <Sparkles className="size-4" aria-hidden /> Try an example:
          </span>
          {GROUPS.map((group) => (
            <div key={group} className="flex flex-wrap items-center gap-2">
              <span className="w-16 text-xs font-medium text-muted">{group}</span>
              {EXAMPLES.filter((ex) => ex.group === group).map((ex) => (
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
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted" id="input-mode-label">
          Enter maths with:
        </span>
        <div role="group" aria-labelledby="input-mode-label" className="inline-flex rounded-lg border border-border bg-muted-surface p-1">
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              aria-pressed={mode === m.value}
              onClick={() => changeMode(m.value)}
              className={cn(
                "rounded-md px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-primary",
                mode === m.value ? "bg-card text-foreground shadow-sm" : "text-muted hover:text-foreground",
              )}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <ol className="flex flex-col" aria-label="Solution steps">
        <li className="list-none">
          <InsertButton label="Add step above step 1" onClick={() => insertAt(0)} disabled={rows.length >= MAX_STEPS} />
        </li>
        {rows.map((row, index) => {
          const tooLong = row.text.length > MAX_STEP_LENGTH;
          return (
            <Fragment key={row.id}>
            <li className="rounded-lg border border-border bg-card p-3">
              <div className="flex items-start gap-3">
                <span className="mt-2 w-14 shrink-0 text-xs font-medium text-muted">{stepLabel(index)}</span>
                <div className="flex min-w-0 flex-1 flex-col gap-2">
                  {visual ? (
                    <VisualMathField
                      initialLatex={textToLatex(row.text)}
                      label={stepLabel(index)}
                      invalid={tooLong || Boolean(visualErrors[row.id])}
                      onFocus={() => setActiveId(row.id)}
                      onLatex={(latex) => onVisualEdit(row.id, latex)}
                    />
                  ) : (
                    <input
                      ref={(el) => {
                        if (el) inputs.current.set(row.id, el);
                        else inputs.current.delete(row.id);
                      }}
                      value={row.text}
                      onChange={(e) => update(row.id, e.target.value)}
                      onFocus={() => setActiveId(row.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          if (index === rows.length - 1) add();
                        }
                      }}
                      placeholder={index === 0 ? "e.g. 2x + 5 = 15 or d/dx(x^2 sin(x))" : "e.g. 2x = 10"}
                      aria-label={stepLabel(index)}
                      aria-invalid={tooLong}
                      spellCheck={false}
                      autoComplete="off"
                      autoCapitalize="off"
                      className={cn(
                        "h-10 w-full rounded-md border bg-background px-3 font-mono text-sm text-foreground",
                        "focus:outline-2 focus:outline-primary",
                        tooLong ? "border-invalid" : "border-border",
                      )}
                    />
                  )}
                  <div className="flex min-h-6 items-center justify-between gap-2">
                    {visual ? (
                      visualErrors[row.id] ? (
                        <span role="alert" className="text-xs text-invalid">
                          {visualErrors[row.id]}
                        </span>
                      ) : (
                        <span className="min-w-0 truncate text-xs text-muted">
                          {row.text.trim() ? (
                            <>
                              Checked as: <code>{row.text}</code>
                            </>
                          ) : (
                            "Type with the keyboard icon or your own keyboard"
                          )}
                        </span>
                      )
                    ) : row.text.trim() ? (
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
            <li className="list-none">
              <InsertButton
                label={`Add step below step ${index + 1}`}
                onClick={() => insertAt(index + 1)}
                disabled={rows.length >= MAX_STEPS}
              />
            </li>
            </Fragment>
          );
        })}
      </ol>

      {!visual && (
        <div className="sticky bottom-2 z-10 flex flex-col gap-2 sm:static">
          <Button
            variant="ghost"
            size="sm"
            className="self-start"
            aria-expanded={keypadOpen}
            onClick={() => setKeypadOpen((open) => !open)}
          >
            <Calculator className="size-4" aria-hidden /> {keypadOpen ? "Hide keypad" : "Show keypad"}
          </Button>
          {keypadOpen && <MathKeypad onKey={pressKey} target={stepLabel(targetIndex)} />}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-end gap-3">
        <Button size="lg" onClick={submit} disabled={submitting}>
          {submitting ? "Checking…" : submitLabel}
        </Button>
      </div>
      {touched && problem && (
        <p role="alert" className="text-sm text-invalid">
          {problem}
        </p>
      )}
      <div className="flex flex-col gap-1 text-xs text-muted">
        <p>
          Write powers as <code>x^2</code>, roots as <code>sqrt(13)</code>, use <code>±</code> or <code>+/-</code>, and{" "}
          <code>or</code> between answers (e.g. <code>x = 2 or x = 3</code>).
        </p>
        <p>
          Calculus: <code>d/dx(x^2 sin(x))</code>, <code>int(x^2) dx</code>, <code>int[0, 2](x^2) dx</code>,{" "}
          <code>lim(x-&gt;0, sin(x)/x)</code>, <code>[x^3/3][0, 2]</code>, and <code>+ C</code> on indefinite integrals.
        </p>
      </div>
    </div>
  );
}
