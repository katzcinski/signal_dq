# Batch 4 — Kind-Aware Compliance/Incident Split + Engineering Signals

> **Goal**: Honour ADR-0001 §5 — only `*_contract` artifacts drive the
> governance compliance traffic-light and the Consumer-SLA. An `internal_gate`
> that fails produces an **Engineering Signal** (team-internal incident, routed
> to the product/platform team) and **never** touches the governance ampel, the
> SLA windows, or the ODCS export. "Gleiche Regel, zwei Artefakte" — same test,
> different consequence.
>
> **Depends on**: Batch 1–3 merged (`kind` discriminator on `Contract`,
> `ContractOut`, `Proposal`; coverage dimension switcher; promotion flow).
> Current `main` = `53ada3c`.

---

## Pre-conditions

- `kind ∈ {internal_gate, consumer_contract, provider_contract}` is validated
  (`packages/dq_core/contract/validator.py:23`, `VALID_KINDS`) and surfaced on
  `ContractOut.kind` (`services/api/schemas/contract_schemas.py`).
- Coverage summary already splits `with_internal_gate` vs `with_contract_checks`
  (`services/api/routers/metrics.py:89`).
- All existing tests pass (`pytest` + `npm run test`).

> **Naming note**: the shipped implementation uses **`kind`** with values
> `internal_gate | consumer_contract | provider_contract` (not the ADR §9 OP-1
> `boundary`/`internal|inbound|outbound` proposal). Batch 4 stays on the shipped
> `kind` vocabulary throughout — do not reintroduce `boundary`.

---

## Background — the category confusion to remove

`services/api/routers/objects.py:379` gates the entire compliance → incident →
notify block on **lifecycle only**, never on `kind`:

```python
# CURRENT (objects.py:377-383) — kind-blind
if _contract_lifecycle_map().get(object_id) == "active":
    from dq_core.contract.compliance import compute_compliance
    previous = store.get_compliance(object_id)
    new_compliance = compute_compliance(summary.results)
    store.set_compliance(object_id, contract_version, new_compliance, run_id)
    ...
    title = f"Contract-Breach: {object_id} v{contract_version or '?'}"
    incident_id = store.open_incident(...)
    notify_breach(...)
```

So an **active `internal_gate`** today gets: a governance compliance row
(`dq_compliance`), a SLA event (`dq_compliance_events` → `get_sla`), a
"Contract-Breach" incident, and a breach notification. That is exactly the
category confusion ADR-0001 §0/§5 calls out. Batch 4 makes the consequence
follow the `kind`.

`kind` is per **product** (one artifact file per product, identity-joined
`id == product`), so the split is clean: a product is *either* governance-tracked
(`*_contract`) *or* engineering-tracked (`internal_gate`) — never both.

---

## Part A — Backend: Kind-Aware Compliance Decision

### A1. Kind lookup helper — `services/api/routers/objects.py`

Mirror the existing `_contract_lifecycle_map()` (`objects.py:29`) with a kind map
(or extend it to return `(lifecycle, kind)` tuples). Standalone keeps the diff
small:

```python
def _contract_kind_map() -> dict[str, str]:
    """Map product → kind from on-disk contracts (default internal_gate)."""
    import yaml
    from pathlib import Path
    out: dict[str, str] = {}
    base = Path(get_settings().contracts_dir)
    if not base.exists():
        return out
    for path in base.glob("*.y*ml"):
        if path.name.endswith(".active.yml"):
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        product = data.get("product") or path.stem
        out[product] = data.get("kind", "internal_gate")
    return out
```

### A2. Split the run-thread decision — `objects.py:377-433`

Replace the single lifecycle-gated block with a `kind`-branched one. Both
branches reuse `compute_compliance()` (`packages/dq_core/contract/compliance.py:15`)
as a **pure pass/fail oracle** — the difference is what gets persisted.

```python
# NEW
lifecycle = _contract_lifecycle_map().get(object_id)
kind = _contract_kind_map().get(object_id, "internal_gate")

if lifecycle == "active" and kind in ("consumer_contract", "provider_contract"):
    # ── Governance path (UNCHANGED behaviour) ───────────────────────────
    from dq_core.contract.compliance import compute_compliance
    previous = store.get_compliance(object_id)
    new_compliance = compute_compliance(summary.results)
    store.set_compliance(object_id, contract_version, new_compliance, run_id)
    newly_breached = new_compliance == "breached" and (
        not previous or previous.get("compliance") != "breached"
    )
    if newly_breached:
        failed = [...]                      # unchanged
        worst = "critical" if ... else "fail"
        title = f"Contract-Breach: {object_id} v{contract_version or '?'}"
        incident_id = store.open_incident(..., kind=kind, actor="system")
        owned_by, owners = _active_contract_owner(object_id)
        space = ...
        notify_breach(..., kind=kind, owned_by=owned_by, owners=owners, ...)
    elif new_compliance == "compliant" and previous and previous.get("compliance") == "breached":
        store.auto_resolve_incidents(object_id, run_id)

elif kind == "internal_gate":
    # ── Engineering-signal path (NEW) ───────────────────────────────────
    # NO dq_compliance / dq_compliance_events write → no governance ampel,
    # no SLA window, no ODCS. A failing gate is a team-internal signal only.
    from dq_core.contract.compliance import compute_compliance, BREACHED
    gate_state = compute_compliance(summary.results)   # pure oracle, not persisted
    if gate_state == BREACHED:
        failed = [
            r.name for r in summary.results
            if not r.passed and r.state == "executed" and r.severity in ("fail", "critical")
        ]
        worst = "critical" if any(
            r.severity == "critical" and not r.passed and r.state == "executed"
            for r in summary.results
        ) else "fail"
        title = f"Engineering-Signal: {object_id} (Gate)"
        incident_id = store.open_incident(
            product=object_id, run_id=run_id, severity=worst, title=title,
            failed_checks=failed, contract_version=contract_version,
            kind="internal_gate", actor="system",
        )
        owned_by, owners = _active_contract_owner(object_id)
        space = next(
            (o.get("space", "") for o in inventory
             if (o.get("id") or o.get("technicalName") or o.get("name")) == object_id), "",
        )
        from ..notify import notify_breach
        notify_breach(
            product=object_id, compliance="signal", run_id=run_id,
            contract_version=contract_version, failed_checks=failed, severity=worst,
            title=title, incident_id=incident_id, owned_by=owned_by, owners=owners,
            settings=settings, store=store, space=space, kind="internal_gate",
        )
    else:
        # recovery: resolve any open engineering-signal incident for this gate
        store.auto_resolve_incidents(object_id, run_id)
# else: draft gate / no artifact → nothing persisted (today's behaviour)
```

> **Design note — no compliance events for gates.** Engineering signals
> deliberately bypass `dq_compliance`/`dq_compliance_events`, so `get_sla()`
> (`sqlite_store.py:403`) returns `None` for a gate and the governance ampel is
> never coloured by internal noise. The "newly broken / recovered" transition is
> recovered for free from `open_incident`'s grouping (one open incident per
> product, `sqlite_store.py:244`) + `auto_resolve_incidents` (`:288`). Because
> `kind` is per-product, auto-resolve stays per-product and never crosses
> categories.

### A3. Persist `kind` on incidents — store + migration

`dq_incidents` (`migrations/004_incident_lifecycle.sql`) has no `kind`. Add it.

`packages/dq_core/store/migrations/007_incident_kind.sql`:

```sql
ALTER TABLE dq_incidents ADD COLUMN kind TEXT NOT NULL DEFAULT 'consumer_contract';
-- Backfill: every pre-Batch-4 incident was a governance breach (created under
-- the lifecycle==active path), so the contract default is the honest value.
```

`open_incident()` (`sqlite_store.py:244`) — add `kind: str = "consumer_contract"`
to the signature, persist it in the `INSERT INTO dq_incidents (... kind)` and the
grouped-append branch (leave existing `kind` untouched when appending an event to
an already-open incident). Surface `kind` in the incident read paths
(`get_incidents`, `get_incident`) and in `services/api/schemas/incident_schemas.py`
(add `kind: str = "consumer_contract"`).

> **Why store `kind`, not a derived `category`** — keeps one vocabulary
> (`ArtifactKind`) end-to-end. The UI derives "Engineering-Signal vs
> Contract-Breach" from `kind == "internal_gate"`, exactly as `Proposals.tsx`
> already badges proposal kind.

---

## Part B — Backend: Kind-Aware Notification Routing

ADR §5: gate signals → product/platform team; contract breaches →
consumer/governance. Achieved by threading `kind` into routing + an optional
`match_kind` rule facet (additive, wildcard when empty — existing rules keep
matching everything).

### B1. Notify functions take `kind` — `services/api/notify.py`

- `notify_breach()` (`notify.py:340`) and `notify_incident_transition()` (`:288`):
  add `kind: str = "consumer_contract"`; put it in `ctx` and pass to the resolver.
- `_resolve_with_store()` (`:182`) and `resolve_db_targets()` / `resolve_targets()`:
  forward `kind` to `_rule_matches`.

### B2. `match_kind` facet — `_rule_matches` (`notify.py:132-150`)

```python
# After the match_owner check (line 148), add:
if rule.get("match_kind") and rule["match_kind"] != kind:
    return False
```

### B3. Rule storage + API — migration + router

- `migrations/007_incident_kind.sql` (same file): 
  `ALTER TABLE dq_notification_rules ADD COLUMN match_kind TEXT DEFAULT '';`
- `add_notification_rule()` in the store: add `match_kind=""` param + column.
- `RuleIn` (`services/api/routers/notifications.py:104-108`): add
  `match_kind: str = ""`; validate against `{"", *VALID_KINDS}`; pass through at
  `:120-122`.
- Frontend Notifications rule editor: add a `kind` dropdown
  (`Alle | Internal Gate | Consumer | Provider`) — small addition, mirrors the
  existing severity/space facets.

---

## Part C — Backend: SLA, Coverage, ODCS Guard

### C1. SLA stays contract-only — `services/api/routers/contracts.py:738`

`get_contract_sla` reads `dq_compliance`/events; gates now have none, so it
already returns `current: "unknown"` + `null` windows for a gate. Make the
contract-only intent explicit and let the FE filter cleanly:

```python
# In get_contract_sla — add kind to the response:
data = _load_contract(product)
kind = (data or {}).get("kind", "internal_gate")
return {
    "product": product,
    "kind": kind,
    "current": compliance_row["compliance"] if compliance_row else "unknown",
    "windows": {"7d": ..., "30d": ..., "90d": ...},
}
```

### C2. Kind-split governance counts — `services/api/routers/metrics.py:89`

Extend `/coverage/summary` so the cockpit can show governance breaches and
engineering-signal counts separately:

```python
# Reuse internal_gate_products / boundary_contract_products (already computed).
contracts_breached = 0
for p in boundary_contract_products:
    row = store.get_compliance(p)
    if row and row.get("compliance") == "breached":
        contracts_breached += 1

# gates_failing: internal gates whose latest run has an open engineering-signal
gates_failing = store.count_open_incidents(kind="internal_gate")  # new thin store helper

return {
    ...existing keys...,
    "contracts_breached": contracts_breached,
    "gates_failing": gates_failing,
}
```

`count_open_incidents(kind)` — thin `SELECT COUNT(*) FROM dq_incidents WHERE
status != 'resolved' AND kind=?` helper in `sqlite_store.py`.

### C3. ODCS export guard — `contracts.py:782` + `odcs_export.py`

ADR §9 OP-3: never export an `internal_gate` (it has no counterparty, so it does
not belong in an external contract registry).

```python
# services/api/routers/contracts.py — in export_odcs(), after _load_contract (line 791):
if data.get("kind", "internal_gate") == "internal_gate":
    raise HTTPException(
        status_code=409,
        detail="Internal gates have no counterparty and are not exported to ODCS "
               "(ADR-0001 §6/OP-3). Promote to a contract first.",
    )
```

Belt-and-braces guard inside `to_odcs()` (`odcs_export.py:28`) — raise
`ValueError` on `internal_gate` so any other caller is protected too — and carry
the kind through the documented lossless escape hatch (`odcs_export.py:17`):

```python
# Where odcs dict is built (odcs_export.py:106), add:
odcs["customProperties"] = [{"property": "signal_kind", "value": contract.get("kind", "")}]
```

---

## Part D — Frontend: Types + Incident / My-Work Kind Awareness

### D1. Types — `apps/cockpit/src/types/index.ts`

```typescript
// Incident (lines 613-625) — add:
  kind?: ArtifactKind;                 // 'internal_gate' → Engineering-Signal

// LineageNode (lines 444-461) — add:
  kind?: ArtifactKind;

// SlaResponse (lines 359-363) — add:
  kind?: ArtifactKind;

// CoverageSummary (lines 366-374) — add:
  contracts_breached?: number;
  gates_failing?: number;
```

### D2. i18n — `apps/cockpit/src/i18n/de.ts`

```typescript
// incidents section (lines 263+) — add:
  kindContract: 'Contract-Breach',
  kindGate: 'Engineering-Signal',
  filterKind: 'Art',
  filterAll: 'Alle',

// new top-level signal labels reused by Lineage legend + Cockpit:
  // (or extend the existing `compliance` block at line 83)
  gateSignal: 'Gate-Signal',
  governanceBreach: 'Governance-Breach',
```

### D3. Incidents page — `apps/cockpit/src/pages/Incidents.tsx`

- Add a `kind` badge next to the title/severity in both the table row and the
  `IncidentDrawer` header (precedent: the `Proposals.tsx` kind badge — green
  `--qual` for `internal_gate`/Gate, blue `--cont` for contract).
- Add a kind filter chip (`Alle | Engineering-Signal | Contract-Breach`)
  alongside the existing status tabs — purely client-side over the already-fetched
  list, or pass a `kind` query param if `useIncidents` is extended.

### D4. My Work — `apps/cockpit/src/pages/MyWork.tsx`

Split the incident lists by `kind` so the role landing reflects ADR §5
addressees: a steward sees **Contract-Breaches** on their products first;
operators/platform see **Engineering-Signals**. Add a small section divider +
the kind badge per row (reuse D3 badge). No new endpoint — group the existing
`useIncidents()` result by `i.kind === 'internal_gate'`.

---

## Part E — Frontend: Lineage Border + Cockpit SLA + Governance

### E1. LineageMap per-kind border — `apps/cockpit/src/pages/LineageMap.tsx`

Border **colour** is already taken by the coverage flag
(`coverageColor(coverage_flag)`, stylesheet `:479`). To add kind differentiation
without collision, use **border *style*** for kind and keep colour = coverage:

```typescript
// Node data (around :433) — add:
kind: n.kind ?? 'internal_gate',

// Stylesheet (:468) — keep border-color = coverage, add per-kind dash:
{
  selector: 'node[kind = "internal_gate"]',
  style: { 'border-style': 'dashed' },   // gate = dashed, contract = solid (default)
},
```

Populate `LineageNode.kind` from the backend: `get_coverage()`
(`packages/dq_core/lineage/loader.py`) already receives `gate_products` /
`contract_products` (Batch 3 A1) — set `kind` on each node there
(`internal_gate` vs the contract kind from `contract_products`). Add a one-line
legend entry ("— gestrichelt = Gate, durchgehend = Contract").

### E2. Cockpit SLA panel — `apps/cockpit/src/pages/Cockpit.tsx:244`

The SLA panel maps "active contracts" to `<SlaRow>` (`:253`). Filter that list to
`kind ∈ {consumer_contract, provider_contract}` so gates no longer show an empty
SLA row. Add a compact "Gate-Signale: N" stat (from
`CoverageSummary.gates_failing`) next to "Open Incidents" so failing gates stay
visible without polluting the governance SLA view.

### E3. Governance traffic-light — `apps/cockpit/src/pages/Governance.tsx`

Ensure the compliance/onboarding surface (the Batch 3 onboarding state landed
here, not in a `Compliance.tsx`) only counts `*_contract` toward the
governance ampel; show `contracts_breached` from the summary. Internal gates are
explicitly out of this panel (link them to Incidents/Health instead).

---

## Part F — Tests

### F1. Backend — compliance/incident split (`tests/api/test_*` + `tests/unit/`)

```python
def test_internal_gate_failure_emits_signal_not_compliance(client, seeded_gate_failing):
    """Active internal_gate with a failing fail/critical check:
       - NO dq_compliance row, NO SLA event
       - opens an Engineering-Signal incident (kind=internal_gate)"""
    client.post(f"/api/objects/{seeded_gate_failing}/run"); _await_run(...)
    assert store.get_compliance(seeded_gate_failing) is None
    inc = [i for i in store.get_incidents() if i["product"] == seeded_gate_failing]
    assert inc and inc[0]["kind"] == "internal_gate"
    assert inc[0]["title"].startswith("Engineering-Signal")

def test_contract_failure_sets_compliance_and_breach_incident(client, seeded_contract_failing):
    client.post(f"/api/objects/{seeded_contract_failing}/run"); _await_run(...)
    assert store.get_compliance(seeded_contract_failing)["compliance"] == "breached"
    inc = [i for i in store.get_incidents() if i["product"] == seeded_contract_failing]
    assert inc and inc[0]["kind"] in ("consumer_contract", "provider_contract")
    assert inc[0]["title"].startswith("Contract-Breach")

def test_gate_recovery_resolves_signal(client, seeded_gate): ...
def test_gate_has_no_sla(client, seeded_gate):
    assert client.get(f"/api/contracts/{seeded_gate}/sla").json()["windows"]["7d"] is None

def test_odcs_export_rejects_internal_gate(client, seeded_gate):
    assert client.get(f"/api/contracts/{seeded_gate}/export/odcs").status_code == 409

def test_coverage_summary_kind_split(client):
    body = client.get("/api/coverage/summary").json()
    assert "contracts_breached" in body and "gates_failing" in body

def test_notify_rule_match_kind():
    """A rule with match_kind=internal_gate matches a gate signal, not a contract breach."""
    assert _rule_matches({"match_kind": "internal_gate"}, kind="internal_gate", ...) is True
    assert _rule_matches({"match_kind": "internal_gate"}, kind="consumer_contract", ...) is False
```

### F2. Migration test

`007_incident_kind.sql` applies idempotently; pre-existing incident rows backfill
to `consumer_contract`; `dq_notification_rules.match_kind` defaults to `''`.

### F3. Frontend

No change to `role.test.ts`. `tsc --noEmit` clean (new `kind?` fields are
optional). Visual verification via acceptance criteria.

---

## Execution order

```
 A1  _contract_kind_map() helper
 A2  Split run-thread decision (governance vs engineering-signal)
 A3  open_incident(kind=…) + migration 007 + incident schema
  ↓
 B1  notify_breach / notify_incident_transition take kind
 B2  _rule_matches match_kind facet
 B3  rules table match_kind + RuleIn + store + Notifications editor
  ↓
 C1  SLA endpoint returns kind (contract-only intent)
 C2  coverage/summary: contracts_breached + gates_failing (+ count_open_incidents)
 C3  ODCS export guard (router 409 + to_odcs ValueError + customProperties)
  ↓
 D1  Types (Incident.kind, LineageNode.kind, SlaResponse.kind, CoverageSummary)
 D2  i18n
 D3  Incidents page kind badge + filter
 D4  My Work split by kind
  ↓
 E1  LineageMap per-kind border-style + loader sets node.kind
 E2  Cockpit SLA filtered to contracts + Gate-Signale stat
 E3  Governance traffic-light contract-only
  ↓
 F1–F3  Tests
```

---

## Acceptance criteria

| # | Criterion | How to verify |
|---|-----------|---------------|
| A1 | Failing **active internal_gate** writes **no** `dq_compliance` row and **no** SLA event | API test / inspect store |
| A2 | Failing internal_gate opens an incident titled `Engineering-Signal: …`, `kind=internal_gate` | API test |
| A3 | Failing **consumer/provider_contract** still sets `breached` + `Contract-Breach` incident (`kind` set) | API test |
| A4 | Gate recovery auto-resolves its engineering-signal incident | API test |
| B1 | A notification rule with `match_kind=internal_gate` matches gate signals only | unit test |
| B2 | Existing rules (empty `match_kind`) keep matching all kinds (no regression) | unit test |
| C1 | `GET /contracts/{gate}/sla` → `windows` all `null`; response carries `kind` | curl |
| C2 | `GET /coverage/summary` returns `contracts_breached` + `gates_failing` | curl |
| C3 | `GET /contracts/{gate}/export/odcs` → 409; contract export carries `signal_kind` customProperty | curl / API test |
| D1 | Incidents table + drawer show "Engineering-Signal" vs "Contract-Breach" badge | Visual |
| D2 | Incidents kind filter narrows the list | Visual |
| D3 | My Work splits Contract-Breaches from Engineering-Signals | Visual |
| E1 | Lineage gate nodes render dashed border, contract nodes solid; coverage colour unchanged | Visual |
| E2 | Cockpit SLA panel lists only contracts; "Gate-Signale: N" stat shown | Visual |
| E3 | Governance ampel reflects only `*_contract`; gates absent | Visual |
| F1 | All Python tests pass (`pytest`) | CLI |
| F2 | Migration 007 applies idempotently, backfill correct | CLI |
| F3 | `npm run test` green; `tsc --noEmit` clean | CLI |

---

## Out of scope (later batches)

- **Garantie-level `kind` override** (ADR §9 OP-2 phase 2): a dataset carrying
  both contract clauses *and* internal gates → two compliance states per dataset.
  Batch 4 stays set/product-level (the 80% reality).
- **Breaking-change diff gated on kind** (ADR §9 step 3 / O1): SemVer + breaking
  protection only for `*_contract`. Independent track.
- **Counterparty + `depends_on` chains** (ADR §10): cross-product contract chains,
  transitive compliance, upstream breaking visibility.
- **Escalation / digest** for engineering signals (no scheduler in repo — same
  carve-out as UX-N2).
- **Per-kind notification *channel defaults*** (auto-route gates to a platform
  channel without an explicit rule) — Batch 4 ships the `match_kind` mechanism;
  opinionated defaults come later.
- **Incident analytics by kind** (MTTR split gate vs contract) — needs the kind
  column to accrue history first.
