export type Example = { id: string; group: "Algebra" | "Calculus"; title: string; description: string; steps: string[] };

export const EXAMPLES: Example[] = [
  {
    id: "correct-linear",
    group: "Algebra",
    title: "Correct linear solution",
    description: "Every step is valid and the answer is complete.",
    steps: ["2x + 5 = 15", "2x = 10", "x = 5"],
  },
  {
    id: "first-error",
    group: "Algebra",
    title: "Arithmetic slip",
    description: "15 − 5 is simplified incorrectly in step 3.",
    steps: ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"],
  },
  {
    id: "lost-root",
    group: "Algebra",
    title: "Lost quadratic solution",
    description: "One factor is dropped, losing the root x = 3.",
    steps: ["x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0", "x = 2"],
  },
  {
    id: "product-rule",
    group: "Calculus",
    title: "Product rule",
    description: "A correct derivative using the product rule.",
    steps: ["d/dx(x^2 sin(x))", "d/dx(x^2) sin(x) + x^2 d/dx(sin(x))", "2x sin(x) + x^2 cos(x)"],
  },
  {
    id: "product-rule-slip",
    group: "Calculus",
    title: "Product rule slip",
    description: "The two derivatives are multiplied together in step 2.",
    steps: ["d/dx(x^2 sin(x))", "d/dx(x^2) d/dx(sin(x))", "2x cos(x)"],
  },
  {
    id: "chain-rule-slip",
    group: "Calculus",
    title: "Chain rule slip",
    description: "The derivative of the inside is forgotten.",
    steps: ["d/dx(sin(x^2))", "cos(x^2)"],
  },
  {
    id: "missing-constant",
    group: "Calculus",
    title: "Missing + C",
    description: "A correct antiderivative without the constant of integration.",
    steps: ["int(2x) dx", "x^2"],
  },
  {
    id: "definite-integral",
    group: "Calculus",
    title: "Definite integral",
    description: "Evaluating an antiderivative between limits.",
    steps: ["int[0, 2](x^2) dx", "[x^3/3][0, 2]", "8/3 - 0", "8/3"],
  },
  {
    id: "standard-limit",
    group: "Calculus",
    title: "Limit with L'Hôpital",
    description: "A 0/0 limit solved with L'Hôpital's rule.",
    steps: ["lim(x->0, sin(x)/x)", "lim(x->0, cos(x)/1)", "1"],
  },
];
