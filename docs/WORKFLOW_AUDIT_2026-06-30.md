# Signal workflow audit - 2026-06-30

Scope: exploratory workflow audit across the persona-facing surfaces in Signal:
definition/contract workbench, monitoring and extraction, object-contract views,
run/build execution, schedules, proposals, incidents, products, lineage/coverage,
notifications, environments, and the cockpit shell.

This document records findings for later revision. It does not apply fixes.

> **Backlog consolidation 2026-07-04:** Treat this as historical audit evidence.
> Active follow-up tracking is consolidated in [`OPEN_TASKS.md`](OPEN_TASKS.md)
> §M. Do not maintain a separate open-task list in this file.

## Persona workflow map tested

| Persona | Main workflow surfaces |
|---|---|
| Viewer / consumer | Cockpit `/`, objects, products, compliance, lineage/coverage, run details |
| Steward / platform team | Extract/inventory, seed/certify gates, run objects, schedules, incidents, proposals, monitoring request |
| Product owner | Full contract edit/approve/deprecate, compliance/SLA, proposals, product detail |
| Admin | Environment/connector settings, notifications, inventory admin, monitoring desired-state |

## Verification run

| Check | Result |
|---|---|
| `python -m pytest tests/ -v --tb=short` | Failed: 572 passed, 6 failed |
| `npm run typecheck` | Passed |
| `npm run lint` | Failed: 1 hook dependency error |
| `npm run test` | Passed: 35 files, 148 tests |
| `npm run build` | Passed, with Vite chunk-size warning |
| Shipped contract validation + compilation | Passed for all non-`.active.yml` contracts |
| Static G2/G7 spot checks | Passed: no hardcoded `CENTRAL`, no web framework imports in `dq_core` |
| Browser route smoke via Playwright | Passed route load for 19 cockpit routes; no page errors or 500s |
| OpenAPI in-memory drift check | Drift present: generated schema differs from `apps/cockpit/openapi.json` |
| CLI mock dry-run | Executed and returned a real critical DQ verdict, not a crash |

Backend failures observed:

- `tests/api/test_extract.py::test_extract_skipped_without_live_source`
- `tests/api/test_extract.py::test_extract_leaves_snapshot_untouched_without_live_source`
- `tests/api/test_extract.py::test_lineage_stays_stale_after_skipped_extract`
- `tests/api/test_r4_r5_endpoints.py::test_environments_no_secrets`
- `tests/unit/test_data_loads_space.py::test_resolve_space_falls_back_to_connector_file`
- `tests/unit/test_data_loads_space.py::test_resolve_space_empty_when_nothing_configured`

Frontend failure observed:

- `apps/cockpit/src/components/LineageMiniGraph.tsx:232` trips
  `react-hooks/exhaustive-deps`: `sparse` is used inside the effect but omitted
  from the dependency list.

## Findings

### P1 - Proposal actions can become unclickable immediately after listing

Evidence:

- [miner.py](../packages/dq_core/obs/miner.py:87) creates each proposal with a fresh `uuid.uuid4()`.
- [proposals.py](../services/api/routers/proposals.py:78) handles `accept/reject/snooze` by re-mining and searching for the submitted id.
- [proposals.py](../services/api/routers/proposals.py:16) persists decisions by proposal id.

Impact:

A steward can load `/proposals`, see a proposal id, click accept/reject/snooze,
and receive `404` because the action request re-mines the same logical proposal
with a different UUID. Even when a decision is stored, the next mining pass can
show the same logical proposal again under a new id.

Revision direction:

Use a stable id derived from `product + check_name + current_expect +
proposed_expect`, or persist mined proposals before presenting them. Add an API
test that lists a proposal, accepts it using the returned id, then verifies it
does not reappear as open.

### P1 - Contract activation is not atomic when Git commit/push fails

Evidence:

- [contracts.py](../services/api/routers/contracts.py:566) sets lifecycle active and writes the active snapshot before the Git write in `approve`.
- [contracts.py](../services/api/routers/contracts.py:782) persists contract, snapshot, index, and checks before the Git write in `certify`.
- [contracts.py](../services/api/routers/contracts.py:594) and [contracts.py](../services/api/routers/contracts.py:809) can return `502` after the local artifacts already changed.

Impact:

An owner can see "approve/certify failed" while the file, active snapshot,
checks, and contract index have already moved to live state. That creates a
persona deadlock: retrying may say there is nothing to approve, while Git or the
remote still needs intervention.

Revision direction:

Make artifact writes and Git commit semantics explicit. Either commit first and
only then publish active artifacts, or return a success state with a visible
"committed/push failed" remediation path. Add tests for post-error disk/index
state, not only HTTP status.

### P2 - Tests and local workflows are not hermetic because `.env` is always loaded

Evidence:

- [settings.py](../services/api/settings.py:11) always loads `.env`.
- [conftest.py](../tests/api/conftest.py:32) isolates store/contracts/inventory paths but does not clear Datasphere connector env values.
- [data_loads.py](../services/api/routers/data_loads.py:91) resolves data-load space from effective settings when no query arg is provided.

Impact:

Local Datasphere settings can turn "no live source configured" into a real
extraction attempt, causing the extract workflow to return `failed` instead of
`skipped`. The same ambient state makes data-load tests choose the local
`DATASPHERE_SPACE_ID` instead of the mocked connector file.

Revision direction:

Add a test fixture that clears connector-related env vars and resets cached
Datasphere/catalog clients. Consider disabling `.env` loading under tests unless
explicitly opted in.

### P2 - Accepting a proposal records an annotation, not an applied change

Evidence:

- [proposals.py](../services/api/routers/proposals.py:152) appends to `quality_proposals`.
- [proposals.py](../services/api/routers/proposals.py:161) downgrades the contract to draft.
- [ContractWorkbench.tsx](../apps/cockpit/src/pages/ContractWorkbench.tsx:1430) still has a TODO to expose accepted proposals in the workbench.

Impact:

Even after the id bug is fixed, "accept" does not actually update the guarantee
or check expectation. The steward is sent to a draft with no visible pending
proposal banner and no concrete edit to approve.

Revision direction:

Either apply a real patch to the relevant guarantee/check, or rename the action
to "send to workbench" and show a first-class pending-proposal banner with the
exact expected edit.

### P2 - Contract index update failures are silently swallowed

Evidence:

- [contracts.py](../services/api/routers/contracts.py:850) writes `contract_index`.
- [contracts.py](../services/api/routers/contracts.py:872) catches all exceptions and does nothing.

Impact:

Contract list, workbench navigation, and product/compliance views can become
stale after a write even though the write endpoint returned success. That is
especially risky because `contract_index` is the read model for list views.

Revision direction:

Surface index update errors, or make reindex-on-read deterministic when a write
cannot update the index. Add a regression test where `_update_index` fails and
the API response cannot silently claim a clean write.

### P2 - OpenAPI/types are drifting from the backend surface

Evidence:

The in-memory OpenAPI schema differs from `apps/cockpit/openapi.json`. Added
backend paths not present in the committed artifact:

- `/api/admin/connector`
- `/api/admin/connector/login`
- `/api/admin/environments/{name}/secret`
- `/api/contracts/{product}/drift`
- `/api/incidents/{incident_id}/rca`
- `/api/lineage/columns/impact`
- `/api/objects/{object_id}/diff`
- `/api/runs/{run_id}/results/{check_name}/segments`

CI currently marks G4 as advisory in [.github/workflows/ci.yml](../.github/workflows/ci.yml:243).

Impact:

Frontend code can keep relying on handwritten or stale types while backend
workflow endpoints evolve. This is especially visible around schema drift, RCA,
object diff, column impact, connector, and segment workflows.

Revision direction:

Regenerate `openapi.json` and `schema.d.ts` after backend changes, then decide
when G4 should become blocking again.

### P3 - Legacy `/api/environments` response shape is undecided

Evidence:

- [extract.py](../services/api/routers/extract.py:396) returns `name`, `schema`, `host`, and `secret_status`.
- `tests/api/test_r4_r5_endpoints.py::test_environments_no_secrets` still expects `password_ref: ""`.

Impact:

This may be an intentional security cleanup, but the failing test means the API
contract is not settled. Consumers of the legacy run-dialog environment endpoint
need a clear decision: no secret reference at all, or a masked/empty reference
field for backward compatibility.

Revision direction:

Pick the response contract and update either the endpoint or the test/types.

### P3 - Direct settings route throws an admin 403 under non-admin roles

Evidence:

- [Sidebar.tsx](../apps/cockpit/src/components/layout/Sidebar.tsx:92) hides `/settings` unless role is admin.
- [Settings.tsx](../apps/cockpit/src/pages/Settings.tsx:235) still calls the admin endpoint unconditionally if the route is opened directly.

Impact:

Route smoke loaded `/settings` with HTTP 200 shell content, but the page emitted
`403 /api/admin/environments` under the default steward role. This is tolerable
for hidden admin pages, but it is a rough direct-link/access-denied experience.

Revision direction:

Gate the query by role and show a read-only/admin-required panel before making
the admin request.

### P3 - Lint blocks CI on `LineageMiniGraph`

Evidence:

- [LineageMiniGraph.tsx](../apps/cockpit/src/components/LineageMiniGraph.tsx:127) uses `sparse` inside the effect.
- [LineageMiniGraph.tsx](../apps/cockpit/src/components/LineageMiniGraph.tsx:232) omits `sparse` from dependencies.

Impact:

Typecheck, Vitest, and build pass, but frontend CI lint fails. Runtime risk is
low because `sparse` is derived from `subgraph`, but the branch cannot pass the
documented lint gate.

Revision direction:

Include `sparse` in the dependency list or compute the sparse condition inside
the effect.

### P3 - Production build is green but has a large lineage chunk

Evidence:

`npm run build` passed but Vite warned that `SchematicLineage` is about 1.46 MB
minified before gzip.

Impact:

Not a correctness bug, but the lineage/coverage persona workflow may pay a
large lazy-route load cost.

Revision direction:

Consider manual chunks or deeper lazy loading around Cytoscape/ELK/lineage
visualization code after correctness issues are handled.

## Areas that looked sound in this pass

- Shipped contracts validate and compile into non-empty checks.
- G1/G2/G7 spot checks passed locally.
- Run double-start and schedule claim semantics have targeted coverage in the
  existing suite.
- Browser smoke did not find page crashes or backend 500s across the main
  cockpit routes.
- Internal vs boundary contract behavior has good backend test coverage around
  compliance, ODCS export, breaking gates, and incidents.

## Backlog mapping

The normalized active follow-ups are tracked in `OPEN_TASKS.md` §M:

- Proposal identity/action semantics → **M1**.
- Contract activation/Git failure behavior → **M2**.
- Hermetic tests and connector cache isolation → **M3**.
- Accepted-proposal banner / honest accept semantics → **M4**.
- Contract index integrity → **M5**.
- OpenAPI/types drift and G4 gate → **M6**.
- `/api/environments` response and `/settings` direct-link UX → **M7**.
- Lineage chunk measurement/optimization → **M8**.
- The old `LineageMiniGraph` lint finding is closed; future regressions belong
  to the normal lint gate.
