import type { SolutionSetOut } from "@/lib/types";

export const REASON_LABELS: Record<string, string> = {
  LOST_SOLUTIONS: "This step loses solutions.",
  EXTRANEOUS_SOLUTIONS: "This step adds solutions that weren't there before.",
  SOLUTIONS_CHANGED: "This step changes the solutions.",
  BECAME_IDENTITY: "This step turns the equation into one that is true for every x.",
  BECAME_CONTRADICTION: "This step turns the equation into one with no solution.",
  LOST_IDENTITY: "The equation was true for every x, but this step isn't.",
  AMBIGUOUS_ERROR_LOCATION: "Something changed after a step StepCheck couldn't check, so the exact mistake can't be pinpointed.",
  AFTER_UNRESOLVED_STEP: "Comes after a problem StepCheck couldn't locate.",
  NO_VERIFIED_REFERENCE: "The problem itself couldn't be checked.",
  NOT_EQUAL: "This step doesn't have the same value as the step before it.",
  DIFFERS_BY_NON_CONSTANT: "This differs from the step before by more than a constant, so it isn't the same integral.",
  CANNOT_DECIDE: "StepCheck couldn't decide whether this step equals the one before it.",
  UNDEFINED: "A value or limit here is undefined (for example a two-sided limit that doesn't exist).",
  TIMEOUT: "This step took too long to check.",
};

export const TOPIC_LABELS: Record<string, string> = {
  ALGEBRA: "Equation",
  DERIVATIVE: "Derivative",
  INTEGRAL: "Indefinite integral",
  DEFINITE_INTEGRAL: "Definite integral",
  LIMIT: "Limit",
};

export const isCalculus = (topic: string | null | undefined) => Boolean(topic && topic !== "ALGEBRA");

export const CATEGORY_LABELS: Record<string, string> = {
  ADDITION_SUBTRACTION_ERROR: "Addition or subtraction slip",
  MULTIPLICATION_DIVISION_ERROR: "Multiplication or division slip",
  EXPANSION_ERROR: "Expanding brackets",
  COMBINING_LIKE_TERMS_ERROR: "Combining like terms",
  SIGN_ERROR_MOVING_TERM: "Sign error when moving a term",
  INCONSISTENT_OPERATION: "Different operations on each side",
  FACTORIZATION_ERROR: "Factorization",
  QUADRATIC_FORMULA_ERROR: "Quadratic formula",
  LOST_FACTOR: "Dropped a factor",
  DIVIDED_BY_VARIABLE: "Divided by x",
  MISSING_NEGATIVE_ROOT: "Missing the negative square root",
  INCOMPLETE_FINAL_ANSWER: "Incomplete answer",
  EXTRANEOUS_SOLUTIONS: "Extra solutions introduced",
  INCORRECT_FINAL_ANSWER: "Incorrect final answer",
  PRODUCT_RULE_ERROR: "Product rule",
  QUOTIENT_RULE_ERROR: "Quotient rule",
  CHAIN_RULE_ERROR: "Chain rule",
  POWER_RULE_ERROR: "Power rule",
  TRIG_DERIVATIVE_SIGN_ERROR: "Sign of a trig derivative",
  INTEGRAL_POWER_RULE_ERROR: "Power rule for integrals",
  INTEGRAL_COEFFICIENT_ERROR: "Dividing by the inner coefficient",
  INTEGRAL_TRIG_SIGN_ERROR: "Sign of a trig integral",
  LIMITS_SWAPPED: "Limits of integration swapped",
  EVALUATION_ERROR: "Substituting the limits",
  LHOPITAL_NOT_APPLICABLE: "L'Hôpital's rule used when it doesn't apply",
  LHOPITAL_QUOTIENT_ERROR: "L'Hôpital's rule applied as the quotient rule",
  SIMPLIFICATION_ERROR: "Simplifying",
  MISSING_CONSTANT: "Missing + C",
  NOT_FINISHED: "Not finished",
  GENERAL_ERROR: "Invalid step",
};

export function categoryLabel(category: string | null | undefined): string | null {
  return category ? (CATEGORY_LABELS[category] ?? category.replaceAll("_", " ").toLowerCase()) : null;
}

/** LaTeX for a solution set, e.g. x ∈ {2, 3}, x ∈ ℝ or ∅. */
export function solutionSetLatex(set: SolutionSetOut | null | undefined): string {
  if (!set) return "\\text{—}";
  if (set.type === "ALL_REAL") return "x \\in \\mathbb{R}";
  if (set.type === "EMPTY") return "\\varnothing";
  return `x \\in \\{${set.latex.join(",\\ ")}\\}`;
}

export function solutionSetText(set: SolutionSetOut | null | undefined): string {
  if (!set) return "unknown";
  if (set.type === "ALL_REAL") return "all real numbers";
  if (set.type === "EMPTY") return "no real solution";
  return set.values.map((v) => `x = ${v}`).join(" or ");
}

export function valuesLatex(values: string[] | null | undefined, latex?: string[]): string {
  if (!values?.length) return "";
  return (latex ?? values).map((v) => `x = ${v}`).join(",\\ ");
}
