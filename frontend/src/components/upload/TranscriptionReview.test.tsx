import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { TranscriptionResponse } from "@/lib/types";
import transcription from "@/test/fixtures/transcribe-demo2.json";

import { TranscriptionReview } from "./TranscriptionReview";
import { validateImage } from "./ImageDropzone";

const data = transcription as TranscriptionResponse;

describe("TranscriptionReview", () => {
  it("highlights flagged lines and never confirms until they are checked", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<TranscriptionReview transcription={data} imageSrc={null} onConfirm={onConfirm} onCancel={vi.fn()} />);

    const confirm = screen.getByRole("button", { name: /confirm transcription/i });
    expect(confirm).toBeDisabled();
    expect(screen.getByText(/1 highlighted line still needs checking/)).toBeInTheDocument();
    expect(screen.getByText(/The last digit is faint/)).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: /checked this line/i }));
    expect(confirm).toBeEnabled();
    expect(onConfirm).not.toHaveBeenCalled(); // nothing is submitted automatically
  });

  it("submits exactly the reviewed (edited) lines", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<TranscriptionReview transcription={data} imageSrc={null} onConfirm={onConfirm} onCancel={vi.fn()} />);

    const last = screen.getByLabelText("Transcribed step 4");
    await user.clear(last);
    await user.type(last, "x = 5");
    await user.click(screen.getByRole("checkbox", { name: /checked this line/i }));
    await user.click(screen.getByRole("button", { name: /confirm transcription/i }));

    expect(onConfirm).toHaveBeenCalledWith(["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 5"]);
  });
});

describe("validateImage", () => {
  const file = (type: string, size: number) => new File([new Uint8Array(size)], "f", { type });

  it("accepts JPEG, PNG and WebP up to 5 MB", () => {
    expect(validateImage(file("image/png", 100))).toBeNull();
    expect(validateImage(file("image/webp", 100))).toBeNull();
  });

  it("rejects other types, empty and oversized files", () => {
    expect(validateImage(file("image/gif", 100))).toMatch(/JPEG, PNG or WebP/);
    expect(validateImage(file("image/png", 5 * 1024 * 1024 + 1))).toMatch(/larger than 5 MB/);
    expect(validateImage(file("image/png", 0))).toMatch(/empty/);
  });
});
