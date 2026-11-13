import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { StepEditor } from "./StepEditor";

describe("StepEditor", () => {
  it("adds, edits and submits trimmed, non-empty steps", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<StepEditor onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Problem"), "2x + 5 = 15");
    await user.type(screen.getByLabelText("Step 2"), "  2x = 10 ");
    await user.click(screen.getByRole("button", { name: "Add step below step 2" }));
    await user.type(screen.getByLabelText("Step 3"), "x = 5");
    await user.click(screen.getByRole("button", { name: /check my steps/i }));

    expect(onSubmit).toHaveBeenCalledWith(["2x + 5 = 15", "2x = 10", "x = 5"]);
  });

  it("deletes and reorders steps", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<StepEditor initialSteps={["a = 1", "b = 2", "x = 3"]} onSubmit={onSubmit} showExamples={false} />);

    await user.click(screen.getByRole("button", { name: "Delete step 2" }));
    await user.click(screen.getByRole("button", { name: "Move step 2 up" }));
    await user.click(screen.getByRole("button", { name: /check my steps/i }));

    expect(onSubmit).toHaveBeenCalledWith(["x = 3", "a = 1"]);
  });

  it("requires at least two steps", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<StepEditor onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText("Problem"), "2x = 4");
    await user.click(screen.getByRole("button", { name: /check my steps/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/at least 2 steps/);
  });

  it("flags steps that are too long", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<StepEditor initialSteps={["x = 1", "x".repeat(201)]} onSubmit={onSubmit} showExamples={false} />);
    expect(screen.getByLabelText("Step 2")).toHaveAttribute("aria-invalid", "true");
    await user.click(screen.getByRole("button", { name: /check my steps/i }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("types into the focused step with the keypad, caret inside the template", async () => {
    const user = userEvent.setup();
    render(<StepEditor onSubmit={vi.fn()} showExamples={false} />);
    await user.click(screen.getByLabelText("Problem"));
    await user.click(screen.getByRole("tab", { name: "Calculus" }));
    await user.click(screen.getByRole("button", { name: "derivative" }));
    await user.keyboard("x^3");
    expect(screen.getByLabelText("Problem")).toHaveValue("d/dx(x^3)");
    expect(screen.getByLabelText("Problem")).toHaveFocus();
    expect(screen.getByText("Typing into: Problem")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Step 2"));
    await user.click(screen.getByRole("tab", { name: "Basic" }));
    await user.click(screen.getByRole("button", { name: "3" }));
    await user.click(screen.getByRole("button", { name: "x" }));
    await user.click(screen.getByRole("button", { name: "squared" }));
    expect(screen.getByLabelText("Step 2")).toHaveValue("3x^2");
  });

  it("loads a calculus example", async () => {
    const user = userEvent.setup();
    render(<StepEditor onSubmit={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Missing + C" }));
    expect(screen.getByLabelText("Problem")).toHaveValue("int(2x) dx");
  });

  it("loads an example", async () => {
    const user = userEvent.setup();
    render(<StepEditor onSubmit={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Lost quadratic solution" }));
    expect(screen.getByLabelText("Problem")).toHaveValue("x^2 - 5x + 6 = 0");
    expect(screen.getByLabelText("Step 4")).toHaveValue("x = 2");
  });
});

describe("StepEditor: inserting steps like notebook cells", () => {
  const order = () => screen.getAllByRole("textbox").map((el) => (el as HTMLInputElement).value);

  it("offers an insert strip above the first step, between steps and below the last", () => {
    render(<StepEditor initialSteps={["a", "b", "c"]} onSubmit={vi.fn()} showExamples={false} />);
    expect(screen.getAllByRole("button", { name: /^Add step/ }).map((b) => b.getAttribute("aria-label"))).toEqual([
      "Add step above step 1",
      "Add step below step 1",
      "Add step below step 2",
      "Add step below step 3",
    ]);
  });

  it("inserts in the middle, above the first and below the last, and focuses the new step", async () => {
    const user = userEvent.setup();
    render(<StepEditor initialSteps={["a", "b"]} onSubmit={vi.fn()} showExamples={false} />);

    await user.click(screen.getByRole("button", { name: "Add step below step 1" }));
    expect(order()).toEqual(["a", "", "b"]);
    expect(screen.getByLabelText("Step 2")).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Add step above step 1" }));
    expect(order()).toEqual(["", "a", "", "b"]);

    await user.click(screen.getByRole("button", { name: "Add step below step 4" }));
    expect(order()).toEqual(["", "a", "", "b", ""]);
  });
});
