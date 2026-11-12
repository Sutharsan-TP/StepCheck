import { AlertTriangle, CheckCircle2, CircleDashed, CornerDownRight, HelpCircle, XCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { OverallStatus, StepStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

type Tone = "valid" | "invalid" | "downstream" | "review";

export const toneClasses: Record<Tone, { text: string; soft: string; border: string; dot: string }> = {
  valid: { text: "text-valid", soft: "bg-valid-soft", border: "border-valid/40", dot: "bg-valid" },
  invalid: { text: "text-invalid", soft: "bg-invalid-soft", border: "border-invalid/50", dot: "bg-invalid" },
  downstream: { text: "text-downstream", soft: "bg-downstream-soft", border: "border-downstream/30", dot: "bg-downstream" },
  review: { text: "text-review", soft: "bg-review-soft", border: "border-review/40", dot: "bg-review" },
};

export const STEP_STATUS: Record<StepStatus, { label: string; tone: Tone; Icon: LucideIcon; description: string }> = {
  VALID: { label: "Valid", tone: "valid", Icon: CheckCircle2, description: "Same solutions as the step before." },
  FIRST_INVALID: { label: "First error", tone: "invalid", Icon: XCircle, description: "The first step that changes the solutions." },
  DOWNSTREAM_DEPENDENT: {
    label: "Depends on error",
    tone: "downstream",
    Icon: CornerDownRight,
    description: "Built on the incorrect step, so it can't be trusted.",
  },
  UNSUPPORTED: { label: "Unsupported", tone: "review", Icon: AlertTriangle, description: "Outside the mathematics StepCheck supports." },
  NEEDS_REVIEW: { label: "Needs review", tone: "review", Icon: HelpCircle, description: "StepCheck couldn't read or place this step." },
};

export const OVERALL_STATUS: Record<OverallStatus, { label: string; tone: Tone; Icon: LucideIcon; summary: string }> = {
  CORRECT: { label: "Correct", tone: "valid", Icon: CheckCircle2, summary: "Every step is valid and the answer is complete." },
  INCORRECT: { label: "Mistake found", tone: "invalid", Icon: XCircle, summary: "A step changes the solutions of the equation." },
  INCOMPLETE: { label: "Unfinished", tone: "review", Icon: CircleDashed, summary: "Every step is valid, but the answer isn't stated yet." },
  UNSUPPORTED: { label: "Unsupported", tone: "review", Icon: AlertTriangle, summary: "Part of this work is outside the supported mathematics." },
  NEEDS_REVIEW: { label: "Needs review", tone: "review", Icon: HelpCircle, summary: "Some steps couldn't be read or checked." },
};

export function StatusBadge({ status, className }: { status: StepStatus; className?: string }) {
  const meta = STEP_STATUS[status];
  const tone = toneClasses[meta.tone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        tone.text,
        tone.soft,
        tone.border,
        className,
      )}
      data-status={status}
    >
      <meta.Icon className="size-3.5" aria-hidden />
      {meta.label}
    </span>
  );
}
