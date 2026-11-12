export type Example = { id: string; title: string; description: string; steps: string[] };

export const EXAMPLES: Example[] = [
  {
    id: "correct-linear",
    title: "Correct linear solution",
    description: "Every step is valid and the answer is complete.",
    steps: ["2x + 5 = 15", "2x = 10", "x = 5"],
  },
  {
    id: "first-error",
    title: "Arithmetic slip",
    description: "15 − 5 is simplified incorrectly in step 3.",
    steps: ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"],
  },
  {
    id: "lost-root",
    title: "Lost quadratic solution",
    description: "One factor is dropped, losing the root x = 3.",
    steps: ["x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0", "x = 2"],
  },
];
