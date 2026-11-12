"use client";

import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { MathText } from "@/components/math/MathText";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { textToLatex } from "@/lib/math-renderer";
import type { TranscriptionResponse } from "@/lib/types";
import { cn, MAX_STEP_LENGTH, MAX_STEPS, MIN_STEPS } from "@/lib/utils";

type ReviewRow = { id: string; text: string; flagged: boolean; reasons: string[]; checked: boolean };

let nextId = 0;

function rowsFrom(t: TranscriptionResponse): ReviewRow[] {
  return t.steps.map((s) => ({
    id: `review-${nextId++}`,
    text: s.expression,
    flagged: s.needs_review,
    reasons: s.review_reasons,
    checked: !s.needs_review,
  }));
}

/**
 * Side-by-side review of an AI transcription. Nothing is verified until the student
 * presses "Confirm transcription", and every flagged line must be checked first.
 */
export function TranscriptionReview({
  transcription,
  imageSrc,
  onConfirm,
  onCancel,
  submitting,
}: {
  transcription: TranscriptionResponse;
  imageSrc: string | null;
  onConfirm: (steps: string[]) => void;
  onCancel: () => void;
  submitting?: boolean;
}) {
  const [rows, setRows] = useState<ReviewRow[]>(() => rowsFrom(transcription));
  const unchecked = rows.filter((r) => !r.checked).length;
  const filled = rows.filter((r) => r.text.trim()).length;
  const tooLong = rows.some((r) => r.text.length > MAX_STEP_LENGTH);
  const canConfirm = unchecked === 0 && filled >= MIN_STEPS && !tooLong && !submitting;

  const patch = (id: string, change: Partial<ReviewRow>) =>
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...change } : r)));

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="overflow-hidden">
        <CardHeader>
          <CardTitle className="text-base">Your photo</CardTitle>
        </CardHeader>
        <CardContent>
          {imageSrc ? (
            // eslint-disable-next-line @next/next/no-img-element -- local data URL preview, not an optimisable asset
            <img src={imageSrc} alt="Uploaded handwritten working" className="w-full rounded-md border border-border" />
          ) : (
            <p className="text-sm text-muted">Preview unavailable.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Check the transcription</CardTitle>
          <CardDescription>
            AI read your handwriting. Compare each line with your photo and fix anything that&apos;s wrong — StepCheck
            will check exactly what is written here.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {transcription.warnings.map((w) => (
            <Alert key={w} tone="warning">
              {w}
            </Alert>
          ))}
          <ol className="flex flex-col gap-2" aria-label="Transcribed steps">
            {rows.map((row, index) => (
              <li
                key={row.id}
                data-flagged={row.flagged || undefined}
                className={cn(
                  "rounded-md border p-3",
                  row.flagged && !row.checked ? "border-review/60 bg-review-soft" : "border-border bg-card",
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="w-8 shrink-0 text-xs text-muted tabular-nums">{index + 1}</span>
                  <input
                    value={row.text}
                    onChange={(e) => patch(row.id, { text: e.target.value })}
                    aria-label={`Transcribed step ${index + 1}`}
                    spellCheck={false}
                    className="h-9 min-w-0 flex-1 rounded-md border border-border bg-background px-2 font-mono text-sm focus:outline-2 focus:outline-primary"
                  />
                  <Button
                    variant="danger"
                    size="sm"
                    aria-label={`Delete transcribed step ${index + 1}`}
                    onClick={() => setRows((rs) => rs.filter((r) => r.id !== row.id))}
                  >
                    <Trash2 className="size-4" aria-hidden />
                  </Button>
                </div>
                {row.text.trim() && <MathText latex={textToLatex(row.text)} className="mt-2 ml-10 block text-sm" />}
                {row.flagged && (
                  <div className="mt-2 ml-10 flex flex-col gap-1.5 text-xs">
                    <p className="flex items-start gap-1.5 text-review">
                      <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                      <span>{row.reasons.join(" ") || "Please double-check this line."}</span>
                    </p>
                    <label className="flex items-center gap-2 text-muted-strong">
                      <input
                        type="checkbox"
                        checked={row.checked}
                        onChange={(e) => patch(row.id, { checked: e.target.checked })}
                      />
                      I&apos;ve checked this line against my photo
                    </label>
                  </div>
                )}
              </li>
            ))}
          </ol>
          <Button
            variant="secondary"
            size="sm"
            className="self-start"
            disabled={rows.length >= MAX_STEPS}
            onClick={() =>
              setRows((rs) => [...rs, { id: `review-${nextId++}`, text: "", flagged: false, reasons: [], checked: true }])
            }
          >
            <Plus className="size-4" aria-hidden /> Add a missing line
          </Button>

          <div className="mt-2 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
            <Button variant="ghost" onClick={onCancel}>
              Use a different photo
            </Button>
            <Button
              size="lg"
              disabled={!canConfirm}
              onClick={() => onConfirm(rows.map((r) => r.text.trim()).filter(Boolean))}
            >
              {submitting ? "Checking…" : "Confirm transcription"}
            </Button>
          </div>
          {unchecked > 0 && (
            <p className="text-xs text-review" role="status">
              {unchecked} highlighted line{unchecked === 1 ? "" : "s"} still need{unchecked === 1 ? "s" : ""} checking.
            </p>
          )}
          {tooLong && <p className="text-xs text-invalid">Each step can be at most {MAX_STEP_LENGTH} characters.</p>}
        </CardContent>
      </Card>
    </div>
  );
}
