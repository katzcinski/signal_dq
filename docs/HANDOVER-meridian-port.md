# Handover — Meridian → Signal port (open points)

*Status: 2026-06-14 · full test suite: **308 passed, 0 failed** (Windows, Py 3.14)*

Porting proven mechanisms from **Meridian** (`datasphere-tools`, the SAP-Datasphere
connectivity/extraction engine) into **Signal** (FastAPI + React cockpit, framework-free
`dq_core`). The two are complementary — Signal stays the governance/observability product;
Meridian supplies live-data plumbing. **Scope is read-only** (no flows / transport / DEV-PROD
delta). Data policy: **port code only, never customer data** (no populated `.env`, `profiles/*`,
keyring secrets, or `transport/releases/*`).

---

## Done & verified

- **Column-lineage chain** (resolves the tracked **O3** defect): `dq_core/lineage/_sql_column_parser.py`,
  `_csn_reconstructor.py`, `_column_lineage.py` — SQL (sqlglot, optional) + CSN → `columnEdges`.
- **HANA connector hardening**: `dq_core/connect/db_connection.get_connection` — transient retry +
  `statementTimeout`, S-13 fail-closed `RuntimeError` + `MockConnection` preserved.
- **Connectivity**: `services/api/datasphere_catalog.py` (REST/OAuth catalog, default),
  `services/api/datasphere_cli.py` (`@sap/datasphere-cli` wrapper, optional via `DATASPHERE_USE_CLI`),
  `services/api/secrets.py` (env-backed, vault-ready `SecretResolver`; `get_environment` resolves
  `password_ref: env:VAR`).
- **Extraction**: `services/api/extraction.py` + gated `POST /api/extract` — writes Meridian-shaped
  `inventory.json` / `lineage.json` when REST/CLI configured; local mtime-touch fallback otherwise.
- **Column-lineage API**: `GET /api/lineage/columns?object=&column=`.
- **Profiling**: `dq_core/profile/*` + `dq_core/connect/query_helpers.py`, exposed via
  `POST /api/objects/{id}/profile` (steward+, fail-closed on no env). Per-column stats + PK
  candidates + heuristic key scores.

---

## Open points (prioritized)

### 1. Frontend cockpit (the main remaining feature — option "a")
- **Surface column-level lineage**: build a column view consuming `GET /api/lineage/columns`
  (compound graph: object = parent, columns = children, edges colored by `edgeType`; click-to-trace).
  Reference UX: Meridian `datasphere_column_lineage_viewer.py`. Signal already uses cytoscape+dagre.
- **Adopt the richer node schema**: backend now emits `layer:string` / `layerCode` / `role` /
  `confidence` / `columns[]`, but `apps/cockpit/src/pages/LineageMap.tsx` still **hard-codes
  `layer:int` 0-2 and `LAYERS[3]`** and ignores `edge.type`. Needs a lane-derivation change in the FE
  + `apps/cockpit/src/types/index.ts`.
  - **Open decision**: clean cutover vs. back-compat adapter mapping new→old shape during migration.
- **Profiling UI**: a panel that calls `POST /api/objects/{id}/profile` and renders column stats +
  key candidates (the endpoint is ready).

### 2. Snapshot/compare/diff validator (counts-only)
- Not yet ported. Source: Meridian `datasphere_data_validator.py` (`gather_stats`, `cmd_compare`
  row-ratio fan-out > 1.05, `cmd_diff` SQL `EXCEPT`, `get_key_cardinality`).
- **PII gate**: keep row-level `EXCEPT` **counts-only / non-sensitive columns** (or behind the
  diagnostics allow-list). Target: `dq_core/validator/` (framework-free) + an API route.
- Also unported: the **fan-out / cardinality guardrail** as a `check_library.json` template.

### 3. Live-tenant validation (connectivity is mock-tested only)
- REST catalog endpoints are **best-effort guesses** verified only against `respx` mocks:
  - `read_object_definition` uses `$expand=definition` — **may not return full CSN**; in practice the
    **CLI path is needed for column lineage**. Verify on a real tenant.
  - **Pagination** (`@odata.nextLink`) is **not handled** — large spaces truncate to the first page.
- CLI wrapper is a faithful port but never run against the real `@sap/datasphere-cli` here.
- Broadening Datasphere access beyond read-only status may need **additional OAuth scopes**.

### 4. Deferred by scope / single-tenant
- **Multi-tenant profiles resolver** (Meridian `db_credentials.py` / `config.py`): only needed if
  Signal targets multiple HANA/Datasphere tenants. Single `DATASPHERE_*` + `environments.yml` suffices
  for now.
- **Flows / DEV-PROD delta / full transport lifecycle**: intentionally **out of scope** (read-only
  decision). Re-open only if Signal moves into write/transport operations.
- **Scheduler/queue**: extraction runs synchronously in the request threadpool; no durable job queue.
  Large spaces could be slow — fine for now, revisit if needed.

---

## Constraints & gotchas

- **`dq_core` is framework-free (CI gate G7)** — no `fastapi`/`pydantic`/`starlette`/`typer`/`rich`/`pandas`.
  Validator/profiler ports must stay pure (cursor-in, dict-out). Connectivity/orchestration lives in
  `services/api/`.
- **Optional deps** (commented in `services/requirements.txt`): `hdbcli` (live HANA) and `sqlglot`
  (SQL column lineage) — both degrade gracefully when absent. The optional CLI path needs Node +
  `@sap/datasphere-cli` installed and an interactive `datasphere login` on the host.
- **Dev env**: Python 3.14; backend deps were `pip install`ed ad-hoc — consider pinning them.
- **Secrets**: env-backed now; `services/api/secrets.py` is vault-ready (implement a
  `VaultSecretResolver` satisfying the Protocol and swap the default).

## How to verify
```
python -m pytest -q          # full suite (308 passing)
# Live smoke (needs config): set DATASPHERE_* (+ DATASPHERE_USE_CLI=true for CLI),
# then POST /api/extract and inspect data/lineage.json columnEdges.
```
