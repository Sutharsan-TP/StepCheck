import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import guided from "@/test/fixtures/guided-demo2.json";
import { mockFetch } from "@/test/fetch";

import { GuidedPanel } from "./GuidedPanel";

const STEPS = ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"];
const work = { verificationId: null, steps: STEPS };

describe("GuidedPanel", () => {
  it("escalates hints and reveals the step only at level 3", async () => {
    const user = userEvent.setup();
    const calls = mockFetch({ body: guided.start }, { body: guided.hint2 }, { body: guided.reveal });
    render(<GuidedPanel work={work} />);

    expect(await screen.findByText("Hint 1 of 3")).toBeInTheDocument();
    expect(screen.queryByText("Answer")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /another hint/i }));
    expect(await screen.findByText("Hint 2 of 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /show me this step/i }));
    expect(await screen.findByText("Answer")).toBeInTheDocument();
    expect(calls.map((c) => c.body?.hint_level)).toEqual([1, 2, 3]);
    expect(calls.every((c) => c.body?.mode === "GUIDED")).toBe(true);
  });

  it("explains a rejected attempt", async () => {
    const user = userEvent.setup();
    mockFetch({ body: guided.start }, { body: guided.rejected });
    render(<GuidedPanel work={work} />);
    await user.type(await screen.findByLabelText("Your next step"), "2x = 11");
    await user.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByText("Not quite")).toBeInTheDocument();
    expect(screen.getByText(/loses x = 5/)).toBeInTheDocument();
  });

  it("sends server-issued progress and token back unchanged until solved", async () => {
    const user = userEvent.setup();
    const calls = mockFetch({ body: guided.start }, { body: guided.accepted }, { body: guided.solved });
    render(<GuidedPanel work={work} />);

    await user.type(await screen.findByLabelText("Your next step"), "2x = 10");
    await user.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByText("Correct!")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Your next step"), "x = 5");
    await user.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByText("Verified final answer")).toBeInTheDocument();

    expect(calls[1].body).toMatchObject({ attempt: "2x = 10", progress: [] });
    expect(calls[1].body?.progress_token).toBeUndefined();
    expect(calls[2].body).toMatchObject({
      attempt: "x = 5",
      progress: guided.accepted.guided.progress,
      progress_token: guided.accepted.guided.progress_token,
    });
  });
});
