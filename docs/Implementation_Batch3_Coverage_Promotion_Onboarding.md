# Batch 3 — Coverage Dimension Switcher + Promotion Flow + Govern Onboarding

> **Goal**: Make the `kind` discriminator visible in the Coverage Map via a
> dimension switcher (Internal | Contract | All); add the Promotion-Flow CTA
> that bridges DQ-First gates to Contract governance; show an onboarding state
> when the Govern block has no contracts yet.
>
> **Depends on**: Batch 2 (kind discriminator) must be merged first.

---

## Pre-conditions

- Batch 2 merged: `kind` field on `Contract`, `CheckDef`, `CheckResult`,
  `CheckResultOut`, `ContractOut`; migration 006 applied; Segment-Control on
  Object-Detail works.
- All existing tests pass (`npm run test` + `pytest`).

---

## Part A — Backend: Kind-Aware Coverage + Promotion Endpoint

### A1. Lineage coverage annotation — `packages/dq_core/lineage/loader.py`

Extend `get_coverage()` to annotate each node with both `has_internal_gate`
and `has_contract` (where "has_contract" means `consumer_contract` or
`provider_contract`, not `internal_gate`).

**Change the signature** to accept a richer contracts data structure:

```python
# OLD signature (lines 17–21)
def get_coverage(
    nodes: list[dict],
    object_statuses: list[dict],
    contracts: list[str],
) -> list[dict]:

# NEW signature
def get_coverage(
    nodes: list[dict],
    object_statuses: list[dict],
    contracts: list[str],
    *,
    gate_products: set[str] | None = None,
    contract_products: set[str] | None = None,
) -> list[dict]:
```

**Update the annotation loop** (lines 30–56):

```python
    status_by_name = {s.get("dataset"): s for s in object_statuses}
    contracted = set(contracts)
    gates = gate_products or set()
    contracts_set = contract_products or set()

    result = []
    for node in nodes:
        node_id = node.get("id") or node.get("technicalName") or ""
        status = status_by_name.get(node_id, {})
        has_any_contract = node_id in contracted
        has_gate = node_id in gates
        has_boundary_contract = node_id in contracts_set

        if node.get("objectType") in ("external_raw", "unknown") or not node_id:
            flag = "○"
        elif not has_any_contract:
            flag = "▲"
        elif status.get("status") in ("fail", "critical", "error"):
            flag = "◐"
        elif status.get("status") == "pass":
            flag = "●"
        else:
            flag = "◐"

        result.append({
            **node,
            "coverage_flag": flag,
            "dq_status": status.get("status", "unknown"),
            "last_run": status.get("last_run"),
            "has_contract": has_any_contract,
            "has_internal_gate": has_gate,
            "has_boundary_contract": has_boundary_contract,
        })
    return result
```

### A2. Lineage router — `services/api/routers/lineage.py`

Pass kind-aware contract sets to `get_coverage()`:

```python
# OLD (lines 30–38)
    contracts_dir = Path(settings.contracts_dir)
    contracted = (
        [p.stem for p in contracts_dir.glob("*.y*ml") if not p.name.endswith(".active.yml")]
        if contracts_dir.exists()
        else []
    )
    annotated_nodes = get_coverage(nodes, object_statuses, contracted)

# NEW
    import yaml as _yaml
    contracts_dir = Path(settings.contracts_dir)
    contracted: list[str] = []
    gate_products: set[str] = set()
    contract_products: set[str] = set()

    if contracts_dir.exists():
        for path in contracts_dir.glob("*.y*ml"):
            if path.name.endswith(".active.yml"):
                continue
            product = path.stem
            contracted.append(product)
            try:
                data = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                gate_products.add(product)  # default to gate if unreadable
                continue
            kind = data.get("kind", "internal_gate")
            if kind == "internal_gate":
                gate_products.add(product)
            else:
                contract_products.add(product)

    annotated_nodes = get_coverage(
        nodes, object_statuses, contracted,
        gate_products=gate_products,
        contract_products=contract_products,
    )
```

### A3. Promotion endpoint — `services/api/routers/contracts.py`

Add a new endpoint that implements the Promotion act (ADR-0001: copy-semantics,
gate keeps its copy, new contract artifact created):

```python
@router.post("/{product}/promote", response_model=ContractOut)
def promote_to_contract(
    product: str,
    principal: PrincipalDep,
    store: StoreDep = ...,
):
    """ADR-0001 Promotion: copy guarantees from an internal_gate into a new
    consumer_contract. The gate keeps its copy — two artifacts, same rules.

    Creates the contract as draft; must be approved separately.
    """
    from dq_core.contract.validator import validate_contract

    _validate_product(product)
    data = _load_contract(product)
    if not data:
        raise HTTPException(status_code=404, detail=f"Contract {product!r} not found")
    if data.get("kind") != "internal_gate":
        raise HTTPException(
            status_code=409,
            detail=f"Only internal_gate artifacts can be promoted (got {data.get('kind')!r}).",
        )

    _require_write(principal, data)

    # Copy semantics: create a consumer_contract with same guarantees.
    promoted = dict(data)
    promoted["kind"] = "consumer_contract"
    promoted["lifecycle"] = "draft"
    promoted["version"] = "1.0.0"

    # Write as a separate file: {product}_contract.yaml
    contract_product = f"{product}_contract"
    if _load_contract(contract_product):
        raise HTTPException(
            status_code=409,
            detail=f"Contract {contract_product!r} already exists. Edit it directly in the workbench.",
        )

    promoted["product"] = contract_product

    errors = validate_contract(promoted)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Promoted contract validation failed (Gate G1)", "errors": errors},
        )

    _save_contract(contract_product, promoted)
    _update_index(store, contract_product, promoted)
    return _contract_out(store, contract_product, promoted)
```

> **Design note**: The promoted contract gets product name `{product}_contract`
> to avoid collision with the gate. The user can rename it in the workbench.
> The original gate remains unchanged — "gleiche Regel, zwei Artefakte".

### A4. Proposal kind — `packages/dq_core/obs/miner.py` + API schemas

Add `kind` to `Proposal` dataclass to distinguish gate-proposals from
contract-clause-proposals:

```python
# In Proposal dataclass (line 19–29), add:
    kind: str = "internal_gate"  # internal_gate | consumer_contract
```

The miner should read `kind` from the contract/check when generating proposals.
Update `ProposalMiner.mine()` to set `kind` based on the source contract.

Update `services/api/schemas/proposal_schemas.py`:

```python
# ProposalOut — add after created_at:
    kind: str = "internal_gate"
```

Update frontend type `apps/cockpit/src/types/index.ts`:

```typescript
// Proposal interface (line 670) — add after status:
  kind: ArtifactKind;
```

---

## Part B — Frontend: Coverage Dimension Switcher

### B1. Types — `apps/cockpit/src/types/index.ts`

Add kind-awareness fields to `LineageNode`:

```typescript
// LineageNode (lines 445–460) — add after has_contract:
  has_internal_gate?: boolean;
  has_boundary_contract?: boolean;
```

### B2. i18n — `apps/cockpit/src/i18n/de.ts`

Add labels for the dimension switcher under the `lineage` section:

```typescript
// In lineage section, add:
  dimensionAll: 'Alle',
  dimensionInternal: 'Internal',
  dimensionContract: 'Contract',
  promoteCta: 'Promote to Contract',
  promoteHint: 'Kopiert die Gate-Garantien in einen neuen Contract-Entwurf.',
  noGateForPromotion: 'Kein Internal Gate vorhanden.',
  promotionSuccess: 'Contract-Entwurf erstellt.',
```

Add Govern onboarding strings:

```typescript
// In contracts section, add:
  onboardingTitle: 'Noch keine Contracts',
  onboardingDesc: 'Dein DQ-First-Setup läuft vollständig über Internal Gates. '
    + 'Sobald du bereit bist, kannst du einzelne Gates über „Promote to Contract" '
    + 'in die Governance überführen.',
  onboardingCta: 'Zur Coverage Map →',
```

### B3. Coverage Map — `apps/cockpit/src/pages/LineageMap.tsx`

**B3a. Add dimension state**

In the top-level `LineageMap` component (or the `ObjectLineageGraph` sub-
component), add state:

```typescript
type CoverageDimension = 'all' | 'internal' | 'contract';
const [dimension, setDimension] = useState<CoverageDimension>('all');
```

Pass `dimension` and `setDimension` to `ObjectLineageGraph`.

**B3b. Add SegmentControl to the filter bar**

Reuse the `SegmentControl` component created in Batch 2 (or import from a
shared location). Add it to the filter bar (after the coverage-flag select,
around line 549–560):

```tsx
<SegmentControl
  value={dimension}
  onChange={setDimension}
  options={[
    { key: 'all', label: t.lineage.dimensionAll },
    { key: 'internal', label: t.lineage.dimensionInternal },
    { key: 'contract', label: t.lineage.dimensionContract },
  ]}
/>
```

**B3c. Apply dimension filter in `applyFilters`**

Extend the `applyFilters` callback (lines 290–309) to hide nodes based on
dimension:

```typescript
// After the existing flagFilter block, add:
if (dimension === 'internal') {
  cy.nodes().filter(n =>
    !n.data('isLane') && !n.data('has_internal_gate')
  ).style('opacity', 0.15);
}
if (dimension === 'contract') {
  cy.nodes().filter(n =>
    !n.data('isLane') && !n.data('has_boundary_contract')
  ).style('opacity', 0.15);
}
```

> Use opacity dim (not `display: none`) so the graph layout stays stable.
> This matches the root-cause highlighting pattern already used (`.rc-dim`
> class sets `opacity: 0.18`).

**B3d. Pass new fields to Cytoscape node data**

In the Cytoscape element creation (lines 364–383), add the new fields:

```typescript
// After has_contract (line 379), add:
has_internal_gate: n.has_internal_gate ?? false,
has_boundary_contract: n.has_boundary_contract ?? false,
```

**B3e. Add dimension to applyFilters dependency array**

```typescript
// Line 309 — update dependency array:
}, [layerFilter, flagFilter, search, dimension]);
```

**B3f. Update CoverageKpis**

The `CoverageKpis` component (lines 111–151) shows counts from
`useCoverageSummary()`. With the new `with_internal_gate` and
`with_contract_checks` fields from Batch 2, add conditional display
based on the dimension:

```tsx
// In CoverageKpis, receive dimension as prop:
function CoverageKpis({ dimension }: { dimension: CoverageDimension }) {
  ...
  // Show relevant count based on dimension:
  {dimension !== 'contract' && (
    <span style={chip}>
      <span style={num}>{data.with_internal_gate}</span> Internal Gates
    </span>
  )}
  {dimension !== 'internal' && (
    <span style={chip}>
      <span style={num}>{data.with_contract_checks}</span> Contracts
    </span>
  )}
```

### B4. Object Side Panel — Promotion CTA

In the `ObjectSidePanel` component (lines 153–249), add a "Promote to
Contract" button when the node has an internal gate but no boundary contract:

```tsx
// After the existing buttons (line 246), add:
{node.has_internal_gate && !node.has_boundary_contract && canProfile && (
  <button
    onClick={() => navigate(`/contracts?promote=${encodeURIComponent(node.id)}`)}
    style={{
      background: 'var(--cont)', color: '#fff', border: 'none',
      borderRadius: 5, padding: '7px 14px', fontSize: 13, cursor: 'pointer',
    }}
  >
    {t.lineage.promoteCta}
  </button>
)}
```

> The `?promote=` query param is picked up by ContractWorkbench to trigger the
> promotion flow (see Part C).

---

## Part C — Frontend: Promotion Flow in Contract Workbench

### C1. ContractWorkbench — `apps/cockpit/src/pages/ContractWorkbench.tsx`

**C1a. Read the `promote` query parameter**

At the top of the component, extract the `promote` param:

```typescript
const [promoteProduct] = useSearchParamState('promote', '');
```

**C1b. Trigger promotion on mount**

When `promoteProduct` is set, call the promotion endpoint and open the newly
created contract:

```typescript
import { api } from '@/api/client';

useEffect(() => {
  if (!promoteProduct) return;
  const doPromote = async () => {
    try {
      const resp = await api.post(`/contracts/${promoteProduct}/promote`);
      toast.success(t.lineage.promotionSuccess);
      // Navigate to the promoted contract
      setSelectedProduct(resp.data.product);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Promotion fehlgeschlagen.');
    }
  };
  doPromote();
}, [promoteProduct]);
```

> The `promote` param is one-shot: once the contract is created, the URL is
> updated to `?product={promoted_product}` and the param clears.

### C2. API hook — `apps/cockpit/src/api/contracts.ts`

Add a `usePromoteContract` mutation hook:

```typescript
export function usePromoteContract() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (product: string) =>
      api.post(`/contracts/${product}/promote`).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
}
```

---

## Part D — Frontend: Govern-Block Onboarding

### D1. Contract Workbench empty state — `apps/cockpit/src/pages/ContractWorkbench.tsx`

When the contracts list is empty and the user has no `*_contract` kind
artifacts, show an onboarding panel instead of the empty list:

```tsx
// In the component, after fetching contracts:
const hasContracts = contracts.some(
  c => c.kind === 'consumer_contract' || c.kind === 'provider_contract'
);

// In the render, when contracts list is empty:
{contracts.length === 0 && (
  <div style={{
    background: 'var(--bg-1)', border: '1px dashed var(--line-2)',
    borderRadius: 10, padding: 32, textAlign: 'center', marginTop: 24,
  }}>
    <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--fg)', marginBottom: 8 }}>
      {t.contracts.onboardingTitle}
    </h2>
    <p style={{ fontSize: 13, color: 'var(--fg-3)', maxWidth: 480, margin: '0 auto 16' }}>
      {t.contracts.onboardingDesc}
    </p>
    <button
      onClick={() => navigate('/lineage')}
      style={{
        background: 'var(--cont)', color: '#fff', border: 'none',
        borderRadius: 5, padding: '8px 20px', fontSize: 13, cursor: 'pointer',
      }}
    >
      {t.contracts.onboardingCta}
    </button>
  </div>
)}
```

### D2. Compliance page empty state — `apps/cockpit/src/pages/Compliance.tsx`

When no active contracts exist, show an onboarding hint above the existing
panels:

```tsx
// After activeContracts computation:
{activeContracts.length === 0 && (
  <div style={{
    background: 'color-mix(in srgb, var(--cont) 8%, transparent)',
    border: '1px solid var(--cont)',
    borderRadius: 8, padding: '12px 16px', marginBottom: 16,
    fontSize: 12, color: 'var(--fg-2)',
  }}>
    Noch keine aktiven Contracts — Compliance-Daten erscheinen nach der ersten
    Contract-Aktivierung. Internal Gates laufen unabhängig unter <strong>Health</strong>.
  </div>
)}
```

### D3. Proposals page — kind-aware badges — `apps/cockpit/src/pages/Proposals.tsx`

Add a kind badge to each `ProposalCard` to distinguish gate proposals from
contract-clause proposals:

```tsx
// In ProposalCard, after the product label, add:
<span style={{
  fontSize: 9, borderRadius: 3, padding: '1px 5px', marginLeft: 4,
  background: proposal.kind === 'internal_gate'
    ? 'color-mix(in srgb, var(--qual) 14%, transparent)'
    : 'color-mix(in srgb, var(--cont) 14%, transparent)',
  color: proposal.kind === 'internal_gate' ? 'var(--qual)' : 'var(--cont)',
  border: `1px solid ${proposal.kind === 'internal_gate' ? 'var(--qual)' : 'var(--cont)'}`,
}}>
  {proposal.kind === 'internal_gate' ? 'Gate' : 'Contract'}
</span>
```

For contract-clause proposals, change the action buttons: instead of direct
"Accept", show a CTA that navigates to the Govern section:

```tsx
// In ProposalCard, wrap the accept button conditionally:
{proposal.kind !== 'internal_gate' ? (
  <button
    onClick={() => navigate(`/contracts?product=${proposal.product}`)}
    style={{ flex: 1, background: 'var(--cont)22', border: '1px solid var(--cont)', color: 'var(--cont)', borderRadius: 5, padding: '6px 0', fontSize: 12, cursor: 'pointer' }}
  >
    Im Contract prüfen →
  </button>
) : (
  <button onClick={() => act('accept')} ...existing accept button... />
)}
```

---

## Part E — Tests

### E1. Backend: lineage coverage test

```python
def test_get_coverage_annotates_kind():
    nodes = [{"id": "ds1"}, {"id": "ds2"}, {"id": "ds3"}]
    statuses = [
        {"dataset": "ds1", "status": "pass"},
        {"dataset": "ds2", "status": "pass"},
    ]
    contracted = ["ds1", "ds2"]

    result = get_coverage(
        nodes, statuses, contracted,
        gate_products={"ds1"},
        contract_products={"ds2"},
    )
    ds1 = next(n for n in result if n["id"] == "ds1")
    ds2 = next(n for n in result if n["id"] == "ds2")
    ds3 = next(n for n in result if n["id"] == "ds3")

    assert ds1["has_internal_gate"] is True
    assert ds1["has_boundary_contract"] is False
    assert ds2["has_internal_gate"] is False
    assert ds2["has_boundary_contract"] is True
    assert ds3["has_internal_gate"] is False
    assert ds3["coverage_flag"] == "▲"
```

### E2. Backend: promotion endpoint test

```python
def test_promote_creates_consumer_contract(client, seeded_gate):
    """POST /api/contracts/{product}/promote creates a consumer_contract."""
    resp = client.post(f"/api/contracts/{seeded_gate}/promote")
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "consumer_contract"
    assert data["product"] == f"{seeded_gate}_contract"
    assert data["lifecycle"] == "draft"


def test_promote_rejects_non_gate(client, seeded_contract):
    """Only internal_gate artifacts can be promoted."""
    resp = client.post(f"/api/contracts/{seeded_contract}/promote")
    assert resp.status_code == 409


def test_promote_rejects_duplicate(client, seeded_gate):
    """Promotion fails if target contract already exists."""
    client.post(f"/api/contracts/{seeded_gate}/promote")
    resp = client.post(f"/api/contracts/{seeded_gate}/promote")
    assert resp.status_code == 409
```

### E3. Frontend: existing tests unaffected

No changes to `role.test.ts`. Visual verification via acceptance criteria.

---

## Execution order

```
 A1  Lineage loader — kind-aware get_coverage()
 A2  Lineage router — pass gate/contract sets
 A3  Promotion endpoint
 A4  Proposal kind field
  ↓
 B1  Frontend types (LineageNode fields)
 B2  i18n (dimension labels, promotion strings, onboarding)
 B3  Coverage Map dimension switcher
 B4  Object Side Panel promotion CTA
  ↓
 C1  ContractWorkbench promotion trigger
 C2  API hook (usePromoteContract)
  ↓
 D1  Contract Workbench onboarding state
 D2  Compliance onboarding state
 D3  Proposals kind badges
  ↓
 E1–E2  Tests
```

---

## Acceptance criteria

| # | Criterion | How to verify |
|---|-----------|---------------|
| A1 | `/api/lineage` response nodes include `has_internal_gate` and `has_boundary_contract` | curl / httpie |
| A2 | `POST /api/contracts/{product}/promote` creates a `consumer_contract` draft | curl / API test |
| A3 | Promotion of a non-gate returns 409 | API test |
| A4 | Promotion of same gate twice returns 409 (duplicate) | API test |
| B1 | Coverage Map shows SegmentControl: "Alle \| Internal \| Contract" | Visual |
| B2 | Clicking "Internal" dims nodes without internal gates | Visual |
| B3 | Clicking "Contract" dims nodes without boundary contracts | Visual |
| B4 | Clicking "Alle" restores all nodes to full opacity | Visual |
| B5 | CoverageKpis show gate/contract counts based on dimension | Visual |
| B6 | Side panel shows "Promote to Contract" when node has gate but no contract | Visual: click a gate-only node |
| B7 | Clicking "Promote to Contract" navigates to workbench with promote param | Visual |
| C1 | Promotion from workbench creates contract and opens editor | Visual: navigate via promote CTA |
| C2 | Toast confirms promotion success | Visual |
| D1 | Contracts page shows onboarding panel when no contracts exist | Visual: ensure no contracts |
| D2 | Compliance page shows hint when no active contracts | Visual |
| D3 | Proposal cards show "Gate" or "Contract" badge | Visual: open Proposals page |
| D4 | Contract-clause proposals show "Im Contract prüfen →" instead of "Accept" | Visual |
| E1 | All Python tests pass (`pytest`) | CLI |
| E2 | All frontend tests pass (`npm run test`) | CLI |
| E3 | No TypeScript errors (`tsc --noEmit`) | CLI |

---

## Out of scope (later batches)

- My Work kind-awareness (gate vs contract grouping in work list)
- Dual-Run awareness in Runs page (two runs per dual-role dataset)
- Compliance-Ampel (traffic-light per contract, needs state machine)
- Contract-SLA-Breach list expansion (needs backend aggregation per kind)
- Coverage-Map: node border color differentiation by kind
- Promotion: renaming promoted contract product (currently hardcoded suffix)
- Promotion: partial promotion (select which guarantees to copy)
