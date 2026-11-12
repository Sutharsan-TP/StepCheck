# StepCheck frontend

Next.js (App Router) + TypeScript + Tailwind CSS. See the repository README for full setup.

```bash
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                         # http://localhost:3000
```

| Script | Purpose |
|---|---|
| `npm run gen:api` | Regenerate `src/lib/api-schema.ts` from the backend's OpenAPI schema |
| `npm run check:api` | Fail if the generated types are out of date |
| `npm run lint` / `npm run typecheck` | ESLint / TypeScript |
| `npm run test` | Unit and component tests (Vitest + Testing Library) |
| `npm run e2e` | End-to-end tests (Playwright; starts the backend with the offline AI stub) |
