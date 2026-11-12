import { ArrowRight, Camera, ListOrdered, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { MathText } from "@/components/math/MathText";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/verification/status";
import type { StepStatus } from "@/lib/types";

const EXAMPLE: { latex: string; status: StepStatus; note?: string }[] = [
  { latex: "2x + 5 = 15", status: "VALID" },
  { latex: "2x = 15 - 5", status: "VALID" },
  { latex: "2x = 20", status: "FIRST_INVALID", note: "15 − 5 is 10, not 20 — the solution changes from 5 to 10." },
  { latex: "x = 10", status: "DOWNSTREAM_DEPENDENT", note: "Follows from the mistake above." },
];

const SUPPORTED = [
  "Linear equations in x",
  "Quadratic equations (factoring, the quadratic formula, ±)",
  "Expanding brackets and combining like terms",
  "Adding, subtracting, multiplying and dividing both sides",
  "Exact answers: fractions and square roots",
  "Identities and equations with no real solution",
];

export default function LandingPage() {
  return (
    <div className="flex flex-col gap-14">
      <section className="grid items-center gap-10 lg:grid-cols-[1.1fr_1fr]">
        <div className="flex flex-col gap-5">
          <p className="text-sm font-medium tracking-wide text-primary uppercase">Step-by-step algebra checking</p>
          <h1 className="font-serif text-4xl leading-tight font-semibold text-foreground sm:text-5xl">
            Find the exact step where a solution goes wrong.
          </h1>
          <p className="max-w-xl text-lg text-muted-strong">
            StepCheck checks every line of your working, pinpoints the first incorrect step, explains why it&apos;s
            invalid, and helps you fix it — without just handing over the answer.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="/workspace"
              className="inline-flex h-12 items-center gap-2 rounded-md bg-primary px-6 font-medium text-primary-foreground shadow-sm hover:bg-primary/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              Check my solution
              <ArrowRight className="size-4" aria-hidden />
            </Link>
            <span className="text-sm text-muted">Type your steps or upload a photo.</span>
          </div>
        </div>

        <Card aria-label="Example of first-error detection">
          <CardHeader>
            <CardTitle className="text-base">Example check</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="flex flex-col gap-3">
              {EXAMPLE.map((row, i) => (
                <li key={row.latex} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between gap-3">
                    <span className="flex items-center gap-3">
                      <span className="w-5 text-right text-xs text-muted tabular-nums">{i + 1}</span>
                      <MathText latex={row.latex} label={row.latex} />
                    </span>
                    <StatusBadge status={row.status} />
                  </div>
                  {row.note && <p className="pl-8 text-xs text-muted">{row.note}</p>}
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {[
          {
            Icon: ListOrdered,
            title: "Every step, not just the answer",
            body: "Each line is compared with the one before it, so a lucky final answer can't hide a broken step.",
          },
          {
            Icon: ShieldCheck,
            title: "Mathematically verified",
            body: "A symbolic engine decides what is correct. AI never judges your maths — it only helps explain it.",
          },
          {
            Icon: Camera,
            title: "Typed or handwritten",
            body: "Type your steps, or upload a photo and confirm the transcription before anything is checked.",
          },
        ].map(({ Icon, title, body }) => (
          <Card key={title}>
            <CardContent className="flex flex-col gap-2 py-5">
              <Icon className="size-5 text-primary" aria-hidden />
              <h2 className="font-serif text-lg font-semibold">{title}</h2>
              <p className="text-sm text-muted-strong">{body}</p>
            </CardContent>
          </Card>
        ))}
      </section>

      <section>
        <Card>
          <CardHeader>
            <CardTitle>What StepCheck supports</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-6 md:grid-cols-[1fr_auto]">
            <ul className="grid gap-2 text-sm text-muted-strong sm:grid-cols-2">
              {SUPPORTED.map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
                  {item}
                </li>
              ))}
            </ul>
            <p className="max-w-xs text-sm text-muted">
              Single variable x, real numbers only. Higher-degree polynomials, trigonometry, logarithms, inequalities
              and other variables are reported as unsupported rather than guessed.
            </p>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
