"use client";

import { BookOpenCheck, Columns2, Compass, Loader2, MessageSquareText, PencilLine, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CompareView } from "@/components/verification/CompareView";
import { CorrectionView } from "@/components/verification/CorrectionView";
import { ExplainPanel } from "@/components/verification/ExplainPanel";
import { GuidedPanel } from "@/components/verification/GuidedPanel";
import { ResultBanner } from "@/components/verification/ResultBanner";
import { SolutionSummary } from "@/components/verification/SolutionSummary";
import { StepTimeline } from "@/components/verification/StepTimeline";
import { useStepCheck } from "@/hooks/useStepCheck";
import { correct, describeError, explain, type WorkRef } from "@/lib/api";
import { useHydrated, useSession, type Session } from "@/lib/session";
import type { CorrectResponse, ExplainResponse, VerifyResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

type Panel = "explain" | "guided" | "correction" | "compare";
type Loadable<T> = { state: "idle" } | { state: "loading" } | { state: "error"; message: string } | { state: "ready"; data: T };

export default function ResultsPage() {
  const hydrated = useHydrated();
  const session = useSession();
  if (!hydrated) return <div className="h-96 animate-pulse rounded-lg bg-muted-surface" aria-hidden />;
  if (!session?.verification) {
    return (
      <Card className="mx-auto max-w-lg">
        <CardHeader>
          <CardTitle>No solution checked yet</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-muted-strong">Enter or upload your working to see step-by-step results.</p>
          <Link href="/workspace" className="self-start rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">
            Check a solution
          </Link>
        </CardContent>
      </Card>
    );
  }
  return <Results key={session.verification.verification_id} session={session as Session & { verification: VerifyResponse }} />;
}

function Results({ session }: { session: Session & { verification: VerifyResponse } }) {
  const verification = session.verification;
  const { startOver } = useStepCheck();
  const [panel, setPanel] = useState<Panel | null>(null);
  const [explanation, setExplanation] = useState<Loadable<ExplainResponse>>({ state: "idle" });
  const [full, setFull] = useState<Loadable<CorrectResponse>>({ state: "idle" });
  const work: WorkRef = useMemo(
    () => ({ verificationId: verification.verification_id, steps: session.steps }),
    [verification.verification_id, session.steps],
  );
  const correctWork = verification.overall_status === "CORRECT";

  async function open(next: Panel) {
    setPanel(next);
    if (next === "explain" && (explanation.state === "idle" || explanation.state === "error")) {
      setExplanation({ state: "loading" });
      try {
        setExplanation({ state: "ready", data: await explain(work) });
      } catch (e) {
        setExplanation({ state: "error", message: describeError(e) });
      }
    }
    if ((next === "correction" || next === "compare") && (full.state === "idle" || full.state === "error")) {
      setFull({ state: "loading" });
      try {
        setFull({ state: "ready", data: await correct(work, { mode: "FULL" }) });
      } catch (e) {
        setFull({ state: "error", message: describeError(e) });
      }
    }
  }

  const actions: { value: Panel; label: string; Icon: typeof Compass; hint: string }[] = [
    { value: "explain", label: "Explain mistake", Icon: MessageSquareText, hint: "Why the step is wrong" },
    { value: "guided", label: "Guide me through it", Icon: Compass, hint: "Fix it yourself with hints" },
    { value: "correction", label: "Show corrected solution", Icon: BookOpenCheck, hint: "A verified full solution" },
    { value: "compare", label: "Compare my work", Icon: Columns2, hint: "Your steps side by side" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-serif text-3xl font-semibold">Results</h1>
        <div className="flex gap-2">
          <Link
            href="/workspace"
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-card px-3 text-sm hover:bg-muted-surface"
          >
            <PencilLine className="size-4" aria-hidden /> Edit steps
          </Link>
          <Button variant="ghost" size="sm" onClick={startOver}>
            <RotateCcw className="size-4" aria-hidden /> New problem
          </Button>
        </div>
      </div>

      <ResultBanner verification={verification} />

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <section aria-label="Steps" className="min-w-0">
          <StepTimeline verification={verification} />
        </section>
        <aside className="flex flex-col gap-4">
          <SolutionSummary verification={verification} />
          {session.imagePreview && (
            <Card className="overflow-hidden">
              <CardHeader>
                <CardTitle className="text-base">Original photo</CardTitle>
              </CardHeader>
              <CardContent>
                {/* eslint-disable-next-line @next/next/no-img-element -- local data URL */}
                <img src={session.imagePreview} alt="Uploaded handwritten working" className="w-full rounded-md border border-border" />
              </CardContent>
            </Card>
          )}
        </aside>
      </div>

      {correctWork ? (
        <Alert tone="success" title="Nothing to correct">
          Every transformation keeps exactly the same solutions, and your final answer states all of them.
        </Alert>
      ) : (
        <section aria-label="Help with this solution" className="flex flex-col gap-4">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4" role="group" aria-label="Correction options">
            {actions.map(({ value, label, Icon, hint }) => (
              <button
                key={value}
                type="button"
                aria-pressed={panel === value}
                onClick={() => void open(value)}
                className={cn(
                  "flex items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors",
                  "focus-visible:outline-2 focus-visible:outline-primary",
                  panel === value ? "border-primary bg-primary-soft" : "border-border bg-card hover:border-primary/50",
                )}
              >
                <Icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
                <span>
                  <span className="block font-medium text-foreground">{label}</span>
                  <span className="block text-xs text-muted">{hint}</span>
                </span>
              </button>
            ))}
          </div>

          {panel && (
            <Card>
              <CardContent className="py-5">
                {panel === "explain" && <LoadableView value={explanation} render={(data) => <ExplainPanel explanation={data} />} />}
                {panel === "guided" && <GuidedPanel work={work} />}
                {panel === "correction" && (
                  <LoadableView value={full} render={(data) => <CorrectionView correction={data} verification={verification} />} />
                )}
                {panel === "compare" && (
                  <LoadableView value={full} render={(data) => <CompareView correction={data} verification={verification} />} />
                )}
              </CardContent>
            </Card>
          )}
        </section>
      )}
    </div>
  );
}

function LoadableView<T>({ value, render }: { value: Loadable<T>; render: (data: T) => React.ReactNode }) {
  if (value.state === "ready") return <>{render(value.data)}</>;
  if (value.state === "error") return <Alert tone="error" title="Couldn't load this">{value.message}</Alert>;
  return (
    <p className="flex items-center gap-2 text-sm text-muted" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden /> Working on it…
    </p>
  );
}
