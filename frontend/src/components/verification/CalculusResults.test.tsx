import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { VerifyResponse } from "@/lib/types";
import correct from "@/test/fixtures/verify-calculus-correct.json";
import missingC from "@/test/fixtures/verify-calculus-missing-c.json";
import slip from "@/test/fixtures/verify-calculus-slip.json";

import { ResultBanner } from "./ResultBanner";
import { SolutionSummary } from "./SolutionSummary";
import { StepTimeline } from "./StepTimeline";

const v = (fixture: unknown) => fixture as VerifyResponse;

describe("calculus results", () => {
  it("marks the product-rule slip as the first error and shows the evidence", () => {
    const { container } = render(<StepTimeline verification={v(slip)} />);
    const statuses = [...container.querySelectorAll("li[data-status]")].map((li) => li.getAttribute("data-status"));
    expect(statuses).toEqual(["VALID", "FIRST_INVALID", "DOWNSTREAM_DEPENDENT"]);

    const first = container.querySelector('li[data-status="FIRST_INVALID"] details') as HTMLDetailsElement;
    expect(first.open).toBe(true);
    expect(within(first).getByText(/doesn't have the same value/)).toBeInTheDocument();
    expect(within(first).getByText("This step works out to:")).toBeInTheDocument();
    expect(within(first).getByText("It should equal:")).toBeInTheDocument();
    expect(within(first).getByText(/the two differ at x = /)).toBeInTheDocument();
    // Algebra-only details must not appear for calculus.
    expect(within(first).queryByText("Lost:")).not.toBeInTheDocument();
    expect(within(first).queryByText(/Solutions of this line/)).not.toBeInTheDocument();
  });

  it("explains the missing constant in the banner and summary", () => {
    render(
      <>
        <ResultBanner verification={v(missingC)} />
        <SolutionSummary verification={v(missingC)} />
      </>,
    );
    expect(screen.getByText("Unfinished")).toBeInTheDocument();
    expect(screen.getByText(/add \+ C to finish/)).toBeInTheDocument();
    expect(screen.getByText("Indefinite integral")).toBeInTheDocument();
    expect(screen.getByText("No — add + C")).toBeInTheDocument();
    expect(screen.getByRole("math", { name: "x^2 + C" })).toBeInTheDocument();
  });

  it("shows the engine's final answer and the student's for a correct limit", () => {
    render(<SolutionSummary verification={v(correct)} />);
    expect(screen.getByText("Limit")).toBeInTheDocument();
    expect(screen.getByText("Fully evaluated", { selector: "dd" })).toBeInTheDocument();
    // The engine's answer and the student's final line are both 1.
    expect(screen.getAllByRole("math", { name: "1" })).toHaveLength(2);
  });

  it("uses value wording instead of solution-set wording for a mistake", () => {
    render(<ResultBanner verification={v(slip)} />);
    expect(screen.getByText("A step changes the value of the expression.")).toBeInTheDocument();
  });
});
