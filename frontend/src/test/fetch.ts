import { vi } from "vitest";

export type Call = { url: string; body: Record<string, unknown> | null };

/** Stub global fetch with queued JSON responses and record every request. */
export function mockFetch(...responses: { status?: number; body: unknown; headers?: Record<string, string> }[]) {
  const calls: Call[] = [];
  const queue = [...responses];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const raw = typeof init?.body === "string" ? init.body : null;
      calls.push({ url, body: raw ? JSON.parse(raw) : null });
      const next = queue.shift();
      if (!next) throw new Error(`Unexpected fetch to ${url}`);
      return new Response(JSON.stringify(next.body), {
        status: next.status ?? 200,
        headers: { "Content-Type": "application/json", ...next.headers },
      });
    }),
  );
  return calls;
}
