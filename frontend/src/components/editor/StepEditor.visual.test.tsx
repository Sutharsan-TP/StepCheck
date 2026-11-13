import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetInputModeMemory } from "@/lib/preferences";

import { StepEditor } from "./StepEditor";

// jsdom cannot run MathLive's real element (the browser tests do); stand in a minimal one.
const fields = vi.hoisted(() => [] as (HTMLElement & { value: string })[]);
vi.mock("mathlive", () => {
  class FakeMathfieldElement {
    static fontsDirectory: string | null = "";
    static soundsDirectory: string | null = "";
    constructor() {
      const el = Object.assign(document.createElement("div"), { value: "" });
      fields.push(el);
      return el as unknown as FakeMathfieldElement;
    }
  }
  return { MathfieldElement: FakeMathfieldElement };
});

function type(index: number, latex: string) {
  act(() => {
    fields[index].value = latex;
    fields[index].dispatchEvent(new Event("input"));
  });
}

beforeEach(() => {
  fields.length = 0;
  Object.assign(window, { mathVirtualKeyboard: { layouts: [] } });
});

afterEach(() => {
  window.localStorage.clear();
  resetInputModeMemory();
});

async function openVisual(onSubmit = vi.fn()) {
  const user = userEvent.setup();
  render(<StepEditor onSubmit={onSubmit} showExamples={false} />);
  await user.click(screen.getByRole("button", { name: "Visual editor" }));
  await waitFor(() => expect(fields).toHaveLength(2));
  return { user, onSubmit };
}

describe("StepEditor visual mode", () => {
  it("switches to the visual editor, hides the keypad and remembers the choice", async () => {
    await openVisual();
    expect(screen.getByRole("button", { name: "Visual editor" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByLabelText("Maths keypad")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Problem" })).not.toBeInTheDocument();
    expect(window.localStorage.getItem("stepcheck.inputMode.v1")).toBe("visual");
  });

  it("starts the visual field from the step's existing text", async () => {
    const user = userEvent.setup();
    render(<StepEditor initialSteps={["d/dx(x^3)", "3x^2"]} onSubmit={vi.fn()} showExamples={false} />);
    await user.click(screen.getByRole("button", { name: "Visual editor" }));
    await waitFor(() => expect(fields).toHaveLength(2));
    expect(fields[0].value).toBe("\\frac{d}{dx}\\left(x^{3}\\right)");
    expect(fields[1].value).toBe("3x^{2}");
  });

  it("turns what is typed in the visual editor into the text that is submitted", async () => {
    const { user, onSubmit } = await openVisual();
    type(0, "\\frac{d}{dx}\\left(x^{3}\\right)");
    type(1, "3x^{2}");
    expect(screen.getAllByText(/Checked as:/)).toHaveLength(2);
    expect(screen.getByText("d/dx(x^3)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /check my steps/i }));
    expect(onSubmit).toHaveBeenCalledWith(["d/dx(x^3)", "3x^2"]);
  });

  it("refuses to submit something StepCheck can't read, and says why", async () => {
    const { user, onSubmit } = await openVisual();
    type(0, "\\sum_{i=1}^{n}i");
    type(1, "3x^{2}");
    expect(screen.getByText(/isn't supported/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /check my steps/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/Fix the steps marked in red/)).toBeInTheDocument();

    type(0, "\\int x^{2}\\,dx");
    await user.click(screen.getByRole("button", { name: /check my steps/i }));
    expect(onSubmit).toHaveBeenCalledWith(["int(x^2) dx", "3x^2"]);
  });

  it("keeps the typed text when switching back to the keypad", async () => {
    const { user } = await openVisual();
    type(0, "\\int x^{2}\\,dx");
    type(1, "\\frac{x^{3}}{3}+C");
    await user.click(screen.getByRole("button", { name: "Keypad" }));
    expect(screen.getByRole("textbox", { name: "Problem" })).toHaveValue("int(x^2) dx");
    expect(screen.getByRole("textbox", { name: "Step 2" })).toHaveValue("x^3/3 + C");
    expect(screen.getByLabelText("Maths keypad")).toBeInTheDocument();
  });

  it("offers the keypad when the visual editor can't load", async () => {
    vi.resetModules();
    fields.length = 0;
    const user = userEvent.setup();
    // Make the dynamic import fail for this test only.
    vi.doMock("mathlive", () => {
      throw new Error("offline");
    });
    const { StepEditor: Fresh } = await import("./StepEditor");
    render(<Fresh onSubmit={vi.fn()} showExamples={false} />);
    await user.click(screen.getAllByRole("button", { name: "Visual editor" }).at(-1)!);
    expect((await screen.findAllByText(/couldn't load/)).length).toBeGreaterThan(0);
    vi.doUnmock("mathlive");
  });
});
