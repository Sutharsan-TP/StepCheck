import { MathText } from "@/components/math/MathText";
import { Alert } from "@/components/ui/alert";
import { textToLatex } from "@/lib/math-renderer";
import type { CorrectResponse, VerifyResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

type Change = "same" | "fixed" | "removed" | "added";

const CHANGE: Record<Change, { label: string; className: string }> = {
  same: { label: "Kept", className: "text-valid" },
  fixed: { label: "Corrected", className: "text-corrected" },
  removed: { label: "Removed", className: "text-invalid" },
  added: { label: "Added", className: "text-muted-strong" },
};

const compact = (s: string) => s.replace(/[\s*]/g, "");

export type CompareRow = { index: number; mine: string | null; mineLatex: string | null; theirs: string | null; theirsLatex: string | null; change: Change };

/** Aligns the student's steps with the verified correction, line by line. */
export function compareRows(verification: VerifyResponse, correction: CorrectResponse): CompareRow[] {
  const corrected = correction.full?.corrected_solution ?? [];
  const length = Math.max(verification.steps.length, corrected.length);
  const rows: CompareRow[] = [];
  for (let i = 0; i < length; i++) {
    const mine = verification.steps[i];
    const theirs = corrected[i];
    let change: Change;
    if (mine && !theirs) change = "removed";
    else if (!mine && theirs) change = "added";
    else if (mine && theirs && compact(mine.input) === compact(theirs.text)) change = "same";
    else change = "fixed";
    rows.push({
      index: i + 1,
      mine: mine?.input ?? null,
      mineLatex: mine ? (mine.latex ?? textToLatex(mine.input)) : null,
      theirs: theirs?.text ?? null,
      theirsLatex: theirs ? (theirs.latex ?? textToLatex(theirs.text)) : null,
      change,
    });
  }
  return rows;
}

export function CompareView({ correction, verification }: { correction: CorrectResponse; verification: VerifyResponse }) {
  if (!correction.full || correction.status === "NEEDS_REVIEW") {
    return <Alert tone="warning" title="Nothing to compare yet">{correction.message}</Alert>;
  }
  if (correction.status === "NO_CORRECTION_NEEDED") {
    return <Alert tone="success" title="Your work already matches a verified solution." />;
  }
  const rows = compareRows(verification, correction);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[32rem] border-separate border-spacing-y-1 text-sm">
        <caption className="sr-only">Your steps compared with the verified correction</caption>
        <thead>
          <tr className="text-left text-xs text-muted">
            <th scope="col" className="w-8 font-medium">#</th>
            <th scope="col" className="font-medium">Your step</th>
            <th scope="col" className="font-medium">Verified step</th>
            <th scope="col" className="w-24 font-medium">Change</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.index} data-change={row.change} className={cn(row.change !== "same" && "bg-muted-surface")}>
              <td className="rounded-l-md px-2 py-2 text-xs text-muted tabular-nums">{row.index}</td>
              <td className={cn("px-2 py-2", row.change !== "same" && row.mine && "text-invalid line-through decoration-invalid/70")}>
                {row.mineLatex ? <MathText latex={row.mineLatex} label={row.mine ?? undefined} /> : <span className="text-muted">—</span>}
              </td>
              <td className="px-2 py-2">
                {row.theirsLatex ? <MathText latex={row.theirsLatex} label={row.theirs ?? undefined} /> : <span className="text-muted">—</span>}
              </td>
              <td className={cn("rounded-r-md px-2 py-2 text-xs font-medium", CHANGE[row.change].className)}>
                {CHANGE[row.change].label}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
