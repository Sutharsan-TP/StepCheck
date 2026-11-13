import { resolve } from "node:path";

import { expect, type Page, test } from "@playwright/test";

const SAMPLES = resolve(__dirname, "../../examples/handwritten_samples");
const SHOTS = resolve(__dirname, ".artifacts/screens");

async function enterSteps(page: Page, steps: string[]) {
  await page.goto("/workspace");
  for (let i = 0; i < steps.length; i++) {
    if (i >= 2) await page.getByRole("button", { name: `Add step below step ${i}` }).click();
    await page.getByLabel(i === 0 ? "Problem" : `Step ${i + 1}`, { exact: true }).fill(steps[i]);
  }
  await page.getByRole("button", { name: "Check my steps" }).click();
  await expect(page).toHaveURL(/\/results$/);
}

function statuses(page: Page) {
  return page.locator("li[data-status]").evaluateAll((items) => items.map((li) => li.getAttribute("data-status")));
}

test("landing page leads to the workspace", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("exact step");
  await expect(page.getByText("What StepCheck supports")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/landing.png`, fullPage: true });
  await page.getByRole("link", { name: "Check my solution" }).click();
  await expect(page).toHaveURL(/\/workspace$/);
});

test("demo 1: a correct linear solution", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Correct linear solution" }).click();
  await page.screenshot({ path: `${SHOTS}/workspace.png`, fullPage: true });
  await page.getByRole("button", { name: "Check my steps" }).click();
  await expect(page.getByRole("heading", { name: "Correct" })).toBeVisible();
  expect(await statuses(page)).toEqual(["VALID", "VALID", "VALID"]);
  await expect(page.getByText("Nothing to correct")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/results-correct.png`, fullPage: true });
});

test("demo 2: first-error detection, explanation, correction and comparison", async ({ page }) => {
  await enterSteps(page, ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"]);
  await expect(page.getByRole("heading", { name: "Mistake found" })).toBeVisible();
  expect(await statuses(page)).toEqual(["VALID", "VALID", "FIRST_INVALID", "DOWNSTREAM_DEPENDENT"]);
  await expect(page.locator('li[data-status="FIRST_INVALID"]').getByText("Lost:")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/results-demo2.png`, fullPage: true });

  await page.getByRole("button", { name: /Explain mistake/ }).click();
  await expect(page.getByText("Explained by AI from StepCheck's verified result")).toBeVisible();
  await expect(page.getByText("Addition or subtraction slip")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/explain.png`, fullPage: true });

  await page.getByRole("button", { name: /Show corrected solution/ }).click();
  const corrected = page.locator('li[data-source="CORRECTED"]');
  await expect(corrected).toContainText("Corrected");
  await expect(corrected.getByRole("math", { name: "2x = 10" })).toBeVisible();
  await expect(page.getByText(/re-checked by StepCheck/)).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/correction.png`, fullPage: true });

  await page.getByRole("button", { name: /Compare my work/ }).click();
  const changes = await page.locator("tr[data-change]").evaluateAll((rows) => rows.map((r) => r.getAttribute("data-change")));
  expect(changes).toEqual(["same", "same", "fixed", "fixed"]);
});

test("demo 3: lost quadratic root and incomplete answer", async ({ page }) => {
  await enterSteps(page, ["x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0", "x = 2"]);
  expect(await statuses(page)).toEqual(["VALID", "VALID", "FIRST_INVALID", "DOWNSTREAM_DEPENDENT"]);
  await expect(page.getByText("Not complete")).toBeVisible();
  await expect(page.getByText("Missing", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Show corrected solution/ }).click();
  await expect(page.getByText("Dropped a factor.")).toBeVisible();
  await expect(page.locator('li[data-source="CORRECTED"]').getByRole("math", { name: "x - 2 = 0 or x - 3 = 0" })).toBeVisible();
});

test("handwritten upload: review is required before verification", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByRole("tab", { name: "Upload photo" }).click();
  await page.getByTestId("image-input").setInputFiles(`${SAMPLES}/demo2_first_error.png`);

  await expect(page.getByText("Check the transcription")).toBeVisible();
  const confirm = page.getByRole("button", { name: "Confirm transcription" });
  await expect(confirm).toBeDisabled();
  await expect(page.locator("li[data-flagged]")).toHaveCount(1);
  await page.screenshot({ path: `${SHOTS}/review.png`, fullPage: true });
  await expect(page).toHaveURL(/\/workspace$/); // nothing submitted automatically

  await page.getByRole("checkbox", { name: /checked this line/ }).check();
  await confirm.click();
  await expect(page).toHaveURL(/\/results$/);
  await expect(page.getByRole("heading", { name: "Mistake found" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Uploaded handwritten working" })).toBeVisible();
});

test("guided correction: hints, a rejected attempt, then solved", async ({ page }) => {
  await enterSteps(page, ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"]);
  await page.getByRole("button", { name: /Guide me through it/ }).click();
  await expect(page.getByText("Hint 1 of 3")).toBeVisible();

  const attempt = page.getByLabel("Your next step");
  await attempt.fill("2x = 11");
  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByText("Not quite")).toBeVisible();

  await page.getByRole("button", { name: /another hint/ }).click();
  await expect(page.getByText("Hint 2 of 3")).toBeVisible();

  await attempt.fill("2x = 10");
  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByText("Correct!", { exact: true })).toBeVisible();

  await attempt.fill("x = 5");
  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByText("Verified final answer")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/guided-solved.png`, fullPage: true });
});

test("an answer that was already complete: remove the extra step", async ({ page }) => {
  await enterSteps(page, ["2x + 5 = 15", "2x = 10", "x = 5", "x = 10"]);
  await expect(page.getByText("Your answer was already complete at step 3.")).toBeVisible();
  await page.getByRole("button", { name: /Show corrected solution/ }).click();
  await expect(page.getByText(/already complete at step 3/).first()).toBeVisible();
  await expect(page.getByText(/Step 4 removed/)).toBeVisible();
});

test("unsupported mathematics is reported, not guessed", async ({ page }) => {
  await enterSteps(page, ["x^3 = 8", "x = 2"]);
  await expect(page.getByRole("heading", { name: "Unsupported" })).toBeVisible();
  await page.getByRole("button", { name: /Show corrected solution/ }).click();
  await expect(page.getByText("No verified correction available")).toBeVisible();
});

test("results survive a page refresh", async ({ page }) => {
  await enterSteps(page, ["2x + 5 = 15", "2x = 10", "x = 5"]);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Correct" })).toBeVisible();
  await page.getByRole("link", { name: "Edit steps" }).click();
  await expect(page.getByLabel("Problem", { exact: true })).toHaveValue("2x + 5 = 15");
});

test("phone layout has no horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ["/", "/workspace"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  }
  await enterSteps(page, ["x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0", "x = 2"]);
  await page.getByRole("button", { name: /Show corrected solution/ }).click();
  await expect(page.getByText(/re-checked by StepCheck/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: `${SHOTS}/mobile-results.png`, fullPage: true });
});
