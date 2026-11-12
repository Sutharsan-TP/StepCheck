import type {
  ApiErrorBody,
  CorrectRequest,
  CorrectResponse,
  ExplainResponse,
  TranscriptionResponse,
  VerifyResponse,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const DEFAULT_TIMEOUT_MS = 30_000;
const AI_TIMEOUT_MS = 90_000;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const NETWORK_MESSAGE = "StepCheck's server could not be reached. Check your connection and try again.";

async function request<T>(path: string, init: RequestInit, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1${path}`, { ...init, signal: controller.signal });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "AbortError";
    throw new ApiError(0, timedOut ? "TIMEOUT" : "NETWORK_ERROR", timedOut ? "The request took too long." : NETWORK_MESSAGE);
  } finally {
    clearTimeout(timer);
  }
  if (response.ok) return (await response.json()) as T;

  let body: Partial<ApiErrorBody> = {};
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    // non-JSON error (e.g. a proxy page): fall through to a generic message
  }
  const retryAfter = Number(response.headers.get("Retry-After")) || undefined;
  throw new ApiError(
    response.status,
    body.error?.code ?? "HTTP_ERROR",
    body.error?.message ?? `Request failed (${response.status}).`,
    retryAfter,
  );
}

function postJson<T>(path: string, payload: unknown, timeoutMs?: number): Promise<T> {
  return request<T>(
    path,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
    timeoutMs,
  );
}

export function verify(steps: string[]): Promise<VerifyResponse> {
  return postJson("/verify", { steps, variable: "x", domain: "REAL" });
}

export function transcribe(file: File): Promise<TranscriptionResponse> {
  const form = new FormData();
  form.append("file", file);
  return request("/transcribe", { method: "POST", body: form }, AI_TIMEOUT_MS);
}

/** Source of the original work: a stored verification id, falling back to the steps themselves. */
export type WorkRef = { verificationId?: string | null; steps: string[] };

const STALE_ID = new Set(["VERIFICATION_NOT_FOUND", "VERIFICATION_EXPIRED"]);

async function withWork<T>(work: WorkRef, send: (source: Record<string, unknown>) => Promise<T>): Promise<T> {
  if (work.verificationId) {
    try {
      return await send({ verification_id: work.verificationId });
    } catch (error) {
      // Stored verifications live in server memory and vanish on restart: resend the steps.
      if (!(error instanceof ApiError && STALE_ID.has(error.code))) throw error;
    }
  }
  return send({ steps: work.steps });
}

type CorrectOptions = Omit<CorrectRequest, "verification_id" | "steps" | "variable" | "domain">;

export function correct(work: WorkRef, options: CorrectOptions): Promise<CorrectResponse> {
  return withWork(work, (source) => postJson("/correct", { ...source, ...options }));
}

export function explain(work: WorkRef): Promise<ExplainResponse> {
  return withWork(work, (source) => postJson("/explain", source, AI_TIMEOUT_MS));
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "RATE_LIMITED" || error.code === "AI_RATE_LIMITED") {
      return error.retryAfter ? `${error.message} (try again in ${error.retryAfter}s)` : error.message;
    }
    return error.message;
  }
  return "Something went wrong. Please try again.";
}
