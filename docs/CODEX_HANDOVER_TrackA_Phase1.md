# Codex Handover — Track A Phase 1: Data Product Aggregate

**Date:** 2026-06-23  
**Status:** **implemented** (historisch; Phase 1 geliefert als `packages/dq_core/product/` + `routers/products.py` + `/products`-Seiten — Phase-2-Punkte in `OPEN_TASKS.md` **P**)  
**Source docs:** `ADR-0004_DataProduct-als-Komposition.md` · `PLAN_ADR-0003-0004_Implementation.md` · `CONTEXT.md`  
**Constraint:** Engine/Compiler/Store untouched (`[ENGINE-FROZEN]`). Additive, read-side only. No migrations.

---

## 0 — What this builds

A new `packages/dq_core/product/` package and a `services/api/routers/products.py` router that expose the **Data Product as a read-side aggregate** over the existing lineage graph. The Cockpit gets a Products page and a `LineageMiniGraph` component.

Build order (each step is a mergeable unit):

```
model.py → walk.py → reconcile.py → health.py → /api/products → Products page → LineageMiniGraph
```

---

## 1 — `packages/dq_core/product/model.py`

### Dataclass

```python
@dataclass
class OutputPort:
    dataset: str          # technicalName of the object

@dataclass
class InboundDep:
    product: str          # manifest product name of upstream
    version: str          # pinned SemVer string

@dataclass
class Product:
    product: str          # identifier, matches ^[A-Za-z_]\w*$
    owners: list[str]     # owner hull — non-empty
    output_ports: list[OutputPort]
    inbound: list[InboundDep]
```

No `lifecycle`, no `version`, no `interior` — all derived, never in the manifest.

### Loader

- New setting `products_dir` (default `"products"`) in `services/api/settings.py`.
- `load_manifest(path) -> Product` — **lenient/structure-only**: validates only that `product` matches `^[A-Za-z_]\w*$`, `owners` is non-empty, each port has `dataset`, each inbound has `product` + `version`. Referential gaps (port without contract, object absent from lineage) are **not** load errors — they become Findings in reconcile.
- `load_all_manifests(products_dir) -> list[Product]` — skips files that fail structural validation with a logged warning; never raises.

---

## 2 — `packages/dq_core/product/walk.py`

### Inputs

```python
def walk_all(
    manifests: list[Product],
    upstream: dict[str, list[str]],    # node_id → list of upstream node_ids
    downstream: dict[str, list[str]],  # node_id → list of downstream node_ids
    node_data: dict[str, dict],        # node_id → full lineage node record (layer, role, etc.)
    is_external: Callable[[str], bool],
) -> list[ProductAggregate]:
```

`upstream` and `downstream` come from `build_lineage_graph` edges (source→target). Build both maps before calling:

```python
upstream = defaultdict(list)
downstream = defaultdict(list)
for edge in lineage_graph["edges"]:
    downstream[edge["source"]].append(edge["target"])
    upstream[edge["target"]].append(edge["source"])
```

### Port index

Build **before** walking any product:

```python
port_index: dict[str, list[str]] = defaultdict(list)   # dataset → [product_name, ...]
for m in manifests:
    for p in m.output_ports:
        port_index[p.dataset].append(m.product)
```

Datasets with `len(port_index[d]) > 1` are **Contested-Ports** — collected here, emitted as findings in `reconcile.py`, and **excluded from the walk's stop logic** (treated as unresolved boundary → walk traverses through them as interior, conservative fallback).

```python
clean_port_index: dict[str, str] = {
    d: owners[0]
    for d, owners in port_index.items()
    if len(owners) == 1
}
```

### Walk per product

```python
@dataclass
class ProductAggregate:
    product: Product
    interior: set[str]           # node ids
    inbound_sources: list[str]   # external node ids
    resolved_inbound_deps: list[str]  # other-product port node ids (Fall B)
    subgraph_nodes: list[dict]   # full node_data records for interior + ports
    subgraph_edges: list[dict]   # edges connecting those nodes
```

Algorithm:

```python
for m in sorted(manifests, key=lambda m: m.product):   # deterministic order
    interior = set()
    inbound_sources = []
    resolved_inbound_deps = []
    subgraph_nodes = {}   # node_id → node_data record
    subgraph_edges = []

    visited = set()
    queue = [p.dataset for p in m.output_ports]

    # Seed subgraph with port nodes
    for port in m.output_ports:
        if port.dataset in node_data:
            subgraph_nodes[port.dataset] = node_data[port.dataset]

    while queue:
        n = queue.pop()
        if n in visited:
            continue
        visited.add(n)

        for up in sorted(upstream.get(n, [])):
            # STOP CONDITION: any declared port (own or foreign)
            if up in clean_port_index:
                owner = clean_port_index[up]
                if owner != m.product:
                    # Fall A or B
                    manifest_owner = next(x for x in manifests if x.product == owner)
                    if set(manifest_owner.owners) == set(m.owners):
                        pass   # Fall A — internal hand-off, no record needed
                    else:
                        resolved_inbound_deps.append(up)   # Fall B
                # Own port OR foreign port → STOP regardless
                if up in node_data:
                    subgraph_nodes[up] = node_data[up]
                subgraph_edges.append({"source": up, "target": n})
                continue

            elif is_external(up):
                inbound_sources.append(up)
                subgraph_edges.append({"source": up, "target": n})
                continue

            else:
                interior.add(up)
                if up in node_data:
                    subgraph_nodes[up] = node_data[up]
                subgraph_edges.append({"source": up, "target": n})
                queue.append(up)
```

`is_external(node_id)`: `True` when the node's `sourceScope == "external_system"` or id matches `ext` / `S4:*` patterns (same logic as existing `inventory.py`).

---

## 3 — `packages/dq_core/product/reconcile.py`

### Inputs

```python
def reconcile(
    aggregates: list[ProductAggregate],
    port_index: dict[str, list[str]],         # full (including contested)
    downstream: dict[str, list[str]],
    all_manifests: list[Product],
    contracts: dict[str, Any],                # dataset → Contract (loaded by caller)
    lineage_node_ids: set[str],               # all node ids in the lineage graph
) -> list[Finding]:
```

### Finding type

```python
@dataclass
class Finding:
    finding_type: Literal[
        "dangling_port",
        "contested",          # scope discriminator below
        "boundary_leak",
    ]
    scope: Literal["port", "interior"] | None   # for "contested" only
    product: str
    object_id: str
    detail: str
```

### Three findings in v1

**1 — Dangling-Port**

For each `output_port` of each manifest:
- No contract file for `port.dataset` **or** contract has `kind == "internal_gate"`: emit `dangling_port`
- No lineage node for `port.dataset`: emit `dangling_port`

```python
for agg in aggregates:
    for port in agg.product.output_ports:
        contract = contracts.get(port.dataset)
        no_contract = contract is None or contract.kind == "internal_gate"
        no_node = port.dataset not in lineage_node_ids
        if no_contract or no_node:
            findings.append(Finding("dangling_port", None, agg.product.product, port.dataset, ...))
```

**2 — Contested (port or interior)**

```python
# Contested-Port (from port_index built in walk.py)
for dataset, claimants in port_index.items():
    if len(claimants) > 1:
        for claimant in claimants:
            findings.append(Finding("contested", "port", claimant, dataset, ...))

# Contested-Interior: object in interior of ≥2 products
interior_membership: dict[str, list[str]] = defaultdict(list)  # node_id → [product_names]
for agg in aggregates:
    for node_id in agg.interior:
        interior_membership[node_id].append(agg.product.product)

for node_id, products in interior_membership.items():
    if len(products) > 1:
        for p in products:
            findings.append(Finding("contested", "interior", p, node_id, ...))
```

**3 — Boundary-Leak (cross-owner only, v1)**

```python
# Build owner map: product_name → owner_set
owner_map = {m.product: set(m.owners) for m in all_manifests}

for agg in aggregates:
    p_owners = set(agg.product.owners)
    for node_id in agg.interior:
        for downstream_node in downstream.get(node_id, []):
            # Is downstream_node owned by a different owner set?
            claimants = port_index.get(downstream_node, [])
            for claimant_product in claimants:
                if owner_map.get(claimant_product, set()) != p_owners:
                    if node_id not in {p.dataset for p in agg.product.output_ports}:
                        findings.append(Finding("boundary_leak", None, agg.product.product, node_id, ...))
```

> **Log explicitly** that estate-leaving leaks (consumers outside the inventory) are NOT detected in v1.

---

## 4 — `packages/dq_core/product/health.py`

### Signatures

```python
def own_health(
    agg: ProductAggregate,
    contracts: dict[str, Any],    # dataset → Contract
    store: BaseStore,
) -> str:   # OverallStatus: pass|fail|warn|critical|unknown

def upstream_risk(
    agg: ProductAggregate,
    all_manifests: list[Product],
    contracts: dict[str, Any],
    store: BaseStore,
) -> list[UpstreamRiskEntry]:
```

### `own_health`

```python
governance_statuses = []
for port in agg.product.output_ports:
    contract = contracts.get(port.dataset)
    if contract is None:
        continue
    if contract.kind not in ("consumer_contract", "provider_contract"):
        continue
    if contract.lifecycle != "active":       # only active ports count
        continue
    compliance = store.get_compliance(port.dataset)
    if compliance:
        governance_statuses.append(compliance["compliance"])

if not governance_statuses:
    return "unknown"
return worst_of(governance_statuses)   # critical > fail > warn > pass > unknown
```

**Key rules:**
- `internal_gate` ports: excluded (already Dangling-Port findings)
- `deprecated` / `draft` ports: excluded
- Empty governance set → `"unknown"` (not a failure — findings carry the nuance)

### `upstream_risk`

```python
@dataclass
class UpstreamRiskEntry:
    product: str
    pinned_version: str
    current_version: str | None
    compliance: str | None      # from store, per worst port of upstream product
    upstream_breach: bool
    version_drift: bool

for dep in agg.product.inbound:
    upstream_manifest = find_manifest(all_manifests, dep.product)
    if not upstream_manifest:
        continue

    # Walk upstream product's ports at query time (no store key by product name)
    worst_compliance = None
    worst_version = None
    for port in upstream_manifest.output_ports:
        rec = store.get_compliance(port.dataset)
        if rec:
            if worst_compliance is None or compliance_rank(rec["compliance"]) > compliance_rank(worst_compliance):
                worst_compliance = rec["compliance"]
                worst_version = rec["contract_version"]

    entries.append(UpstreamRiskEntry(
        product=dep.product,
        pinned_version=dep.version,
        current_version=worst_version,
        compliance=worst_compliance,
        upstream_breach=(worst_compliance == "breached"),
        version_drift=(worst_version is not None and worst_version != dep.version),
    ))
```

**Non-contagious:** `upstream_risk` entries never affect `own_health`. Separate fields in API response.

---

## 5 — `services/api/routers/products.py`

### Endpoints

- `GET /api/products` — list
- `GET /api/products/{product}` — detail

### List item shape

```json
{
  "product": "sales_overview",
  "owners": ["team-sales"],
  "port_count": 2,
  "own_health": "pass",
  "upstream_risk_count": 1,
  "finding_count": 0,
  "lifecycle": "active"
}
```

`lifecycle` derived per ADR-0004 §8:
- ≥1 active governance port → `"active"`
- all governance ports deprecated → `"deprecated"`
- only draft ports (or none) → `"draft"`

### Detail shape

```json
{
  "product": "sales_overview",
  "owners": ["team-sales"],
  "lifecycle": "active",
  "own_health": "pass",

  "ports": [
    {
      "dataset": "DS_REVENUE_SUMMARY",
      "kind": "provider_contract",
      "lifecycle": "active",
      "compliance": "compliant",
      "version": "1.3.0"
    }
  ],

  "interior": [
    {
      "id": "CORE_ORDERS",
      "layer": "transformation",
      "role": "core",
      "coverage_flag": "covered"
    }
  ],

  "inbound_dependencies": [
    {
      "product": "kunde",
      "pinned_version": "1.2.0",
      "current_version": "1.2.1",
      "compliance": "compliant",
      "upstream_breach": false,
      "version_drift": true
    }
  ],

  "inbound_sources": ["S4:ORDERS_RAW"],

  "upstream_risk": [...],   // same as inbound_dependencies entries

  "findings": [
    {
      "finding_type": "dangling_port",
      "scope": null,
      "object_id": "DS_ORDERS_FACT",
      "detail": "no governance contract"
    }
  ],

  "subgraph": {
    "nodes": [...],   // LineageNode shape from types/index.ts — layer, role, coverage_flag, kind, etc.
    "edges": [...]    // LineageEdge shape — id, source, target
  }
}
```

**No `boundary_view` field anywhere.** Topology is encoded by sub-array position. `subgraph.nodes[]` carry rendering metadata via existing lineage fields.

### Schemas file

`services/api/schemas/product_schemas.py` — Pydantic models for all shapes above.

### Router wiring

```python
# services/api/main.py
from .routers import products
app.include_router(products.router, prefix="/api")
```

---

## 6 — Cockpit: Products page + LineageMiniGraph

### New files

- `apps/cockpit/src/pages/Products.tsx` — list view
- `apps/cockpit/src/pages/ProductDetail.tsx` — detail view
- `apps/cockpit/src/components/LineageMiniGraph.tsx` — read-only graph
- `apps/cockpit/src/api/products.ts` — React Query hooks

### Route additions (`App.tsx`)

```tsx
<Route path="/products" element={<Products />} />
<Route path="/products/:name" element={<ProductDetail />} />
```

### API hooks (`api/products.ts`)

```ts
export const useProducts = () =>
  useQuery({ queryKey: ['products'], queryFn: () => api.get('/products').then(r => r.data) });

export const useProduct = (name: string) =>
  useQuery({ queryKey: ['products', name], queryFn: () => api.get(`/products/${name}`).then(r => r.data), enabled: !!name });
```

### Products list page

Reuse existing primitives: `StatusPill` (own_health), `CovFlag`, `OwnershipTag`, sortable table. Columns: Product name | Owners | Health | Ports | Findings | Lifecycle.

### ProductDetail page

Sections:
1. **Header** — product name, owners, lifecycle, `own_health` pill
2. **Upstream Risk** — only shown if `upstream_risk.length > 0`; non-contagious badge, list of entries with version_drift / upstream_breach indicators
3. **Findings** — grouped by `finding_type`; empty state = no findings
4. **Ports** — table of `ports[]` with kind, compliance, version
5. **Interior** — table of `interior[]` with layer, role, coverage_flag
6. **Lineage** — `<LineageMiniGraph subgraph={data.subgraph} />`

### `LineageMiniGraph` component

```tsx
interface LineageMiniGraphProps {
  subgraph: LineageGraph;   // existing type from types/index.ts
}
```

- Cytoscape + dagre layout (LR direction), extracted from `LineageMap.tsx` — **LineageMap stays untouched**
- Fit-to-view on mount
- Node colour by `role` / `coverage_flag` (same colour logic as LineageMap)
- Click-through to `/objects/:id`
- Read-only: no selection persistence, no lane filter, no focus-path UI

**Excluded in v1:** positions persistence, lane filter, transitive upstream chain, workbench embed, Contested-Interieur overlay.

---

## 7 — Tests

### Python unit tests (`tests/test_product_*.py`)

All tests use fixtures: hand-crafted manifests + synthetic lineage graph dicts. No real DB.

| File | Cases |
|---|---|
| `test_product_walk.py` | Fall A (same owner), Fall B (different owner), multi-claim → Contested-Interior, diamond graph, cycle safety, determinism (same input → same output), own-port stop (port of P stops walk), Contested-Port exclusion from port_index |
| `test_product_reconcile.py` | Dangling-Port (no contract), Dangling-Port (internal_gate), Dangling-Port (no lineage node), Contested-Interior, Contested-Port, cross-owner Boundary-Leak, no-leak when port declared |
| `test_product_health.py` | worst-of pass/fail/critical, active-only filter (deprecated port excluded), all-unknown returns "unknown", upstream_risk worst-of ports, upstream_breach flag, version_drift flag, non-contagion (upstream breach doesn't change own_health) |

### API smoke tests

`tests/test_api_products.py` — list returns array, detail returns full shape, unknown product returns 404.

### Frontend component tests

- `LineageMiniGraph.test.tsx` — renders without crash given a minimal `LineageGraph`
- `Products.test.tsx` — list renders product names and health pills
- `ProductDetail.test.tsx` — findings section hidden when empty, upstream risk section hidden when empty

---

## 8 — What NOT to touch

| Area | Rule |
|---|---|
| `packages/dq_core/engine/` | `[ENGINE-FROZEN]` — no changes |
| `packages/dq_core/compiler/` | no changes |
| `packages/dq_core/store/sqlite_store.py` | no new tables, no schema changes |
| `packages/dq_core/contract/model.py` | no changes — `boundary` is still never persisted |
| `apps/cockpit/src/pages/LineageMap.tsx` | untouched — LineageMiniGraph is a new component |
| Existing `/api/lineage` endpoint | untouched |
| `contracts/*.yaml` files | untouched |

The `products_dir` setting is the only new config key.

---

## 9 — Decision log (grilling 2026-06-23)

| # | Decision |
|---|---|
| G1 | `upstream_risk` uses Option A: walks upstream manifest's `output_ports` at query time, calls `store.get_compliance(port.dataset)` for each, takes worst-of. No store key change. |
| G2 | `own_health` over empty governance set → `"unknown"`. Filter to `lifecycle == "active"` ports only. Deprecated ports excluded. |
| G3 | Product detail endpoint includes `subgraph: {nodes, edges}` (LineageGraph shape). Walk accumulates edges. LineageMiniGraph takes a LineageGraph prop. No separate `/api/lineage` call from frontend. |
| G4 | `reconcile` receives full `downstream` map alongside `port_index`. Boundary-Leak detection is a separate pass in `reconcile.py`, not folded into `walk.py`. |
| G5 | `boundary_view` field dropped entirely from API response. No per-object boundary field. Topology encoded by sub-array position (`ports[]`, `interior[]`, etc.). |
| G6 | Contested-Port is a v1 finding. Folded into Contested type with `scope: "port" \| "interior"`. Contested-Port datasets excluded from `clean_port_index`; walk traverses through them as interior (conservative). |
| G7 | Walk stop condition: `up in port_index` (any declared port, own or foreign). Drop `!= P` guard. Same-product ports → stop, not interior, not recorded as inbound dep. |
