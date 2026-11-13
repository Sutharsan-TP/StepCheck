import { resolve } from "node:path";

import { expect, type Page, test } from "@playwright/test";

const SAMPLES = resolve(__dirname, "../../examples/handwritten_samples");
const SHOTS = resolve(__dirname, ".artifacts/screens");

function statuses(page: Page) {
  return page.locator("li[data-status]").evaluateAll((items) => items.map((li) => li.getAttribute("data-status")));
}

async function loadExample(page: Page, title: string) {
  await page.goto("/workspace");
  await page.getByRole("button", { name: title, exact: true }).click();
  await page.getByRole("button", { name: "Check my steps" }).click();
  await expect(page).toHaveURL(/\/results$/);
}

/** Put LaTeX into the nth visual field the way typing would: set its value and fire `input`. */
async function setVisual(page: Page, index: number, latex: string) {
  await page.locator("math-field").nth(index).evaluate((el, value) => {
    (el as unknown as { value: string }).value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }, latex);
}

async function openVisualEditor(page: Page) {
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Visual editor", exact: true }).click();
  await expect(page.locator('[data-testid="visual-field"][data-state="ready"]')).toHaveCount(2);
}

test("a calculus mistake is found, explained, and corrections are marked as coming", async ({ page }) => {
  await loadExample(page, "Product rule slip");
  await expect(page.getByRole("heading", { name: "Mistake found" })).toBeVisible();
  await expect(page.getByText("A step changes the value of the expression.")).toBeVisible();
  expect(await statuses(page)).toEqual(["VALID", "FIRST_INVALID", "DOWNSTREAM_DEPENDENT"]);

  const first = page.locator('li[data-status="FIRST_INVALID"]');
  await expect(first.getByText("This step works out to:")).toBeVisible();
  await expect(first.getByText("It should equal:")).toBeVisible();
  await expect(page.getByText("Correct answer")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/calculus-results.png`, fullPage: true });

  await page.getByRole("button", { name: /Explain mistake/ }).click();
  await expect(page.getByRole("region", { name: "Help with this solution" }).getByText("Product rule", { exact: true })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/calculus-explain.png`, fullPage: true });

  for (const name of [/Guide me through it/, /Show corrected solution/, /Compare my work/]) {
    await expect(page.getByRole("button", { name })).toBeDisabled();
  }
  await expect(page.getByText("Coming soon for calculus").first()).toBeVisible();
});

test("an indefinite integral without + C is unfinished", async ({ page }) => {
  await loadExample(page, "Missing + C");
  await expect(page.getByRole("heading", { name: "Unfinished" })).toBeVisible();
  await expect(page.getByText(/add \+ C to finish/)).toBeVisible();
  await expect(page.getByText("No — add + C")).toBeVisible();
});

test("a definite integral and a limit are checked", async ({ page }) => {
  await loadExample(page, "Definite integral");
  await expect(page.getByRole("heading", { name: "Correct" })).toBeVisible();
  expect(await statuses(page)).toEqual(["VALID", "VALID", "VALID", "VALID"]);
  await expect(page.getByText("Nothing to correct")).toBeVisible();

  await loadExample(page, "Limit with L'Hôpital");
  await expect(page.getByRole("heading", { name: "Correct" })).toBeVisible();
  await expect(page.getByText("Limit", { exact: true }).first()).toBeVisible();
});

test("the calculator keypad types calculus into the focused step", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByLabel("Problem", { exact: true }).click();
  await page.getByRole("tab", { name: "Calculus" }).click();
  await page.getByRole("button", { name: "derivative" }).click();
  await page.keyboard.type("x^3");
  await expect(page.getByLabel("Problem", { exact: true })).toHaveValue("d/dx(x^3)");

  await page.getByLabel("Step 2", { exact: true }).click();
  await page.getByRole("tab", { name: "Basic" }).click();
  await page.getByRole("button", { name: "3", exact: true }).click();
  await page.getByRole("button", { name: "x", exact: true }).click();
  await page.getByRole("button", { name: "squared" }).click();
  await expect(page.getByLabel("Step 2", { exact: true })).toHaveValue("3x^2");
  await page.screenshot({ path: `${SHOTS}/calculus-keypad.png`, fullPage: true });

  await page.getByRole("button", { name: "Check my steps" }).click();
  await expect(page.getByRole("heading", { name: "Correct" })).toBeVisible();
});

test("the visual editor builds the same steps and finds the same mistake", async ({ page }) => {
  await openVisualEditor(page);
  await setVisual(page, 0, "\\frac{d}{dx}\\left(x^{2}\\sin\\left(x\\right)\\right)");
  await setVisual(page, 1, "2x\\cos\\left(x\\right)");
  await expect(page.getByRole("list", { name: "Solution steps" }).getByText("d/dx(x^2 sin(x))")).toBeVisible();
  await expect(page.getByRole("list", { name: "Solution steps" }).getByText("2x cos(x)")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/calculus-visual.png`, fullPage: true });

  await page.getByRole("button", { name: "Check my steps" }).click();
  await expect(page.getByRole("heading", { name: "Mistake found" })).toBeVisible();
  expect(await statuses(page)).toEqual(["VALID", "FIRST_INVALID"]);
});

test("the visual editor accepts real typing and refuses what it can't read", async ({ page }) => {
  await openVisualEditor(page);
  await page.locator("math-field").nth(0).click();
  await expect.poll(() => page.evaluate(() => (document.querySelector("math-field") as unknown as { hasFocus(): boolean }).hasFocus())).toBe(true);
  await page.keyboard.type("2x+5=15", { delay: 40 }); // keys sent faster than the field can focus are dropped
  await expect(page.getByRole("list", { name: "Solution steps" }).getByText("2x + 5 = 15")).toBeVisible();

  await setVisual(page, 1, "\\sum_{i=1}^{n}i");
  await expect(page.getByText(/isn't supported/)).toBeVisible();
  await page.getByRole("button", { name: "Check my steps" }).click();
  await expect(page).toHaveURL(/\/workspace$/);
  await expect(page.getByText(/Fix the steps marked in red/)).toBeVisible();

  await setVisual(page, 1, "x=5");
  await page.getByRole("button", { name: "Check my steps" }).click();
  await expect(page.getByRole("heading", { name: "Correct" })).toBeVisible();
});

test("the visual editor's keyboard has a calculus layout", async ({ page }) => {
  await openVisualEditor(page);
  const labels = await page.evaluate(() =>
    (window as unknown as { mathVirtualKeyboard: { layouts: unknown[] } }).mathVirtualKeyboard.layouts.map((l) =>
      typeof l === "string" ? l : (l as { label?: string }).label,
    ),
  );
  expect(labels).toContain("Calculus");
});

test("the chosen input mode is remembered after a reload and can be switched back", async ({ page }) => {
  await page.goto("/workspace");
  await expect(page.getByRole("button", { name: "Keypad", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Visual editor", exact: true }).click();
  await page.reload();
  await expect(page.getByRole("button", { name: "Visual editor", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator('[data-testid="visual-field"][data-state="ready"]')).toHaveCount(2);

  await page.getByRole("button", { name: "Keypad", exact: true }).click();
  await expect(page.getByLabel("Problem", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Maths keypad")).toBeVisible();
});

test("handwritten calculus: reviewed, then checked like typed work", async ({ page }) => {
  await page.goto("/workspace");
  await page.getByRole("tab", { name: "Upload photo" }).click();
  await page.getByTestId("image-input").setInputFiles(`${SAMPLES}/demo4_calculus.png`);
  await expect(page.getByText("Check the transcription")).toBeVisible();
  await expect(page.locator("li[data-flagged]")).toHaveCount(1);
  await page.getByRole("checkbox", { name: /checked this line/ }).check();
  await page.getByRole("button", { name: "Confirm transcription" }).click();
  await expect(page).toHaveURL(/\/results$/);
  await expect(page.getByRole("heading", { name: "Mistake found" })).toBeVisible();
  expect(await statuses(page)).toEqual(["VALID", "FIRST_INVALID", "DOWNSTREAM_DEPENDENT"]);
});

test("phone layout: keypad and calculus results fit without horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/workspace");
  await page.getByLabel("Problem", { exact: true }).click();
  await page.getByRole("tab", { name: "Calculus" }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: `${SHOTS}/mobile-keypad.png`, fullPage: true });

  await page.getByRole("button", { name: "Visual editor", exact: true }).click();
  await expect(page.locator('[data-testid="visual-field"][data-state="ready"]')).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

  await page.getByRole("button", { name: "Keypad", exact: true }).click();
  await page.getByRole("button", { name: "Definite integral", exact: true }).click();
  await page.getByRole("button", { name: "Check my steps" }).click();
  await expect(page.getByRole("heading", { name: "Correct" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: `${SHOTS}/mobile-calculus-results.png`, fullPage: true });
});
