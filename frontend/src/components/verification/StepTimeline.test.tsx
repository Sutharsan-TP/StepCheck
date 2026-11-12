import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { VerifyResponse } from "@/lib/types";
import demo2 from "@/test/fixtures/verify-demo2.json";
import unsupported from "@/test/fixtures/verify-unsupported.json";

import { ResultBanner } from "./ResultBanner";
import { StepTimeline } from "./StepTimeline";

describe("StepTimeline", () => {
  it("shows each step's status with the matching colour", () => {
    const { container } = render(<StepTimeline verification={demo2 as VerifyResponse} />);
    const items = container.querySelectorAll("li[data-status]");
    expect([...items].map((li) => li.getAttribute("data-status"))).toEqual([
      "VALID",
      "VALID",
      "FIRST_INVALID",
      "DOWNSTREAM_DEPENDENT",
    ]);
    const badges = container.querySelectorAll("span[data-status]");
    expect(badges[0]).toHaveClass("text-valid");
    expect(badges[2]).toHaveClass("text-invalid");
    expect(badges[3]).toHaveClass("text-downstream");
  });

  it("opens the first incorrect step with lost and added solutions", () => {
    const { container } = render(<StepTimeline verification={demo2 as VerifyResponse} />);
    const first = container.querySelector('li[data-status="FIRST_INVALID"] details') as HTMLDetailsElement;
    expect(first.open).toBe(true);
    expect(within(first).getByText("Lost:")).toBeInTheDocument();
    expect(within(first).getByText("Added:")).toBeInTheDocument();
    expect(within(first).getByText(/changes the solutions/)).toBeInTheDocument();
  });

  it("uses amber for unsupported or unreadable steps and shows the reason", () => {
    const { container } = render(<StepTimeline verification={unsupported as VerifyResponse} />);
    const statuses = [...container.querySelectorAll("li[data-status]")].map((li) => li.getAttribute("data-status"));
    expect(statuses).toEqual(["UNSUPPORTED", "NEEDS_REVIEW", "NEEDS_REVIEW"]);
    expect(container.querySelector('span[data-status="UNSUPPORTED"]')).toHaveClass("text-review");
    expect(screen.getAllByText(/only linear and quadratic/i).length).toBeGreaterThan(0);
  });
});

describe("ResultBanner", () => {
  it("summarises the overall result", () => {
    render(<ResultBanner verification={demo2 as VerifyResponse} />);
    expect(screen.getByRole("heading", { name: "Mistake found" })).toBeInTheDocument();
    expect(screen.getByText("Step 3")).toBeInTheDocument();
  });
});
