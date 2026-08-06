# Batch 2 — `kind` Discriminator + Compliance Enrichment

> **Goal**: Introduce the ADR-0001 `kind` discriminator (`internal_gate`,
> `consumer_contract`, `provider_contract`) across the full stack; add the
> Segment-Control "Internal | Contract | All" to the Object-Detail Checks tab;
> enrich the Compliance page with relocated SLA panels.
>
> **Depends on**: Batch 1 (nav restructure) must be merged first.

---

## Pre-conditions

- Batch 1 is merged (Compliance.tsx exists, `/compliance` route works).
- All existing tests pass (`npm run test` + `pytest`).
- Python 3.12+, Node 18+.

---

## Part A — Backend: `kind` Foundation

### A1. Data model — `packages/dq_core/contract/model.py`

Add `kind` to `Contract`:

```python
# OLD (line 17–20)
@dataclass
class Contract:
    product: str
    dataset: str
    owned_by: str = "platform"

# NEW
VALID_KINDS: frozenset[str] = frozenset({"internal_gate", "consumer_contract", "provider_contract"})

@dataclass
class Contract:
    product: str
    dataset: str
    owned_by: str = "platform"
    kind: str = "internal_gate"
```

Update `from_dict` to read `kind`:

```python
# In from_dict (line 29–38), add kind extraction:
kind=str(data.get("kind", "internal_gate")),
```

Update `to_dict` to include `kind`:

```python
# In to_dict (line 42–50), add:
"kind": self.kind,
```

### A2. Data model — `packages/dq_core/engine/models.py`

Add `kind` to both `CheckDef` and `CheckResult`:

```python
# CheckDef — after owned_by (line 22), add:
    kind: str = "internal_gate"

# CheckResult — after type (line 44), add:
    kind: str = "internal_gate"
```

Also add to module-level constants:

```python
# After VALID_SEVERITIES (line 8), add:
VALID_KINDS: frozenset[str] = frozenset({"internal_gate", "consumer_contract", "provider_contract"})
```

### A3. Compiler — `packages/dq_core/contract/compiler.py`

Propagate `kind` from contract to compiled checks.

Update `_mk()` (lines 81–85) to accept and forward `kind`:

```python
# OLD
def _mk(template_id: str, dataset: str, params: dict[str, Any], *,
        name: str, expect: str, severity: str, owner: str, unit: str = "") -> CheckDef:
    return CheckDef(name=name, sql=_bind(template_id, dataset, params),
                    expect=expect, severity=severity, type=template_id,
                    unit=unit, owned_by=owner)

# NEW
def _mk(template_id: str, dataset: str, params: dict[str, Any], *,
        name: str, expect: str, severity: str, owner: str, unit: str = "",
        kind: str = "internal_gate") -> CheckDef:
    return CheckDef(name=name, sql=_bind(template_id, dataset, params),
                    expect=expect, severity=severity, type=template_id,
                    unit=unit, owned_by=owner, kind=kind)
```

Update `compile_contract()` to extract and propagate `kind`:

```python
# After owner extraction (line 99–101), add:
    kind = str(contract.get("kind", "internal_gate"))
    if kind not in VALID_KINDS:
        raise CompileError(f"kind muss {sorted(VALID_KINDS)} sein, nicht {kind!r}")
```

Import `VALID_KINDS`:

```python
# Line 20 — update import:
from ..engine.models import CheckDef, DatasetConfig, VALID_OWNERS, VALID_SEVERITIES, VALID_KINDS
```

Pass `kind=kind` to every `_mk()` call (lines 110, 121, 126, 137, 148, 155,
164, 171). All calls get the same extra kwarg — search-and-replace is safe:

```python
# Each _mk(..., owner=owner) becomes _mk(..., owner=owner, kind=kind)
# Each _mk(..., owner=owner, unit="s") becomes _mk(..., owner=owner, kind=kind, unit="s")
# Each _mk(..., owner=owner, unit="%") becomes _mk(..., owner=owner, kind=kind, unit="%")
```

### A4. Store migration — `packages/dq_core/store/migrations/006_artifact_kind.sql`

Create new file:

```sql
-- ADR-0001: artifact kind discriminator (internal_gate | consumer_contract | provider_contract).
-- Default to internal_gate: existing contracts created before kind-awareness are DQ-First gates.
ALTER TABLE dq_check_results ADD COLUMN kind TEXT NOT NULL DEFAULT 'internal_gate';
```

### A5. Store — `packages/dq_core/store/sqlite_store.py`

Update `save_run()` to persist `kind`:

```python
# OLD INSERT (lines 118–127):
"""INSERT INTO dq_check_results
   (run_id, check_name, sql_text, expect_expr, severity,
    passed, actual_value, error_message, duration_ms, state, check_type)
   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
(
    summary.run_id, result.name, result.sql, result.expect,
    result.severity, int(result.passed),
    str(result.actual_value) if result.actual_value is not None else None,
    result.error, result.duration_ms, result.state, result.type,
),

# NEW:
"""INSERT INTO dq_check_results
   (run_id, check_name, sql_text, expect_expr, severity,
    passed, actual_value, error_message, duration_ms, state, check_type, kind)
   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
(
    summary.run_id, result.name, result.sql, result.expect,
    result.severity, int(result.passed),
    str(result.actual_value) if result.actual_value is not None else None,
    result.error, result.duration_ms, result.state, result.type, result.kind,
),
```

Update any query that reads check results to also select `kind`. Search for
`SELECT.*check_type` and `SELECT.*dq_check_results` — ensure `kind` is
included in the result dict where check_type is already returned.

### A6. API schemas — `services/api/schemas/run_schemas.py`

Add `kind` to `CheckResultOut`:

```python
# OLD (lines 7–19)
class CheckResultOut(BaseModel):
    ...
    type: str = ""

# NEW — add after type:
    kind: str = "internal_gate"
```

### A7. API schemas — `services/api/schemas/contract_schemas.py`

Add `kind` to both `ContractIn` and `ContractOut`:

```python
# ContractIn (line 7–16) — add after version:
    kind: str = "internal_gate"

# ContractOut (line 19–28) — add after version:
    kind: str = "internal_gate"

# CheckDefOut (line 31–37) — add after owned_by:
    kind: str = "internal_gate"
```

### A8. Coverage endpoint — `services/api/routers/metrics.py`

Extend `/api/coverage/summary` response with kind-aware counts:

```python
# After line 127, add to the return dict:
    "with_internal_gate": ...,
    "with_contract_checks": ...,
```

Compute these by scanning the contracts dir for `kind` field:

```python
# After active_products computation (line 102), add:
    # kind-aware: contracts with kind != internal_gate are contract-checks
    contract_products: set[str] = set()
    gate_products: set[str] = set()
    for path in (Path(settings.contracts_dir).glob("*.y*ml") if Path(settings.contracts_dir).exists() else []):
        if path.name.endswith(".active.yml"):
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        product = data.get("product") or path.stem
        kind = data.get("kind", "internal_gate")
        if kind == "internal_gate":
            gate_products.add(product)
        else:
            contract_products.add(product)

# Then in the return dict:
    "with_internal_gate": len([o for o in object_ids if o in gate_products]),
    "with_contract_checks": len([o for o in object_ids if o in contract_products]),
```

---

## Part B — Frontend: Types & Segment-Control

### B1. Types — `apps/cockpit/src/types/index.ts`

Add `ArtifactKind` type and update `CheckResult`:

```typescript
// After CheckState type (line 21), add:
export type ArtifactKind = 'internal_gate' | 'consumer_contract' | 'provider_contract';

// Update CheckResult (lines 109–119) — add kind:
export interface CheckResult {
  name: string;
  sql: string;
  expect: string;
  severity: Severity;
  passed: boolean;
  actual_value?: string;
  error?: string;
  duration_ms: number;
  state: CheckState;
  kind: ArtifactKind;       // ← NEW
}
```

Also update `CoverageSummary` (find its definition, add the new fields):

```typescript
// Add to CoverageSummary interface:
  with_internal_gate: number;
  with_contract_checks: number;
```

### B2. i18n — `apps/cockpit/src/i18n/de.ts`

Add kind-related labels:

```typescript
// In the cockpit section, after existing keys, add:
  kind: {
    internal_gate: 'Internal',
    consumer_contract: 'Contract',
    provider_contract: 'Contract',
    all: 'Alle',
  },
  segmentControl: {
    internal: 'Internal',
    contract: 'Contract',
    all: 'Alle',
  },
```

Add Compliance section keys for the relocated SLA panel:

```typescript
// In the compliance section (currently named 'governance'), add:
  slaTitle: 'SLA-Übersicht (aktive Contracts)',
  slaProduct: 'Produkt',
  slaCurrent: 'Aktuell',
  sla7d: '7 Tage',
  sla30d: '30 Tage',
  sla90d: '90 Tage',
  slaEmpty: 'Keine aktiven Contracts',
```

### B3. Object-Detail Checks Tab — `apps/cockpit/src/pages/ObjectDetail.tsx`

This is the main UI change: add a Segment-Control above the checks table that
filters checks by `kind`.

**B3a. Add state for kind filter**

```typescript
// After the Tab type (line 25), add:
type KindFilter = 'internal' | 'contract' | 'all';

// Inside the ObjectDetail component, add state:
const [kindFilter, setKindFilter] = useState<KindFilter>('all');
```

**B3b. Create the SegmentControl component**

Add inside ObjectDetail.tsx (above the default export) or as a shared component
in `apps/cockpit/src/components/ui/SegmentControl.tsx`:

```tsx
function SegmentControl<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { key: T; label: string }[];
}) {
  return (
    <div style={{
      display: 'inline-flex', gap: 0,
      background: 'var(--bg-2)', borderRadius: 6,
      border: '1px solid var(--line)', padding: 2,
    }}>
      {options.map(o => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          style={{
            padding: '4px 12px', fontSize: 11, borderRadius: 4,
            border: 'none', cursor: 'pointer',
            background: value === o.key ? 'var(--cont)' : 'transparent',
            color: value === o.key ? '#fff' : 'var(--fg-3)',
            fontWeight: value === o.key ? 600 : 400,
            transition: 'all var(--t)',
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
```

**B3c. Filter checks and render the segment control**

In the Checks tab rendering, add the segment control above the table and filter
the results:

```tsx
// Find where the checks table is rendered (the checks tab case).
// Before the Table component, add:

const kindOptions = [
  { key: 'all' as const, label: t.segmentControl.all },
  { key: 'internal' as const, label: t.segmentControl.internal },
  { key: 'contract' as const, label: t.segmentControl.contract },
];

const filteredResults = (latestRun?.results ?? []).filter(r => {
  if (kindFilter === 'all') return true;
  if (kindFilter === 'internal') return r.kind === 'internal_gate';
  return r.kind === 'consumer_contract' || r.kind === 'provider_contract';
});

// Render above the checks table:
<div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
  <SegmentControl value={kindFilter} onChange={setKindFilter} options={kindOptions} />
</div>
```

Replace the table's `rows` prop from `latestRun.results` to `filteredResults`.

**B3d. Add kind badge column to checks table**

Add a column to the checks table columns array:

```tsx
// After the existing columns, add before the last column:
{
  key: 'kind',
  header: 'Typ',
  render: (r: CheckResult) => (
    <span style={{
      fontSize: 10, borderRadius: 3, padding: '1px 6px',
      background: r.kind === 'internal_gate'
        ? 'color-mix(in srgb, var(--qual) 14%, transparent)'
        : 'color-mix(in srgb, var(--cont) 14%, transparent)',
      color: r.kind === 'internal_gate' ? 'var(--qual)' : 'var(--cont)',
      border: `1px solid ${r.kind === 'internal_gate' ? 'var(--qual)' : 'var(--cont)'}`,
    }}>
      {r.kind === 'internal_gate' ? 'Internal' : 'Contract'}
    </span>
  ),
},
```

---

## Part C — Compliance Page Enrichment

### C1. Relocate SLA components to Compliance — `apps/cockpit/src/pages/Compliance.tsx`

The `SlaBar` and `SlaRow` components were removed from Cockpit.tsx in Batch 1.
Recreate them in Compliance.tsx (or move to a shared component file).

Add below the existing imports in Compliance.tsx:

```tsx
import { useContracts, useContractSla } from '@/api/contracts';
```

Add `SlaBar` and `SlaRow` components (identical to the originals from
Cockpit.tsx lines 66–93 — see Batch 1 doc for the removed code).

Update the Compliance component to show SLA panel below the existing content:

```tsx
export default function Compliance() {
  const { data: objects = [], isLoading, isError, refetch } = useObjects();
  const { data: contracts = [] } = useContracts();                    // ← NEW
  const activeContracts = contracts.filter(c => c.lifecycle === 'active'); // ← NEW

  return (
    <div className="page-full">
      <h1 ...>{t.governance.title}</h1>

      {/* ... existing G1-policy and Lifecycle panels ... */}

      {/* NEW: SLA Overview — relocated from Health */}
      {activeContracts.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Panel title={t.governance.slaTitle}>
            <div style={{
              display: 'flex', gap: 16, padding: '0 0 6px 0',
              borderBottom: '1px solid var(--line)', marginBottom: 4
            }}>
              <span style={{ fontSize: 10, color: 'var(--fg-3)', flex: 1 }}>{t.governance.slaProduct}</span>
              <span style={{ fontSize: 10, color: 'var(--fg-3)', minWidth: 64 }}>{t.governance.slaCurrent}</span>
              <span style={{ fontSize: 10, color: 'var(--fg-3)', width: 84 }}>{t.governance.sla7d}</span>
              <span style={{ fontSize: 10, color: 'var(--fg-3)', width: 84 }}>{t.governance.sla30d}</span>
              <span style={{ fontSize: 10, color: 'var(--fg-3)', width: 84 }}>{t.governance.sla90d}</span>
            </div>
            {activeContracts.map(c => <SlaRow key={c.product} product={c.product} />)}
          </Panel>
        </div>
      )}

      {/* Existing: Object Status table ... */}
    </div>
  );
}
```

### C2. Add SLA i18n keys to governance section

Ensure these keys exist in `de.ts` under the `governance` section (they were
already present before Batch 1 since they were used by Cockpit.tsx — but verify
they still exist after Batch 1's removal of the SLA panel from Cockpit):

```typescript
governance: {
  // ... existing keys ...
  slaTitle: 'SLA-Übersicht (aktive Contracts)',
  slaProduct: 'Produkt',
  slaCurrent: 'Aktuell',
  sla7d: '7 Tage',
  sla30d: '30 Tage',
  sla90d: '90 Tage',
  slaEmpty: 'Keine aktiven Contracts',
}
```

> Note: The SLA keys currently live under `cockpit.*` (`t.cockpit.slaTitle`
> etc.). In Compliance.tsx, reference them as `t.governance.slaTitle` — so
> either add duplicates under `governance` or move them. Recommendation: **add
> under `governance`** and remove the now-unused `cockpit.sla*` keys.

---

## Part D — Tests

### D1. Backend: compiler test — `tests/unit/test_compiler.py` (or equivalent)

Add test that `kind` propagates through compilation:

```python
def test_compile_contract_propagates_kind():
    contract = {
        "product": "test_ds",
        "dataset": "test_ds",
        "kind": "consumer_contract",
        "guarantees": {
            "volume": {"min_rows": 1},
        },
    }
    config = compile_contract(contract)
    assert all(c.kind == "consumer_contract" for c in config.checks)


def test_compile_contract_defaults_to_internal_gate():
    contract = {
        "product": "test_ds",
        "dataset": "test_ds",
        "guarantees": {
            "volume": {"min_rows": 1},
        },
    }
    config = compile_contract(contract)
    assert all(c.kind == "internal_gate" for c in config.checks)


def test_compile_contract_rejects_invalid_kind():
    contract = {
        "product": "test_ds",
        "dataset": "test_ds",
        "kind": "invalid",
        "guarantees": {"volume": {"min_rows": 1}},
    }
    with pytest.raises(CompileError):
        compile_contract(contract)
```

### D2. Backend: store migration test

After applying migration 006, verify `kind` column exists:

```python
def test_migration_006_adds_kind_column(store):
    conn = store._conn()
    cursor = conn.execute("PRAGMA table_info(dq_check_results)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "kind" in columns
```

### D3. Backend: API test — verify `kind` in response

```python
def test_check_result_includes_kind(client, seeded_run):
    resp = client.get(f"/api/runs/{seeded_run}")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert all("kind" in r for r in results)
```

### D4. Frontend: no new test file needed

Existing `role.test.ts` is unaffected. The Segment-Control is best verified
visually (see acceptance criteria below) or with a future component test.

---

## Execution order

```
 A1  Contract model (kind field)
 A2  Engine models (kind on CheckDef, CheckResult)
 A3  Compiler (propagate kind)
 A4  Migration 006 (ALTER TABLE)
 A5  Store save_run (persist kind)
 A6  Run schemas (CheckResultOut.kind)
 A7  Contract schemas (ContractIn/Out.kind, CheckDefOut.kind)
 A8  Coverage endpoint (kind-aware counts)
  ↓
 B1  Frontend types (ArtifactKind, CheckResult.kind)
 B2  i18n (kind labels, segment control labels, SLA keys)
 B3  ObjectDetail Segment-Control
  ↓
 C1  Compliance SLA enrichment
 C2  i18n key relocation
  ↓
 D1–D3  Tests
```

Parts A, B, C can largely be parallelized — B depends on A6/A7 for type
alignment, C is independent.

---

## Acceptance criteria

| # | Criterion | How to verify |
|---|-----------|---------------|
| A1 | Contract YAML with `kind: consumer_contract` compiles successfully | `pytest tests/unit/test_compiler.py` |
| A2 | Contract without `kind` defaults to `internal_gate` | Unit test |
| A3 | Invalid `kind` raises CompileError | Unit test |
| A4 | Migration 006 applies cleanly | `pytest` (store fixture auto-migrates) |
| A5 | `GET /api/runs/{id}` response includes `kind` on each result | curl / httpie |
| A6 | `GET /api/contracts/{product}` response includes `kind` | curl / httpie |
| A7 | `GET /api/coverage/summary` returns `with_internal_gate` + `with_contract_checks` | curl / httpie |
| B1 | Object-Detail Checks tab shows Segment-Control (Internal \| Contract \| All) | Visual: open `/objects/{id}`, click Checks tab |
| B2 | Clicking "Internal" filters to only `internal_gate` checks | Visual |
| B3 | Clicking "Contract" filters to only `*_contract` checks | Visual |
| B4 | Clicking "All" shows all checks (default) | Visual |
| B5 | Kind badge column shows "Internal" (green) or "Contract" (blue) per check | Visual |
| C1 | Compliance page shows SLA Overview panel with active contracts | Visual: navigate to `/compliance` |
| C2 | SLA bars show 7d / 30d / 90d windows per product | Visual |
| D1 | All Python tests pass (`pytest`) | CLI |
| D2 | All frontend tests pass (`npm run test`) | CLI |
| D3 | No TypeScript errors (`tsc --noEmit`) | CLI |

---

## Out of scope (later batches)

- Coverage-Map dimension switcher (Internal | Contract | All on nodes)
- Promotion-Flow UI (copy-semantics gate → contract)
- My Work kind-awareness (gate-proposals vs contract-proposals)
- Dual-Run awareness in Runs page
- Compliance-Ampel (traffic-light per contract) — needs `kind`-aware
  compliance state machine
- Contract-SLA-Breach list under Compliance (needs backend aggregation)
- Onboarding state for Govern-block (DQ-First welcome when no contracts exist)
