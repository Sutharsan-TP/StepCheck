// Runs once after the dev servers are up. `next dev` compiles each route on first visit and the
// calculus worker imports SymPy on first use; doing both here keeps that cost out of the first
// tests' timeouts (it can take a minute on a busy machine).
const FRONTEND = `http://127.0.0.1:${process.env.E2E_FRONTEND_PORT ?? 3100}`;
const BACKEND = `http://127.0.0.1:${process.env.E2E_BACKEND_PORT ?? 8765}`;
const PATIENT = AbortSignal.timeout.bind(AbortSignal, 180_000);

export default async function globalSetup() {
  for (const path of ["/", "/workspace", "/results"]) {
    await fetch(`${FRONTEND}${path}`, { signal: PATIENT() }).catch(() => undefined);
  }
  await fetch(`${BACKEND}/api/v1/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ steps: ["d/dx(x^2 sin(x))", "2x cos(x)"] }),
    signal: PATIENT(),
  }).catch(() => undefined);
}
