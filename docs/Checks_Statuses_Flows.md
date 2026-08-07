# Checks, Statuses & Flows — How Signal reasons about objects

A thorough reference for everything that happens *around* a check: the kinds of
checks, the states a single check result can carry, how those roll up into an
object status, when something is flagged **stale**, what **gating** and
**dependencies** mean, how a failure becomes a **compliance breach** and an
**incident**, and what **blast radius** (downstream impact) means in Signal.

> This document is descriptive — it explains the logic that already lives in the
> engine (`packages/dq_core/`), the store, and the API. For the canonical
> product spec see [`Tooldokumentation.md`](Tooldokumentation.md), for the two
> operating modes see [`Betriebsmodi_Lite_und_Full.md`](Betriebsmodi_Lite_und_Full.md).
> Most code/comments in the repo are German; the state *literals*
> (`skipped_stale`, `breached`, …) are part of the contract and never translated.

---

## 0. The mental model in one paragraph

A **contract** (semantic YAML) is compiled into a set of **checks** (read-only
SQL + an expectation). A **run** executes those checks against HANA/Datasphere
and produces one **check result** per check, each carrying a **state** (was it
even executed?) and, if executed, a pass/fail verdict at a **severity**. Results
roll up into an **object status** (worst-of), split by **family**
(observability vs. quality). For objects under an *active* contract the run also
computes a **compliance** state (compliant / breached); a fresh breach opens an
**incident** and notifies the owner. Independently, **lineage** lets you ask
"if this object/column is bad, what downstream is affected?" — that is the
**blast radius**.

```
contract.yaml ──compile──▶ checks.yaml ──run──▶ CheckResult[] ──rollup──▶ object status
                                              │                         └─▶ family status
                                              ├─▶ compliance ──▶ incident ──▶ notification
                                              └─▶ baselines ──▶ proposals
lineage.json ───────────────────────────────────────────────────▶ blast radius (impact)
```

---

## 1. Checks

### 1.1 What a check is

A check is the atomic unit of measurement. In the engine it is a
`CheckDef` (`packages/dq_core/engine/models.py`):

| Field | Meaning |
|---|---|
| `name` | unique within the dataset |
| `sql` | read-only scalar query — **exactly one row, one column** |
| `expect` | the expectation expression the scalar must satisfy |
| `severity` | `critical` \| `fail` \| `warn` — how bad a failure is |
| `type` | the library check id (`row_count`, `freshness`, `duplicate`, …) — drives family + gating |
| `kind` | `internal_gate` \| `consumer_contract` \| `provider_contract` |
| `enabled` | disabled checks are skipped entirely (not even a result row) |
| `timeout_s` | per-statement HANA timeout |
| `diagnostics_enabled` / `diagnostics_columns` | **[PII-GATE]** opt-in sample rows + column allowlist |

**G1 invariant:** SQL never lives in a contract. Contracts are semantic; the
compiler (`contract/compiler.py`) is the *only* producer of SQL, and the schema
is bound at runtime via `bind_schema(...)` **[SCHEMA-MAP / G2]** — never
hardcoded.

### 1.2 The check library (the catalog)

The single source of truth for what check types exist is
`packages/dq_core/library/check_library.json`. Each entry declares its
`family`, `gating` class, an `sql_template`, default expectation and default
severity. New behaviour (family membership, gating) is read from here, not
duplicated in code (`check_ids_where(...)`).

Two classifying axes matter for the flows below:

**Family** — which lens the check belongs to:
- **observability** — *is the pipeline healthy?* `row_count`, `volume_anomaly`,
  `volume_delta`, `freshness`, `recent_volume`, `schema`, `type_conformance`,
  `column_count`.
- **quality** — *are the values correct?* `missing`, `completeness_pct`,
  `duplicate(_composite/_approx)`, `invalid`, `cross_field_consistency`,
  `value_range`, `allowed_values`, `pattern_match`, `string_length`,
  `reference_integrity`, `aggregate_range`, `custom_sql`.

**Gating class** — the check's role in run sequencing (see §4):
- **`gate`** — cheap freshness/volume checks that decide whether the rest is
  even worth running: `freshness`, `volume_anomaly`.
- **`expensive`** — heavy consistency scans skipped when a gate fails:
  `duplicate`, `duplicate_composite`, `reference_integrity`, `aggregate_range`.
- **`standard`** — everything else; always runs.

### 1.3 The expectation grammar

`packages/dq_core/engine/expectation.py` is a regex parser (no `eval`). The
scalar `actual` value of the check's SQL is tested against one of:

| Form | Example | Note |
|---|---|---|
| comparison | `> 0`, `<= 2.0`, `!= 5` | |
| range | `BETWEEN 10 AND 10000` | inclusive |
| approx equality | `= 100 ± 3` | |
| delta vs. previous | `DELTA <= 25%` | uses **previous run's** actual; **no baseline → passes (warm-up)** |
| null | `IS NULL` / `IS NOT NULL` | |
| set | `IN(...)` / `NOT IN(...)` | |
| regex | `MATCHES /.../` | |

The `DELTA` form is why a run loads `get_previous_actuals(dataset)` before
executing — run-over-run comparison needs the last finished value.

### 1.4 Check kinds — internal gate vs. boundary contract

`kind` decides *who cares* about the failure and how it is escalated:
- **`internal_gate`** — an engineering self-check. No ODCS export. A breach
  becomes an **"Engineering-Signal"** incident (de-duplicated, see §6).
- **`consumer_contract` / `provider_contract`** — a promise across a team
  boundary. A breach becomes a **"Contract-Breach"** incident and is
  SemVer-protected by **G3** (a breaking change without a major bump fails CI).

---

## 2. The state of a single check result (`CheckResult.state`)

This is the most important and most easily misunderstood concept. **Every check
that the engine considers produces exactly one `CheckResult`** — including the
ones it decided *not* to run. Silently dropping a check is forbidden (**G6**).

`state` answers *"what happened to this check?"* and is orthogonal to
`passed` (the verdict). Allowed values (`engine/models.py`, persisted by
migration `002`):

| `state` | Meaning | `passed` | Counts toward status? |
|---|---|---|---|
| `executed` | ran and produced a verdict | true/false | **yes** |
| `error` | ran but threw (SQL error, wrong shape, timeout) | false | **yes** (→ `error` status) |
| `skipped_stale` | not run because a freshness/volume **gate** failed | false | **no — status-neutral** |
| `skipped_dependency` | not run because a declared dependency wasn't satisfied | false | **no — status-neutral** |
| `downgraded` | ran, but its severity was reduced for this run | n/a | reserved |

The crucial rule, implemented in `_overall_status()` and
`get_object_family_status()`:

> **Skipped/downgraded results are visible but status-neutral.** Only
> `executed` and `error` results count as pass/fail. A check that was skipped
> because data was stale is **not** a green pass and **not** a red fail — it is
> explicitly "we didn't run this, and here's why."

This is what keeps stale data from manufacturing phantom failures *or* false
confidence. The result row still exists, still shows in the run detail, still
carries its name — it just doesn't move the needle.

For the regression diff (`routers/runs.py`), both skip states normalise to a
single `skipped` bucket that ranks equal to `pass`, so a check flipping from
`executed/pass` to `skipped_stale` is *not* reported as a regression.

---

## 3. The verdict and severity (when a check *did* run)

When `state == executed`, the engine evaluates `actual` against `expect`:
- pass → `passed = True`.
- fail → `passed = False`, and the **severity** (`critical | fail | warn`)
  determines how loud it is.

A run-level `overall_status` is the **worst** executed verdict
(`_overall_status`):

```
error  >  critical  >  fail  >  warn  >  pass
```

`error` wins over everything because an exception means we don't actually know
the answer. `warn` failures never block — they surface but are not a breach
(see §5). Diagnostics (sample failing rows) are only fetched when the check
**failed**, has no error, *and* opted in via `diagnostics_enabled` + a column
allowlist **[PII-GATE / G8]**.

---

## 4. Gating — cheap checks gate expensive ones (and produce `skipped_stale`)

Runs are gated by default (`gating=True` in `start_object_run`). The logic in
`check_engine._run_with_gating`:

1. **Run the gates first** — every check whose `type ∈ GATE_TYPES`
   (`freshness`, `volume_anomaly`).
2. **Did a gate fail?** "Stale" = any gate result that is
   `executed` and `not passed`.
   - **No** → run *everything else* normally.
   - **Yes** → run only the **cheap** remainder; for every **expensive** check
     (`duplicate*`, `reference_integrity`, `aggregate_range`) emit a result with
     `state = "skipped_stale"` instead of executing it.

```
        ┌─ gates (freshness, volume_anomaly) ─┐
        │                                     │
   all pass?                            any failed?
        │                                     │
   run the rest                  run cheap rest +
   normally                      expensive → skipped_stale
```

**Why:** stale or volume-broken data makes a duplicate/RI scan both expensive
*and* meaningless — you'd be validating a snapshot that shouldn't be trusted in
the first place. Gating saves HANA load and prevents phantom failures, while
**G6** guarantees the skipped checks are still reported, with the reason
attached.

### 4.1 Execution modes

Independently of gating, a run executes in one of three `execution_mode`s:
- **`batch`** — all checks fused into one `UNION ALL ... FROM DUMMY` round-trip.
- **`isolated`** — one statement per check (slower, but pinpoints failures).
- **`auto`** (default) — try batch; on any batch error, fall back to isolated.

---

## 5. From results to object status (the rollups)

A single object accumulates many runs; the **status grid** shows the *current*
status, derived from the **latest finished run** only.

### 5.1 Object status (worst-of) — `store.get_object_status()`

Scores the latest finished run's executed results and takes the max:

| score | status |
|---|---|
| 4 | `critical` |
| 3 | `fail` |
| 2 | `warn` |
| 1 | `error` |
| 0 | `pass` |

No run yet → `unknown`.

### 5.2 Family status — `store.get_object_family_status()`

The same worst-of, but **split by family** so an object can be e.g. green on
observability and red on quality at once. Critically, this rollup explicitly
zeroes out any result where `state != 'executed'` — **gating states never
contaminate the family verdict.**

### 5.3 Coverage flag — `lineage/loader.get_coverage()`

A separate axis answering *"is this object adequately watched?"*, shown on the
lineage/coverage map:

| glyph | flag | condition |
|---|---|---|
| ● | covered | has a contract **and** the latest status is `pass` |
| ◐ | partial | has a contract but checks fail/are missing/unknown |
| ▲ | gap | no contract (or a key gap flagged) |
| ○ | out-of-scope | `external_raw`/`unknown` object or unresolved upstream |

There is also a contract-centric coverage flag in `routers/objects.py`
(`_coverage_flag`): an object whose contract exists but is *not yet* `active`
(e.g. `draft`) is a **`gap`**; active + checks present is **`covered`**, active
without checks is **`partial`**.

---

## 6. Compliance, incidents & notifications (the breach flow)

This only applies to objects under an **active** contract. It runs as a
side-effect of every finished run (`start_object_run._run_thread`).

### 6.1 Compliance state — `contract/compliance.py`

`compute_compliance(results)` (stored in `dq_compliance`, **separate from the
Git lifecycle** — invariant **A1**):

- **`breached`** — at least one check with severity in `{fail, critical}` did
  not pass.
- **`compliant`** — no such failing check.
- **`unknown`** — no results at all.

Note: `warn` failures **do not** breach. Skipped checks don't either (they're
not "passed", but they're filtered to executed results upstream).

### 6.2 The transition logic

| previous → new | action |
|---|---|
| anything → `breached` (newly) | **open an incident**, route a **notification** to the owner |
| `breached` → `compliant` | **auto-resolve** the open incident(s) |
| `compliant` → `compliant` | nothing (steady state) |

"Newly breached" is guarded so a breach that persists across several red runs
notifies **once**, not every run (the "don't flood" lesson).

For **internal_gate** objects the same shape applies but the incident is an
"Engineering-Signal" and the notification fires only if there wasn't already an
active signal for that product.

### 6.3 Incident lifecycle — `dq_incidents` (migration `004`)

An incident is a persistent object with a timeline, not just a red cell:

```
open ──▶ acknowledged ──▶ investigating ──▶ resolved
  └──────────────── auto_resolved (next run fully green) ───────────────┘
```

- **At most one open incident per product.** A repeat breach while one is open
  appends a `note` event instead of opening a second (grouping, not flooding).
- Every transition writes a `dq_incident_events` row
  (`opened | status_changed | assigned | note | auto_resolved`).
- `failed_checks` (JSON), `severity` (worst of the breaching checks),
  `contract_version` and `kind` are captured at open time.

### 6.4 SLA — `store.get_sla(product, days)`

Compliance over time is integrated from `dq_compliance_events`: the SLA is the
**percentage of wall-clock time the product spent `compliant`** within the
window (7/30/90 days). It's a time-weighted uptime number, not a pass-rate.

---

## 7. Baselines & proposals (the learning loop)

Observability checks feed a rolling statistical model so Signal can *propose*
tighter guarantees instead of requiring hand-tuned thresholds.

- **Baselines** (`obs/baselines.py`, table `dq_baselines`): after each run,
  for `row_count | volume_anomaly | freshness | sap_replication_lag`, the last
  ~50 actuals are turned into mean/stddev/p01/p99/median/MAD. **Warm-up:** fewer
  than `WARMUP_N = 5` samples → no baseline yet (and `DELTA` expectations pass
  during warm-up). Expected bands are `mean ± 3σ`, surfaced on the object
  time-series endpoint as anomaly markers.
- **Proposals** (`obs/miner.py`, table `dq_proposals`): the miner reads a
  check's history (≥ `WARMUP_MIN_SAMPLES = 10`) and proposes
  `BETWEEN p01 AND p99`, with a `confidence` that scales to 1.0 at 30 samples.
  A proposal moves through `open → accepted | rejected | snoozed`. This is the
  "data-driven guarantee proposal" surfaced in the cockpit.

---

## 8. Staleness — three distinct meanings

"Stale" appears in three unrelated places; don't conflate them.

1. **Gate staleness (per check, per run).** A freshness/volume gate failed, so
   expensive checks for *that run* become `skipped_stale` (§4). Property of a
   single run's results.

2. **Extract staleness (the metadata snapshot).** `data/lineage.json` and the
   inventory are point-in-time extracts from Datasphere. The lineage endpoint
   reports `extract_age` (days since file mtime) and flags `stale = age >
   extract_stale_days` (default **7**, `settings.py`). This says "the *map* you're
   looking at may be out of date," independent of any DQ verdict.

3. **Run staleness (informal).** An object whose latest finished run is old —
   visible via `last_run` on the status; the UI can warn, but there is no
   server-side gate that invalidates an old-but-green status.

---

## 9. Dependencies

Two notions of dependency exist in Signal:

1. **Gating dependency (implicit, runtime).** Expensive checks depend on the
   freshness gates passing. When unmet, the dependent check is
   `skipped_stale` (§4). This is the dependency the engine enforces today.

2. **Declared dependency → `skipped_dependency`.** The state model reserves
   `skipped_dependency` for a check skipped because a *declared* prerequisite
   wasn't satisfied (e.g. an upstream object's check must pass first). It is a
   first-class, persisted, status-neutral state (tested in
   `tests/unit/test_pii_gate_g6_g8.py`) so the machinery — store column,
   rollup-neutrality, run-diff bucketing — is in place even where the producing
   path is still being wired up.

3. **Lineage dependency (structural).** `data/lineage.json` encodes
   object→object `edges` and column→column `columnEdges`. This is the data-flow
   dependency graph that powers coverage and blast radius (§10) — it is about
   how data *flows*, not about check sequencing.

---

## 10. Blast radius (downstream impact)

**Blast radius = everything downstream that a problem in this object/column can
contaminate.** It answers "if this is wrong, who else is wrong?" — the reason a
single failing check matters beyond its own cell.

### 10.1 Column-level impact — `GET /api/lineage/columns/impact`

Implemented in `routers/lineage.py::get_column_impact`:
- Build a downstream adjacency map from `columnEdges`
  (`(object, column) → [children]`).
- **BFS** from the starting `(object, column)`; each reachable downstream column
  is reported **once at its minimum hop distance** (`depth`).
- **Cycle-safe** via a `seen` set; bounded by `max_depth` (default 25). Edges
  left unexplored at the cap set `truncated = true`.
- Each impacted node is enriched with the consumer's **ownership** (who to tell)
  and **coverage flag + dq status** (is the blast zone itself watched?).

Response: `impacted[]` (object, column, edgeType, expression, depth, ownedBy,
owners, coverageFlag, dqStatus), `totalImpacted`, `maxDepth`, `truncated`.

### 10.2 Why it's enriched the way it is

The blast radius isn't just a count — it's an action list. By attaching
ownership you get the notification targets; by attaching the coverage flag you
learn whether the downstream is itself protected (a `▲ gap` in the blast zone is
where an upstream defect will silently leak through). This is the same coverage
machinery from §5.3, evaluated over the *impacted* set.

### 10.3 Object-level lineage

`GET /api/lineage` returns the whole graph annotated with live DQ status +
coverage per node, plus the extract-staleness flag (§8.2). The cockpit renders
this as the lineage/coverage map; the column-impact call is the drill-down for a
specific suspect column.

---

## 11. Run lifecycle & concurrency

`RunSummary.run_state` (migration `002`): `running → finished | error`.

- A run is **registered before it executes** (`try_begin_run` seeds a `running`
  row). A partial unique index makes this the **double-run guard (F2)**: a second
  trigger while one is `running` returns `already_running` instead of starting a
  duplicate. Connection resolution happens *before* registration — fail-closed
  (S-13): no usable environment and `ALLOW_MOCK_CONNECTION=false` → 422, no run.
- Rollups (`get_object_status`, family status, `get_previous_actuals`) only
  consider `run_state = 'finished'` runs, so an in-flight or errored run never
  pollutes the current status or the `DELTA` baseline.
- Triggering a run requires **steward+** (`viewer` cannot — runs cost HANA load).
  The HTTP route and the scheduler both funnel through `start_object_run` so
  compliance/incident/notification/baseline side-effects are identical.

---

## 12. Quick reference — the state vocabularies

| Concept | Field / source | Allowed values |
|---|---|---|
| Check result state | `CheckResult.state` | `executed`, `skipped_stale`, `skipped_dependency`, `downgraded`, `error` |
| Check verdict | `CheckResult.passed` | `true` / `false` |
| Severity | `CheckResult.severity` | `critical`, `fail`, `warn` |
| Run state | `RunSummary.run_state` | `running`, `finished`, `error` |
| Object / family status | rollup | `pass`, `warn`, `fail`, `critical`, `error`, `unknown` |
| Overall run status | `_overall_status` | `pass`, `warn`, `fail`, `critical`, `error` |
| Compliance | `dq_compliance` | `compliant`, `breached`, `unknown` |
| Incident status | `dq_incidents` | `open`, `acknowledged`, `investigating`, `resolved` (+ `auto_resolved` event) |
| Proposal | `dq_proposals` | `open`, `accepted`, `rejected`, `snoozed` |
| Coverage flag | `get_coverage` | `●` covered, `◐` partial, `▲` gap, `○` out-of-scope |
| Gating class | check library | `gate`, `expensive`, `standard` |
| Family | check library | `observability`, `quality` |
| Check kind | `CheckDef.kind` | `internal_gate`, `consumer_contract`, `provider_contract` |
| Contract lifecycle | contract YAML | `draft`, `active`, `deprecated` |

### The one rule to remember

> A check result's **state** (did it run?) is independent of its **verdict**
> (did it pass?). Only `executed` and `error` results affect status and
> compliance; `skipped_*` and `downgraded` are **visible but status-neutral**
> (G6). That single principle is what makes stale-gating, dependencies, and
> honest rollups all work without lying to the user.
