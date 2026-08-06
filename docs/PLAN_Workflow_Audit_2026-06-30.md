# PLAN - Workflow Audit Remediation 2026-06-30

Basis: `docs/WORKFLOW_AUDIT_2026-06-30.md`

Status: detailed remediation plan; active backlog tracking is consolidated in
`docs/OPEN_TASKS.md` §M.

> **Backlog consolidation 2026-07-04:** Use `OPEN_TASKS.md` §M for live task IDs
> and priority. This file keeps implementation detail and suggested PR slicing.
> The `LineageMiniGraph` lint item from W1 is no longer a live backlog item; the
> `sparse` dependency is present and future regressions belong to the normal lint
> gate.

Goal: close the workflow audit findings with small, verifiable changes that
restore reliable persona workflows before adding performance-only improvements.

## Assumptions

- This plan fixes the findings from the workflow audit only. It does not add new
  product scope beyond the remediation needed to make those workflows truthful.
- The implementation should stay surgical: fix red gates first, then the P1
  workflow bugs, then schema/type drift and polish.
- The legacy `/api/environments` endpoint should not expose `password_ref`.
  The secure response contract is `name`, `schema`, `host`, and
  `secret_status`; tests and generated types should reflect that decision.
- Proposal "accept" should not pretend to apply a guarantee until proposals
  carry a structured patch. For this revision, the safe behavior is: stable
  proposal ids, persisted decisions, and a first-class Workbench banner showing
  the exact pending edit.
- Contract activation should be locally consistent. If Git commit fails before a
  commit exists, active artifacts must not be published. If the local commit
  succeeds but push is rejected, the UI may publish the activation locally, but
  it must return a visible "remote sync required" warning instead of a failed
  activation that already changed disk state.

## Execution Sequence

| Phase | Fixes | Why first | Exit gate |
|---|---|---|---|
| W0 | Baseline and test isolation | Red local state currently hides real regressions | Backend failing tests are reproducible and isolated |
| W1 | Small CI blockers | Cheap fixes, unblocks branch hygiene | Backend tests + frontend lint are green locally |
| W2 | Proposal workflow truth | P1 user-facing action failure | List -> action -> filtered list works by returned id |
| W3 | Contract activation consistency | P1 data/state consistency risk | Git failure paths leave explicit, tested artifact state |
| W4 | Contract index integrity | P2 read-model correctness | Index failures cannot be silently swallowed |
| W5 | OpenAPI/types/settings route | P2/P3 integration drift and direct-link UX | Generated artifacts match backend and G4 can block again |
| W6 | Lineage chunk performance | P3 non-correctness optimization | Build warning is measured and accepted or reduced |
| W7 | Final verification | Release confidence | Full audit command set passes or has documented residual risk |

## W0 - Baseline And Hermetic Test Harness

Findings covered:

- P2 - Tests and local workflows are not hermetic because `.env` is always loaded.

Implementation tasks:

- Add an autouse test fixture, preferably in `tests/conftest.py`, that clears
  ambient Datasphere and connector settings before each test:
  `DATASPHERE_BASE_URL`, `DATASPHERE_CLIENT_ID`,
  `DATASPHERE_CLIENT_SECRET`, `DATASPHERE_AUTHORIZATION_URL`,
  `DATASPHERE_TOKEN_URL`, `DATASPHERE_OAUTH_SECRETS_FILE`,
  `DATASPHERE_SPACE_ID`, `DATASPHERE_USE_CLI`,
  `DATASPHERE_MONITORING_SPACE`, and `CONNECTOR_FILE`.
- Point `CONNECTOR_FILE`, `ENVIRONMENTS_FILE`, and `SECRETS_FILE` at temp files
  in API fixtures where those files matter.
- Reset cached runtime state in the same fixture:
  `services.api.settings._settings`, `services.api.deps._store_instance`,
  `services.api.datasphere.reset_client()`, and
  `services.api.datasphere_catalog.reset_catalog_client()`.
- Keep `.env` loading for normal local development. Do not globally disable it
  unless a later test proves the fixture is insufficient.
- Tighten `tests/unit/test_data_loads_space.py::_reset_settings` so it controls
  all connector inputs, not just `DATASPHERE_SPACE_ID`.

Acceptance tests:

- `tests/api/test_extract.py::test_extract_skipped_without_live_source`
- `tests/api/test_extract.py::test_extract_leaves_snapshot_untouched_without_live_source`
- `tests/api/test_extract.py::test_lineage_stays_stale_after_skipped_extract`
- `tests/unit/test_data_loads_space.py::test_resolve_space_falls_back_to_connector_file`
- `tests/unit/test_data_loads_space.py::test_resolve_space_empty_when_nothing_configured`

Implementation notes:

- Do not make production settings depend on `PYTEST_CURRENT_TEST`; keep the
  isolation in tests unless there is a clear need for a `SIGNAL_LOAD_DOTENV`
  setting later.
- Avoid broad `monkeypatch.delenv` loops that also erase unrelated settings used
  by a specific test. Keep the cleared key list explicit.

## W1 - Small CI Blockers And Contract Decisions

Findings covered:

- P3 - Legacy `/api/environments` response shape is undecided.
- P3 - Lint blocks CI on `LineageMiniGraph` (**closed after the audit; retained
  here only as historical context**).

Implementation tasks:

- Update `tests/api/test_r4_r5_endpoints.py::test_environments_no_secrets` to
  assert the secure legacy shape:
  `{"name", "schema", "host", "secret_status"}` and no `password_ref`.
- Check whether `apps/cockpit/src/api/schema.d.ts` currently exposes the legacy
  field. If it does, let W5 regeneration remove it after backend changes.
- Historical/closed: `apps/cockpit/src/components/LineageMiniGraph.tsx` now has
  `sparse` in the `useEffect` dependency list. No separate active task remains.

Acceptance tests:

- `python -m pytest tests/api/test_r4_r5_endpoints.py::test_environments_no_secrets -v`
- `cd apps/cockpit && npm run lint`
- `cd apps/cockpit && npm run test -- LineageMiniGraph`

Implementation notes:

- This phase should not change the admin environment endpoints. The admin
  endpoints may continue to use masked secret metadata for admin workflows.

## W2 - Proposal Workflow Truth

Findings covered:

- P1 - Proposal actions can become unclickable immediately after listing.
- P2 - Accepting a proposal records an annotation, not an applied change.

### W2.1 Stable Proposal Identity

Implementation tasks:

- Replace `uuid.uuid4()` in `packages/dq_core/obs/miner.py` with a stable id
  derived from normalized proposal content:
  `product`, `check_name`, `current_expect`, `proposed_expect`, and `kind`.
- Use a deterministic helper such as:
  `proposal-` + first 20 hex chars of `sha256(json.dumps(payload, sort_keys=True))`.
- Keep the helper in `miner.py` or a tiny private function near the `Proposal`
  dataclass. Do not introduce a store abstraction for this narrow fix.
- Add unit coverage in `tests/unit/test_proposal_miner.py`:
  same historical input produces the same id across two `mine()` calls;
  changing `proposed_expect` or `check_name` changes the id.
- Remove the now-unused `uuid` import.

Acceptance tests:

- `python -m pytest tests/unit/test_proposal_miner.py -v`

### W2.2 Action By Returned Id

Implementation tasks:

- Add an API regression test that:
  1. seeds enough run/check history to mine at least one open proposal;
  2. calls `GET /api/proposals`;
  3. posts to `/api/proposals/{returned_id}/accept`;
  4. calls `GET /api/proposals?status=open`;
  5. asserts the accepted proposal id no longer appears as open.
- Add the same returned-id flow for `reject` and `snooze` if test setup remains
  small. At minimum, acceptance must cover `accept`, because that is the
  highest-impact workflow.
- Stop swallowing persistence failures in `_decision_map` if practical. If that
  would create too much churn, at least add logging and keep the API behavior
  explicit in tests.

Acceptance tests:

- New test in `tests/api/test_proposals.py` or an existing proposal API file:
  `test_accepts_listed_proposal_and_filters_from_open`.
- Optional:
  `test_rejects_listed_proposal_and_filters_from_open`;
  `test_snoozes_listed_proposal_and_filters_from_open`.

### W2.3 Honest Accept Semantics

Implementation tasks:

- Expose accepted proposal annotations through the contract API:
  - add `quality_proposals` to `ContractOut` or a typed nested field if the
    frontend already has a better contract detail shape;
  - include `check_name`, `proposed_expect`, `rationale`, `accepted_by`, and a
    timestamp.
- In `services/api/routers/proposals.py`, keep the draft amendment behavior but
  make it explicit:
  - status remains `accepted` for compatibility;
  - response message says the proposal was added to the draft for review;
  - no copy should imply the guarantee was already rewritten.
- In `apps/cockpit/src/pages/ContractWorkbench.tsx`, replace the TODO at the
  accepted-proposal surface with a visible pending-proposal banner:
  - show the affected `check_name`;
  - show current expectation and proposed expectation where available;
  - show rationale and actor;
  - link the user to the relevant guarantee/check area if a local anchor exists.
- In `apps/cockpit/src/pages/Proposals.tsx`, adjust button copy only if needed
  to avoid overpromising. Acceptable labels: "Accept into draft" or "Send to
  Workbench". Keep API route compatibility.

Acceptance tests:

- Backend:
  `GET /api/contracts/{product}` returns accepted proposal annotations after
  accepting a proposal.
- Frontend:
  add or update a `ContractWorkbench` test showing the pending proposal banner
  for a contract fixture with `quality_proposals`.
- Manual smoke:
  `/proposals` -> accept -> `/contracts?product=...` shows the pending edit.

Implementation notes:

- Do not auto-edit `guarantees` in this revision unless the proposal payload is
  upgraded to a structured patch. The current mined proposal only has
  `check_name` plus an expectation string, which is not enough to safely rewrite
  every guarantee family.

## W3 - Contract Activation And Git Failure Semantics

Findings covered:

- P1 - Contract activation is not atomic when Git commit/push fails.

Target behavior:

| Failure point | HTTP result | Contract file | Active snapshot | Checks | Index | UI meaning |
|---|---|---|---|---|---|---|
| Validation or compile fails | 4xx | unchanged | unchanged | unchanged | unchanged | user fixes input |
| Git commit fails before commit exists | 502 | restored | unchanged | unchanged | unchanged | retry after repo fix |
| Local commit succeeds, push rejected | 200 with warning | active/certified | published | published if certify | updated | activation done locally, remote sync required |
| Derived artifact write fails after commit | 500 with explicit partial state | active/certified | may be partial | may be partial | not claimed clean | operator remediation |

Implementation tasks:

- Refactor `services/api/git_repo.py` so callers can distinguish:
  - no Git repository or no GitPython installed, treated as local content hash;
  - commit failure before a commit exists;
  - commit success;
  - push rejection after commit success.
- Prefer returning a small result object over raising `GitPushRejected` for
  push rejection:
  `GitWriteResult(content_hash, commit_hash, committed, pushed, push_error)`.
  If preserving the exception is smaller, attach the commit hash to the
  exception and handle it explicitly.
- Make `GitRepo.write_contract()` restore the previous file content when it
  writes a file but fails before a successful commit/content-hash result.
- In `services/api/routers/contracts.py::approve_contract`:
  - build the active contract data and YAML in memory;
  - run validation and breaking checks before writes;
  - call the Git write path before publishing `.active.yml` and index state;
  - publish active snapshot and index only after commit/content-hash success;
  - include an optional warning field in the response when push failed.
- In `services/api/routers/contracts.py::certify_contract`:
  - compile to YAML before any writes, as it already does;
  - call the Git write path before writing `.active.yml`, generated checks, and
    index state;
  - publish generated checks only after commit/content-hash success;
  - include the same push warning behavior.
- Update frontend mutation handling in `apps/cockpit/src/api/contracts.ts` and
  `ContractWorkbench.tsx` if the response gains a warning field.

Acceptance tests:

- Existing:
  `tests/api/test_contract_lifecycle.py`
  `tests/api/test_lite_certify.py`
- Add:
  - approve commit failure restores the draft file and does not create
    `.active.yml`;
  - approve push rejection returns success with warning and active artifacts are
    present;
  - certify commit failure does not write checks;
  - certify push rejection returns success with warning and checks are present;
  - repeated approve after commit failure is still possible because the contract
    remains draft.

Implementation notes:

- This phase will likely require updating
  `test_approve_returns_409_on_push_rejection`; the new expected behavior is a
  successful local activation with a remote-sync warning.
- Keep `GitRepo` responsible for file restore around commit failures. Endpoint
  code should not duplicate low-level Git rollback behavior.
- If adding warning fields to `ContractOut` causes response-model churn, use a
  typed optional field with a narrow shape, for example:
  `warnings: [{ code: "git_push_rejected", message: "...", commit_hash: "..." }]`.

## W4 - Contract Index Integrity

Findings covered:

- P2 - Contract index update failures are silently swallowed.

Implementation tasks:

- Replace the catch-all `except Exception: pass` in `_update_index` with one of:
  - an `IndexUpdateError` that preserves the original exception message, or
  - no catch at all, letting the original exception surface.
- Ensure write endpoints that call `_update_index` do not return a clean success
  after the index write fails.
- Keep `GET /api/contracts` resilient:
  - if the index is empty, the existing lazy `_reindex` path is acceptable;
  - if the index is corrupt or unavailable, return a clear 500 rather than an
    empty list that looks valid.
- Add logging around `_reindex` skips for malformed YAML if useful, but do not
  change malformed-contract behavior unless a test demands it.

Acceptance tests:

- Add a regression test where `_update_index` or the underlying SQLite
  connection fails during a write. The response must not be a normal success.
- Add a list-view test that an empty index can still be rebuilt deterministically
  from valid contract files.

Implementation notes:

- Avoid using broad monkeypatches that make every SQLite operation fail; target
  `_update_index` or the connection used by that helper so the failure is about
  index integrity, not unrelated store setup.

## W5 - API Drift, Generated Types, And Settings Direct Link

Findings covered:

- P2 - OpenAPI/types are drifting from the backend surface.
- P3 - Direct settings route throws an admin 403 under non-admin roles.

### W5.1 Regenerate API Contract

Implementation tasks:

- After W0-W4 backend shape changes are complete, run:
  `python scripts/export_openapi.py`
- Then run in `apps/cockpit`:
  `npm run gen:api`
- Review generated diffs in:
  - `apps/cockpit/openapi.json`
  - `apps/cockpit/src/api/schema.d.ts`
- Confirm the audit-listed backend paths are present:
  - `/api/admin/connector`
  - `/api/admin/connector/login`
  - `/api/admin/environments/{name}/secret`
  - `/api/contracts/{product}/drift`
  - `/api/incidents/{incident_id}/rca`
  - `/api/lineage/columns/impact`
  - `/api/objects/{object_id}/diff`
  - `/api/runs/{run_id}/results/{check_name}/segments`
- Remove `continue-on-error: true` from the G4 step in
  `.github/workflows/ci.yml` once generated artifacts are committed.

Acceptance tests:

- `python scripts/export_openapi.py`
- `cd apps/cockpit && npm run gen:api`
- `git diff --exit-code -- apps/cockpit/openapi.json apps/cockpit/src/api/schema.d.ts`
  after regeneration is committed.

Implementation notes:

- Do not make G4 blocking before W0-W4 are complete, or schema churn will create
  avoidable rework.

### W5.2 Settings Route Gate

Implementation tasks:

- Update `apps/cockpit/src/api/environments.ts::useAdminEnvironments` to accept
  an `enabled` option or a wrapper query option.
- In `apps/cockpit/src/pages/Settings.tsx`, compute
  `const canAdmin = canManageEnvironments(role)` before calling the admin query.
- Disable the admin environments query unless `canAdmin` is true.
- Render an admin-required/read-only panel for non-admin roles before any admin
  network request is made.
- Keep `ConnectorPanel` behavior aligned with the same role gate.

Acceptance tests:

- Add or update `apps/cockpit/src/tests/Settings.test.tsx`:
  - with role `steward`, rendering `/settings` does not call
    `/api/admin/environments`;
  - the page shows an admin-required/read-only state;
  - with role `admin`, the query still runs and environments render.

Implementation notes:

- The server remains authoritative. This is only a direct-link UX fix and should
  not loosen backend authorization.

## W6 - Lineage Chunk Size

Findings covered:

- P3 - Production build is green but has a large lineage chunk.

Implementation tasks:

- Measure before changing:
  - run `cd apps/cockpit && npm run build`;
  - record the exact warned chunk names and sizes.
- Check whether the warning is from the route chunk alone or shared vendor code.
  `SchematicLineage` is already route-lazy, so the next likely wins are vendor
  chunking or deeper lazy loading inside the lineage route.
- If still worth fixing after correctness work:
  - add `manualChunks` in `apps/cockpit/vite.config.ts` for heavy lineage
    dependencies such as `cytoscape`, `cytoscape-dagre`, and `elkjs`;
  - consider dynamic imports for optional lineage layout/inspector panels;
  - keep the first render nonblank while deeper panels load.
- If the route chunk remains large but isolated, document it as accepted risk
  with measured gzip size and route-only impact.

Acceptance tests:

- `cd apps/cockpit && npm run build`
- Browser smoke on `/lineage` and `/coverage` after any dynamic import change.

Implementation notes:

- Do not prioritize this before W0-W5. It is a performance concern, not a
  correctness failure.

## W7 - Final Verification Matrix

Run these checks after all implementation phases:

Backend:

- `python -m pytest tests/ -v --tb=short`
- Shipped contract validation and compilation for all non-`.active.yml`
  contracts.
- Static G2/G7 spot checks:
  no hardcoded `CENTRAL`; no web framework imports in `dq_core`.
- CLI mock dry-run still returns a real DQ verdict rather than crashing.

Frontend:

- `cd apps/cockpit && npm run typecheck`
- `cd apps/cockpit && npm run lint`
- `cd apps/cockpit && npm run test`
- `cd apps/cockpit && npm run build`

Generated artifacts:

- `python scripts/export_openapi.py`
- `cd apps/cockpit && npm run gen:api`
- `git diff --exit-code -- apps/cockpit/openapi.json apps/cockpit/src/api/schema.d.ts`

Browser smoke:

- Load the same 19 cockpit routes used in the audit.
- Confirm `/settings` under a non-admin role has no admin 403 request.
- Confirm proposal accept flow reaches the Workbench pending-proposal banner.
- Confirm contract approve/certify push-warning flow is visible if simulated.

## Suggested PR Slices

1. PR A - Test isolation and small gates:
   W0 and W1. Goal: full backend suite no longer depends on local `.env`, and
   frontend lint is green.
2. PR B - Proposal workflow:
   W2. Goal: returned proposal ids are actionable and accepted proposals are
   visible in Workbench.
3. PR C - Activation and index consistency:
   W3 and W4. Goal: no endpoint reports failure or success while local contract
   artifacts tell a different story.
4. PR D - API drift and direct-link UX:
   W5. Goal: OpenAPI/types match backend, G4 becomes blocking, `/settings` is
   clean for non-admin roles.
5. PR E - Lineage build optimization:
   W6 only if the measured chunk cost is still worth paying down.

## Done Criteria

- All P1 and P2 findings in the workflow audit have a regression test.
- All originally failing backend tests pass without requiring local `.env`
  changes.
- Frontend lint, typecheck, tests, and build pass.
- Generated OpenAPI and TypeScript schema artifacts are up to date.
- CI G4 is blocking again.
- Any remaining P3 performance concern is either fixed or explicitly accepted
  with measured build output.
