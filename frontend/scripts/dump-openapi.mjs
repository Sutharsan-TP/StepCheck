// Regenerates frontend/openapi.json from the FastAPI app (backend is the contract's source of truth).
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const backend = resolve(here, "../../backend");
const candidates = [join(backend, ".venv/Scripts/python.exe"), join(backend, ".venv/bin/python")];
const python = candidates.find(existsSync) ?? "python";

const result = spawnSync(python, ["scripts/dump_openapi.py", resolve(here, "../openapi.json")], {
  cwd: backend,
  stdio: "inherit",
});
process.exit(result.status ?? 1);
