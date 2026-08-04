# CLAUDE.md

Guidance for AI assistants working in the **Signal** repository — a Data
Quality & Observability Cockpit for **SAP Datasphere**. Read this before making
changes; it captures the architecture, the non-negotiable security gates, and
the workflows that CI enforces.

> Most existing source comments and docs are in **German**. Match the language
> of the surrounding code/comments when editing; user-facing strings in the
> frontend live in `apps/cockpit/src/i18n/de.ts`.

## What Signal does

Signal turns **SQL-free, semantic Data Contracts** (YAML) into deterministically
compiled, **read-only** quality checks that run against HANA/Datasphere. Results
surface in a React cockpit as a status grid, compliance traffic-light, lineage/
coverage map, incidents and data-driven guarantee proposals. It ships in two
operating modes on one codebase: **Lite** (binding without versioning/approval
ceremony) and **Full** (SemVer, approval, breaking-change protection).

The authoritative reference is [`docs/Tooldokumentation.md`](docs/Tooldokumentation.md).
See also [`docs/Betriebsmodi_Lite_und_Full.md`](docs/Betriebsmodi_Lite_und_Full.md);
the full doc index with per-document status (active vs. historical) is
[`docs/README.md`](docs/README.md), the consolidated backlog is
[`docs/OPEN_TASKS.md`](docs/OPEN_TASKS.md).

## Repository layout

```
packages/dq_core/      # Framework-free engine — pip-installable, ZERO web imports [ENGINE-FROZEN]
  engine/              #   check execution, expectation grammar, dataclasses (models.py)
  store/               #   Result-Store (SQLite/HANA) + numbered SQL migrations
  connect/             #   HANA connection (hdbcli) + MockConnection
  contract/            #   model, validator, compiler, diff, gate_g3, seed, ODCS export, compliance
  enforce/             #   enforcement/verdict materialization (DDL/DML plans, framework-free)
  library/             #   check library (sql_template catalog, check_library.json)
  lineage/             #   lineage / CSN analysis
  obs/                 #   rolling baselines + proposal miner
  product/             #   data-product aggregate (ADR-0004)
  profile/             #   data profiling + PK detection heuristics
  validator/           #   standalone validation building blocks
services/api/          # FastAPI app — routers, auth, settings, SSE, Git writer, Datasphere client
apps/cockpit/          # Vite + React 18 + TS (strict) frontend
cli/                   # dq_check_runner.py — run the engine without the API (cron/task-chain)
contracts/             # Contract YAMLs — Git is the source of truth
products/              # Data-product manifests (<name>.yaml — identity, owner, ports)
data/                  # inventory.json / lineage.json (extract snapshots)
scripts/               # seed.py, export_openapi.py
docs/                  # concepts, plans, ADRs, reviews, operating modes, tool reference
tests/                 # pytest: tests/unit (engine) + tests/api (FastAPI)
```

## Security gates — DO NOT VIOLATE

These are enforced by CI (`.github/workflows/ci.yml`) and are the project's core
invariants. Breaking one fails the build.

- **G1 — No SQL in contracts.** Contracts are purely semantic YAML
  (`guarantees:` families). The server validates them (`validate_contract`); SQL
  is only ever produced by the compiler.
- **G2 — Schema bound at runtime.** Never hardcode the `CENTRAL` schema (or any
  schema literal) in `packages/` or `services/`. Schema is injected via
  `bind_schema(...)` `[SCHEMA-MAP]`. CI greps for `"CENTRAL"` literals.
- **G3 — Breaking contract change requires a major bump.** On PRs, `gate_g3`
  diffs each changed contract against the merge-base; a breaking change without a
  major SemVer bump fails CI.
- **G6 — Gating states are never silently omitted.** Every `CheckResult.state`
  (`executed | skipped_stale | skipped_dependency | downgraded | error`) must be
  defined in `engine/models.py` and persisted by the store.
- **G7 — `dq_core` is framework-free.** Nothing under `packages/dq_core/` may
  import `fastapi`, `flask`, or `starlette`. The engine is `[ENGINE-FROZEN]`.
- **G8 — PII gate.** Raw rows never leave HANA without explicit opt-in.
  Diagnostics require per-check `diagnostics_enabled` + a column allowlist, and
  the store gates insertion behind `_allow_diagnostics`.
- **S5 — Fail-closed bind.** `AUTH_MODE=noauth` may only bind to loopback;
  `assert_bind_policy` in `services/api/main.py` raises at startup otherwise.

`[ENGINE-FROZEN]`, `[SCHEMA-MAP]`, `[PII-GATE]` markers in code flag these
invariants — respect them when editing nearby.

## Backend conventions

- Python **3.11+**, `from __future__ import annotations` everywhere.
- The engine (`dq_core`) uses **plain dataclasses**, no Pydantic, no web deps.
  The API layer uses Pydantic / FastAPI.
- Settings are centralized in `services/api/settings.py` (`pydantic-settings`,
  env-driven, `.env` supported). Use `get_settings()`; never read env vars ad hoc.
- DI via `services/api/deps.py` (`StoreDep`, inventory/lineage/environment
  loaders). No silent fallbacks — e.g. `STORE_BACKEND=hana` raises because
  `HanaStore` is a stub; configure `sqlite`.
- **Contract kinds** (`VALID_KINDS` in `contract/validator.py`):
  `internal_gate`, `consumer_contract`, `provider_contract`. `internal_gate`
  has no ODCS export.
- **Auth/roles**: `services/api/auth/provider.py`. Roles are
  `viewer | steward | owner | admin`. Guard write routes with
  `require_roles(...)`; inject the caller via `PrincipalDep`. In local NoAuth
  mode the principal is a fixed admin (override with `X-DQ-Role` header in dev).
- Errors are returned as **RFC-7807 `application/problem+json`**; internals go to
  logs, never the response body (S-14).
- Store schema changes go in **numbered migrations** under
  `packages/dq_core/store/migrations/` (e.g. `00N_description.sql`) — do not edit
  existing migrations.

## Frontend conventions

- Vite + React 18 + TypeScript **strict**. ESLint runs with `--max-warnings 0`
  (incl. `no-danger`, rules-of-hooks); lint must be clean.
- Data fetching via **@tanstack/react-query**; routing via `react-router-dom`
  with lazy-loaded pages (see `src/App.tsx`). State via `zustand`
  (`src/store/`).
- API client in `src/api/`; generated OpenAPI types in `src/api/schema.d.ts`
  (regenerate with `npm run gen:api`). The G4 OpenAPI→TS drift check is currently
  **advisory** (non-blocking) on feature branches.
- UI primitives live in `src/components/ui/`, layout in `src/components/layout/`,
  pages in `src/pages/`. Styling is CSS variables (`var(--fg)`, `var(--bg-2)`…)
  + Tailwind.
- All user-facing copy is German and centralized in `src/i18n/de.ts`.

## Build, run, test

```bash
make install          # backend deps (pip) + frontend deps (npm)
make dev-backend      # FastAPI on 127.0.0.1:8000 (docs at /api/docs)
make dev-frontend     # Vite on localhost:5173
SQLITE_DB=signal.db make seed   # seed demo data into the result store

# Tests (full suites)
make test             # python -m pytest tests/ -v --tb=short
cd apps/cockpit && npm run test -- --run   # vitest
cd apps/cockpit && npm run typecheck       # tsc --noEmit
cd apps/cockpit && npm run lint            # eslint, 0 warnings

# Single test (fast iteration)
python -m pytest tests/unit/test_compiler.py::test_bind_schema_resolves_placeholder -v  # one pytest case
python -m pytest tests/unit -k freshness                                # by keyword
cd apps/cockpit && npx vitest run src/tests/Governance.test.tsx         # one vitest file
cd apps/cockpit && npx vitest run -t "drills into breached"            # by test name
```

Run the engine standalone (no API), e.g. against the mock:

```bash
python cli/dq_check_runner.py --schema MY_SCHEMA --checks path/to/checks.yaml --mock
```

`pytest.ini` sets `pythonpath = . packages`, so `dq_core` imports resolve in
tests. In customer deployments `ALLOW_MOCK_CONNECTION` must be `false` (no silent
fail-open); locally it defaults to `true`.

### What CI checks (mirror locally before pushing)

`.github/workflows/ci.yml` has three jobs:
- **backend**: `tests/unit` (G5 engine regression), `tests/api` (G1/G2/G3 gates),
  contract-file validation, G3 breaking-change check (PRs), G7/G2/G6/G8 static
  checks, coverage.
- **odcs-second-opinion**: `datacontract-cli` advisory breaking check (PRs,
  non-blocking).
- **frontend**: G4 drift (advisory), `typecheck`, `lint`, `vitest`, `build` — all
  gating except G4.

Use `npm run typecheck`/the pinned compiler from `node_modules`, never bare
`npx tsc` (it would fetch a newer major).

## Git workflow

- Develop on the assigned feature branch; **never** push to `main` without
  explicit permission. Branches matching `claude/**` (and `main`) trigger CI.
- `contracts/` is the source of truth for contracts; the API writes contract
  changes back through the Git writer (`services/api/git_repo.py`) with the
  caller as author.
- Push with `git push -u origin <branch>`; retry transient network failures with
  exponential backoff. Do **not** open a PR unless explicitly asked.

## When adding features

- New API endpoint → add a router in `services/api/routers/`, register it in the
  `create_app()` router list in `main.py`, add request/response schemas under
  `services/api/schemas/`, and cover it under `tests/api/`.
- New guarantee/check semantics → extend the engine (`packages/dq_core/`) +
  `tests/unit/`, keeping `dq_core` framework-free (G7). Update the compiler and
  validator together so contracts stay SQL-free (G1).
- New frontend view → lazy page under `src/pages/`, route in `App.tsx`, API
  binding in `src/api/`, German strings in `i18n/de.ts`, and a vitest test.
- Store changes → new numbered migration; never mutate shipped migrations.
