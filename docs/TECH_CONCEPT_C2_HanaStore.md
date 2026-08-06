# Technical Concept: C2 HanaStore

**Stand:** 2026-06-29  
**Status:** Konzept / Umsetzungsvorbereitung  
**Scope:** C2 aus `OPEN_TASKS.md`: produktiver `HanaStore` als HANA-backed
Result-Store, funktional deckungsgleich zu `ResultStore`/SQLite.

## 1. Executive Summary

C2 ersetzt den heutigen HANA-Store-Stub durch einen produktiven Store, der alle
Signal-Laufzeitdaten in ein SAP-HANA/Open-SQL-Schema schreibt: Runs,
Check-Ergebnisse, Compliance, Operations/Progress, Incidents, Schedules,
Notifications, SLA/Rollups, Baselines, Segmentdetails, RCA/Cluster und
Impact-Snapshots.

Das ist kein kleiner Adapter um 17 Protocol-Methoden. Die reale Store-Oberfläche
ist auf rund 50 Methoden gewachsen. Deshalb wird C2 als Paritätsprojekt gebaut:
`HanaStore` muss die von Routern und Services tatsächlich verwendete Oberfläche
von `ResultStore` vollständig abdecken, sonst startet ein HANA-Deployment zwar,
verliert aber Cockpit-Funktionen.

Primäres Ergebnis:

- `STORE_BACKEND=hana` startet ohne Runtime-Abweisung.
- HANA-Migrationen legen alle Signal-Result-Tabellen im konfigurierten
  Open-SQL-Schema an.
- Der HANA-Store besteht dieselben Store-Verhaltenssuiten wie SQLite, ergänzt um
  echte HANA-Smoke-Tests für Dialekt- und Nebenläufigkeitsrisiken.

## 2. Annahmen

1. **Instanz-pro-Tenant bleibt gesetzt.** Kein `tenant_id`, keine Row-Level-
   Filter im Store. Isolation passiert über Deployment, Environment und Schema.
2. **Result-Store lebt im Open-SQL-Schema des konfigurierten DB-Users.** Der
   Schema-Name kommt aus `RESULTS_ENVIRONMENT`, nicht aus Contracts.
3. **Keine stille SQLite-Fallback-Logik.** Wenn `STORE_BACKEND=hana` gesetzt ist
   und HANA nicht erreichbar/migrierbar ist, startet der API-Prozess fail-closed.
4. **Parität vor Optimierung.** Erst korrekt und deckungsgleich, dann Performance-
   Tuning und größere Query-Refactors.
5. **HANA-Dialekt wird explizit gepflegt.** Keine automatische Übersetzung aus
   SQLite-SQL zur Laufzeit.

## 3. Nicht-Ziele

- Kein Quarantine/Reject-Store in C2. Das ist C5/Folgearbeit.
- Kein Connection-Pooling als Muss für v1. Der Store kann mit einer Connection-
  Factory starten; Pooling kommt erst nach Lastmessung.
- Kein Wechsel der Run-Engine. C2 betrifft Persistenz, nicht Check-Ausführung.
- Kein HANA-Sync aus SQLite. Es gibt entweder SQLite- oder HANA-Backend.

## 4. Ist-Zustand

`packages/dq_core/store/hana_store.py` ist ein Stub. Die Stub-Methoden folgen nur
dem veralteten `ResultStoreProtocol` in `base.py`.

`services/api/deps.py` blockiert `STORE_BACKEND=hana` bewusst:

```python
if settings.store_backend == "hana":
    raise RuntimeError(...)
```

Der produktive Store-Vertrag steckt faktisch in `sqlite_store.py`, nicht mehr im
Protocol. Relevante Methodenfamilien:

- Runs und Ergebnisse: `save_run`, `try_begin_run`, `get_run`, `get_runs`,
  `get_all_runs`, `get_latest_run`, `set_run_state`, `get_previous_actuals`,
  `get_check_history`, `get_metric_series`.
- Compliance/SLA/Rollups: `set_compliance`, `get_compliance`,
  `get_compliance_events`, `get_sla`, `get_object_status`,
  `get_object_family_status`, `get_health_trend`, `get_status_heatmap`.
- Operations/SSE: `append_progress`, `get_progress`, `begin_operation`,
  `finish_operation`, `get_operation`.
- Schedules: create/list/get/update/delete/claim/record.
- Incidents: open/update/list/get/transition/auto-resolve/count.
- Observability Intelligence: segment results, baselines, seasonal buckets,
  RCA, clustering, impacted objects.
- Notifications: channels/rules/mutes CRUD.
- Diagnostics: PII-gated diagnostic rows and TTL cleanup.
- Contract index reads used by RCA.

## 5. Target Architecture

### 5.1 Store Construction

Add `results_environment` to settings:

```python
results_environment: str = Field(default="")
```

`deps.get_store()` resolves that environment through the existing
`get_environment()` path, including `password_ref` resolution. Then it creates:

```python
HanaStore.from_environment(env, ...)
```

The HANA store receives a **connection factory**, not a single long-lived
connection:

```python
class HanaStore:
    def __init__(self, connect: Callable[[], DbConnection], schema: str, ...):
        ...
```

Rationale:

- avoids stale shared hdbcli sessions across API threads;
- mirrors SQLite's short transaction blocks;
- keeps retry/fail-closed behavior centralized in `get_connection`.

### 5.2 Schema Ownership

All store tables live in the resolved HANA schema. DDL and DML qualify table
names through one helper:

```python
q.table("dq_runs") -> '"MY_SCHEMA"."DQ_RUNS"'
```

The helper must validate identifiers before quoting. No string-concatenated
user input becomes SQL identifiers. Values always use parameters.

### 5.3 Transaction Model

Each public write method opens a connection, starts an implicit transaction,
executes the method, commits, and closes. On exception it rolls back and closes.

Read methods open and close a short-lived connection too. If later load testing
shows connection churn as a bottleneck, replace the factory with a small pool
behind the same `HanaStore` constructor.

### 5.4 Data Shape

HANA rows are normalized back to Python dictionaries with the same keys and
types as SQLite responses. JSON fields stay JSON strings in the DB and are
decoded at the API boundary exactly like SQLite:

- `failed_checks`
- `impacted_objects`
- `cause_candidates`
- `affected_contracts`
- notification facets where relevant
- operation `result_json`

## 6. Deliverable Slices

### Slice 0: Freeze The Store Contract

Before implementation, create a real contract test that derives or enumerates the
public store surface.

Actions:

1. Update `ResultStoreProtocol` to the actual consumed surface.
2. Add a test that every API-used public method exists on both stores.
3. Add signature checks for methods where callers pass keyword args.
4. Keep private helpers out of the Protocol.

Acceptance:

- `ResultStore` and `HanaStore` both satisfy the expanded Protocol.
- A missing future method fails tests before a HANA deployment fails at runtime.

### Slice 1: HANA Migration Runner

Add dialect-specific migrations under:

```text
packages/dq_core/store/migrations/hana/001_initial_schema.sql
...
```

Use the same version stems as SQLite where possible. The runner keeps a
`schema_migrations` table in HANA and applies unapplied files in lexical order.

Acceptance:

- migration runner can create an empty HANA schema from scratch;
- duplicate-column/idempotent cases are handled deliberately, not by swallowing
  unrelated errors;
- all current SQLite migrations `001` through `015` have a HANA equivalent.

### Slice 2: Core Runs And Results

Implement the minimum store methods required for a run to start, write results,
read detail/history, and stream progress:

- `try_begin_run`
- `save_run`
- `set_run_state`
- `get_run`
- `get_runs`
- `get_all_runs`
- `get_latest_run`
- `get_previous_actuals`
- `get_check_history`
- `append_progress`
- `get_progress`
- `begin_operation`
- `finish_operation`
- `get_operation`

Acceptance:

- a real HANA smoke can create tables, run a mock/real check, persist results,
  and load the run detail back;
- concurrent `try_begin_run` calls for the same dataset allow exactly one
  running run.

### Slice 3: Compliance, SLA, Rollups

Implement:

- `set_compliance`
- `get_compliance`
- `get_compliance_events`
- `get_sla`
- `get_object_status`
- `get_object_family_status`
- `get_metric_series`
- `get_health_trend`
- `get_status_heatmap`

Acceptance:

- Cockpit landing/dashboard object status works with HANA backend.
- SLA math matches SQLite tests on the same fixture data.

### Slice 4: Incidents And Observability Intelligence

Implement:

- `open_incident`
- `open_incident_record`
- `auto_resolve_incidents`
- `list_incidents`
- `get_incident`
- `transition_incident`
- `count_open_incidents`
- `assign_incident_cluster`
- `list_incident_clusters`
- `save_incident_rca`
- `get_incident_rca`
- `get_recent_failures`
- `get_prior_incidents`
- `save_segment_results`
- `get_segment_results`
- baseline read/write methods currently used by `BaselineManager`

Acceptance:

- Observability-Intelligence v1 behavior is not degraded on HANA.
- Notifications dedupe and RCA clustering work identically to SQLite.

### Slice 5: Schedules And Notifications

Implement:

- schedule CRUD/claim/record methods;
- notification channels/rules/mutes CRUD.

Acceptance:

- internal scheduler can claim due work on HANA;
- notification routing still resolves from DB rules before YAML fallback.

### Slice 6: Diagnostics And Retention

Implement:

- `get_diagnostics`
- diagnostic insert path in `save_run`
- `_cleanup_diagnostics`

Respect existing PII-gate defaults: diagnostics are off unless explicitly
enabled, allowlisted, and TTL-cleaned.

Acceptance:

- no diagnostic rows persist unless enabled;
- TTL cleanup deletes only expired diagnostics;
- no raw profile samples are introduced by C2.

### Slice 7: Wire `STORE_BACKEND=hana`

Update `deps.get_store()`:

- resolve `RESULTS_ENVIRONMENT`;
- fail with a safe config error if missing;
- create `HanaStore`;
- run migrations on initialization;
- keep SQLite path unchanged.

Acceptance:

- `STORE_BACKEND=hana RESULTS_ENVIRONMENT=...` starts the API.
- bad/missing env or credentials fail closed with safe error messages.

## 7. HANA Dialect Mapping

| SQLite pattern | HANA target |
|---|---|
| `TEXT` | `NVARCHAR(5000)` for bounded text, `NCLOB` for SQL/JSON/log payloads |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY` |
| `INTEGER` booleans | `TINYINT` or `INTEGER`, normalized to Python `bool`/`int` on read |
| `INSERT OR REPLACE` | `UPSERT ... WITH PRIMARY KEY` or `MERGE` |
| `INSERT OR IGNORE` | `MERGE`/guarded insert |
| SQLite partial unique index | HANA filtered/conditional unique strategy, verified on real HANA |
| `datetime('now', '-7 days')` | compute timestamps in Python and pass parameters |
| `json.loads(TEXT)` | keep JSON as `NCLOB`/`NVARCHAR`, decode in Python |
| `LIMIT ? OFFSET ?` | HANA-compatible `LIMIT ? OFFSET ?` only where supported by hdbcli; otherwise `ORDER BY ... LIMIT` with tested syntax |

Important: avoid HANA-specific SQL in shared call sites. Keep dialect differences
inside `HanaStore` and HANA migration files.

## 8. Table Strategy

Use uppercase physical table names only if HANA quoting requires consistency;
otherwise preserve lowercase quoted identifiers. Pick one convention and use it
everywhere through the identifier helper.

Required tables as of C2:

- `schema_migrations`
- `dq_runs`
- `dq_check_results`
- `dq_diagnostics`
- `dq_compliance`
- `dq_compliance_events`
- `contract_index`
- `dq_progress`
- `dq_operations`
- `dq_schedules`
- `dq_incidents`
- `dq_incident_events`
- `dq_notification_channels`
- `dq_notification_rules`
- `dq_notification_mutes`
- `dq_baselines`
- `dq_baseline_buckets`
- `dq_segment_results`
- `dq_incident_rca`
- `dq_incident_clusters`

## 9. Concurrency Strategy

The critical concurrency invariant is F2: at most one running run per dataset.

Preferred implementation:

1. Add a generated/derived guard column in HANA migrations if HANA filtered
   unique indexes are not suitable:

   ```sql
   running_dataset_key NVARCHAR(...) GENERATED ALWAYS AS
     (CASE WHEN run_state = 'running' THEN dataset ELSE NULL END)
   ```

2. Create a unique index on that guard column.
3. `try_begin_run` performs an insert and returns `False` on unique violation.

This avoids check-then-insert races and mirrors SQLite's partial unique index
semantics.

The same real-HANA smoke must test two concurrent claims for the same dataset.

## 10. Error Handling

Rules:

- Do not expose raw HANA exception text through API responses.
- Inside `HanaStore`, convert expected uniqueness conflicts into boolean return
  values where SQLite does.
- Unexpected DB errors propagate to the service layer, where existing routes
  mark operations/runs as error.
- Always close cursors/connections in `finally`.
- Never log credentials, environment password values, or full connection strings.

## 11. Testing Strategy

### 11.1 Unit Tests Without HANA

Use a small hdbcli-style fake for shape tests only:

- parameter binding is used;
- expected SQL operation family is called;
- Protocol/signature parity holds;
- migration runner selects HANA migration directory.

Do not pretend the fake proves HANA SQL syntax.

### 11.2 Shared Store Behavior Suite

Refactor SQLite store tests into a backend-neutral suite:

```python
def exercise_store_contract(make_store):
    ...
```

Run it for:

- `ResultStore(tmp_path / "test.db")`
- `HanaStore(...)` when `HANA_SMOKE=1`

### 11.3 Real HANA Smoke

Add `tests/integration/test_hana_store_smoke.py`, skipped unless:

```text
HANA_SMOKE=1
HANA_HOST
HANA_PORT
HANA_USER
HANA_PASSWORD or HANA_PASSWORD_REF
HANA_SCHEMA
```

Smoke cases:

1. migrate empty schema;
2. save/read run with result rows;
3. F2 concurrent run guard;
4. compliance transition and SLA;
5. incident open, cluster, RCA, impact JSON;
6. schedule claim;
7. notification rule routing;
8. cleanup/teardown only if test schema is explicitly marked disposable.

## 12. Implementation Order

Recommended order:

1. Expand Protocol and add parity tests.
2. Add HANA identifier/row/transaction helpers.
3. Add HANA migrations through current `015`.
4. Implement core run/operation methods.
5. Wire `STORE_BACKEND=hana` behind `RESULTS_ENVIRONMENT`, but keep tests
   proving bad config fails safely.
6. Implement compliance/rollup methods.
7. Implement incidents/observability methods.
8. Implement schedules/notifications.
9. Implement diagnostics/TTL.
10. Add real HANA smoke and documentation.

This order creates a runnable vertical slice early without claiming full C2 done
until Cockpit parity is complete.

## 13. Review Gates

Do not mark C2 done until:

- every current public `ResultStore` method used by API code exists on
  `HanaStore`;
- HANA migrations cover all SQLite migration versions;
- `STORE_BACKEND=hana` no longer raises the stub error;
- targeted backend suites pass on SQLite;
- HANA smoke passes at least once against a real HANA/Open-SQL schema;
- `Tooldokumentation.md` documents `STORE_BACKEND=hana`,
  `RESULTS_ENVIRONMENT`, required DB grants, and smoke setup.

## 14. Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Protocol under-specifies real store usage | Expand Protocol from actual router/service calls first |
| HANA SQL differs subtly from assumptions | Real HANA smoke is mandatory, fake tests are not enough |
| Duplicate migration maintenance | Require paired SQLite/HANA migrations in review |
| Run guard race under multiple workers | DB-level unique guard plus concurrent smoke |
| JSON/NCLOB values differ from SQLite strings | Normalize row conversion in `HanaStore` helpers |
| HANA connection churn | Start simple; introduce pool only after measurement |
| Error messages leak internals | Safe exception mapping at service boundary |
| Store grows again and HANA lags | Parity test fails when API calls a method absent on `HanaStore` |

## 15. Open Decisions

1. Exact HANA syntax for the run guard: filtered unique index vs generated guard
   column. Decision should be made with a real HANA probe.
2. Physical identifier convention: quoted lowercase vs uppercase. Pick one before
   migrations are written.
3. Whether diagnostics should be supported on HANA in v1 or explicitly disabled.
   Recommendation: support them with the same default-off/TTL behavior for parity.
4. Whether `RESULTS_ENVIRONMENT` may equal the execution environment. Technically
   yes, but production docs should recommend a least-privilege result-store user.

## 16. Definition Of Done

C2 is done when a deployment can run with:

```text
STORE_BACKEND=hana
RESULTS_ENVIRONMENT=<configured environment>
ALLOW_MOCK_CONNECTION=false
```

and still support the same Cockpit workflows as SQLite:

- object runs and run detail;
- live progress;
- compliance state and SLA;
- incidents, RCA, clustering, impact snapshots;
- schedules;
- notification routing;
- metric series, health trend, heatmap;
- diagnostics when explicitly enabled.

The implementation is accepted only after the real HANA smoke has passed and the
remaining HANA-specific setup is documented for operators.
