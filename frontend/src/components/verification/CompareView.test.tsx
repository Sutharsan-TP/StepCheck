import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CorrectResponse, VerifyResponse } from "@/lib/types";
import fullDemo3 from "@/test/fixtures/full-demo3.json";
import fullRemove from "@/test/fixtures/full-remove.json";
import verifyDemo3 from "@/test/fixtures/verify-demo3.json";

import { compareRows } from "./CompareView";
import { CorrectionView } from "./CorrectionView";

const v3 = verifyDemo3 as VerifyResponse;

describe("compareRows", () => {
  it("aligns the student's work with the verified correction", () => {
    const rows = compareRows(v3, fullDemo3 as CorrectResponse);
    expect(rows.map((r) => r.change)).toEqual(["same", "same", "fixed", "fixed"]);
    expect(rows[2].theirs).toBe("x - 2 = 0 or x - 3 = 0");
  });
});

describe("CorrectionView", () => {
  it("labels student, corrected and generated steps and the verified answer", () => {
    const { container } = render(<CorrectionView correction={fullDemo3 as CorrectResponse} verification={v3} />);
    const sources = [...container.querySelectorAll("li[data-source]")].map((li) => li.getAttribute("data-source"));
    expect(sources).toEqual(["STUDENT", "STUDENT", "CORRECTED", "GENERATED"]);
    expect(screen.getByText(/Dropped a factor/)).toBeInTheDocument();
    expect(screen.getByText(/re-checked by StepCheck/)).toBeInTheDocument();
  });

  it("shows removed steps when the answer was already complete", () => {
    const verification = { ...v3, steps: v3.steps.slice(0, 4) } as VerifyResponse;
    render(<CorrectionView correction={fullRemove as CorrectResponse} verification={verification} />);
    expect(screen.getByText(/already complete at step 3/)).toBeInTheDocument();
    expect(screen.getByText(/Step 4 removed/)).toBeInTheDocument();
  });
});
