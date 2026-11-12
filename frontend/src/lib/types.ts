// Friendly aliases over the types generated from the backend's OpenAPI schema
// (src/lib/api-schema.ts, regenerated with `npm run gen:api`). Never edit the
// generated file by hand: the backend is the source of truth for the contract.
import type { components } from "./api-schema";

type Schemas = components["schemas"];

export type VerifyRequest = Schemas["VerifyRequest"];
export type VerifyResponse = Schemas["VerifyResponse"];
export type StepOut = Schemas["StepOut"];
export type TransitionOut = Schemas["TransitionOut"];
export type StepStatus = Schemas["StepStatus"];
export type OverallStatus = Schemas["OverallStatus"];
export type SolutionSetOut = Schemas["SolutionSetOut"];

export type CorrectRequest = Schemas["CorrectRequest"];
export type CorrectResponse = Schemas["CorrectResponse"];
export type FullCorrectionOut = Schemas["FullCorrectionOut"];
export type GuidedCorrectionOut = Schemas["GuidedCorrectionOut"];
export type CorrectionStepOut = Schemas["CorrectionStepOut"];
export type RemovedStepOut = Schemas["RemovedStepOut"];
export type AttemptFeedbackOut = Schemas["AttemptFeedbackOut"];

export type ExplainResponse = Schemas["ExplainResponse"];
export type TranscriptionResponse = Schemas["TranscriptionResponse"];
export type TranscribedStep = Schemas["TranscribedStep"];

export type ApiErrorBody = {
  error: { code: string; message: string; details?: { field: string; message: string }[] };
};
