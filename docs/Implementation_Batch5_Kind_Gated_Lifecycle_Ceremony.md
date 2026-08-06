# Batch 5 — Kind-Gated Lifecycle Ceremony (Breaking-Diff & SemVer for Contracts Only)

> **Goal**: Honour ADR-0001 §3 — `internal_gate` is **"frei änderbar,
> zeremonielos"**; only `*_contract` carries **SemVer, Approval, Breaking-Schutz
> (Gate G3)**. Today the breaking-change guard and the major-bump requirement
> fire for *every* artifact regardless of `kind`, so tightening an internal gate
> wrongly demands a major version bump and full approval ceremony. Batch 5 gates
> the lifecycle ceremony on `kind`. This is **O1 / ADR §9 OP-4 step 3**
> ("Breaking-Diff auf kind gegated — nur Contracts").
>
> **Depends on**: Batch 1–4 merged (`kind` discriminator; compliance/incident
> split; `_contract_kind_map()` helper from Batch 4 A1; ODCS export guard from
> Batch 4 C3).

---

## Pre-conditions

- `kind ∈ {internal_gate, consumer_contract, provider_contract}` validated
  (`packages/dq_core/contract/validator.py:23`).
- Breaking-diff engine exists and classifies the level-1 breaking set
  (`packages/dq_core/contract/diff.py` — `diff_contracts:24`, `is_breaking:35`):
  `removed_column · key_change · constraint_tightened · removed_referential ·
  severity_escalated`.
- Batch 4 gated the **run-thread** compliance path on `kind`; Batch 5 closes the
  remaining kind-blind hole in the **authoring/approval** path.
- All existing tests pass (`pytest` + `npm run test`).

---

## Background — where ceremony is enforced kind-blind today

The G3 breaking guard lives entirely in the **router layer** (not in
`git_repo.py:write_contract` — that just commits). Two enforcement points, both
kind-blind:

```python
# 1) Full-mode approve — services/api/routers/contracts.py:469-486
if snapshot_path.exists():
    prior = yaml.safe_load(...)
    entries = diff_contracts(prior, data)
    if is_breaking(entries) and _semver_major(data["version"]) <= _semver_major(prior["version"]):
        raise HTTPException(409, "Breaking change requires a major version bump (Gate G3).")

# 2) Lite certify — contracts.py:673-686 (same guard, different message)
```

Plus `approve_contract` seeds a compliance row for **any** approved artifact
(`contracts.py:511-512`) — which, after Batch 4, an `internal_gate` should never
have:

```python
# contracts.py:510-512
if not store.get_compliance(product):
    store.set_compliance(product, str(data.get("version", "")), "unknown", "")
```

ADR-0001 §3 lifecycle table:

| Dimension | `internal_gate` | `*_contract` |
|---|---|---|
| Lifecycle | frei änderbar, **zeremonielos** | SemVer, Approval, Breaking-Schutz (G3) |

So: an internal gate should activate/change **without** a major-bump demand,
**without** seeding a governance compliance row, and the FE should not impose
breaking-diff friction on it.

---

## Part A — Backend: Gate the Lifecycle Ceremony on `kind`

`diff_contracts()` stays **pure** (it classifies changes; it should not know
about kind). The gating happens at the two router call sites, which already have
the loaded `data` dict in hand — read `data.get("kind", "internal_gate")`
directly (no new helper needed in these functions).

### A1. Full-mode approve — `services/api/routers/contracts.py:434-526`

```python
kind = data.get("kind", "internal_gate")
is_contract = kind in ("consumer_contract", "provider_contract")

# G3 — breaking guard applies ONLY to contracts (ADR §3: gates are ceremony-free).
snapshot_path = _active_snapshot_path(product)
if is_contract and snapshot_path.exists():
    prior = yaml.safe_load(snapshot_path.read_text(encoding="utf-8")) or {}
    entries = diff_contracts(prior, data)
    if is_breaking(entries) and _semver_major(data.get("version", "0")) <= _semver_major(prior.get("version", "0")):
        raise HTTPException(status_code=409, detail={...})   # unchanged body

data["lifecycle"] = "active"
_save_contract(product, data)
snapshot_path.write_text(...)
_update_index(store, product, data)
# ... git commit (unchanged) ...

# Compliance seed ONLY for contracts (Batch 4: gates have no governance ampel).
if is_contract and not store.get_compliance(product):
    store.set_compliance(product, str(data.get("version", "")), "unknown", "")
```

> **Note**: gates may still be "approved" to `lifecycle: active` (the lifecycle
> field is orthogonal to kind), but the activation is ceremony-light — no
> breaking guard, no compliance seed. The conventional path for a gate is the
> Lite one-step certify (A2); full approve is left functional for gates that
> happen to use it.

### A2. Lite one-step certify — `contracts.py:644-687`

Same gating — the breaking guard at `:673-686` becomes contract-only:

```python
kind = data.get("kind", "internal_gate")
is_contract = kind in ("consumer_contract", "provider_contract")
prior_path = _active_snapshot_path(product)
if is_contract and prior_path.exists():
    prior = yaml.safe_load(...)
    entries = diff_contracts(prior, data)
    if is_breaking(entries) and _semver_major(...) <= _semver_major(...):
        raise HTTPException(409, "Breaking change on a certified contract — use the full-mode approval flow (Gate G3).")
```

> A breaking change to an **active internal gate** now certifies in one step
> (the whole point: tightening a gate is an engineering decision, not a
> governance event). A breaking change to an **active contract** still routes to
> the full-mode flow with the major-bump demand — unchanged.

---

## Part B — Backend: Diff Endpoints Surface `kind` + `ceremony_required`

So the FE can explain *why* a change is or isn't blocked. Both diff endpoints
already load the contract.

### B1. `POST /{product}/diff` — `contracts.py:290-310`

```python
kind = (current or {}).get("kind", "internal_gate")
ceremony_required = kind in ("consumer_contract", "provider_contract")
return {
    "kind": kind,
    "ceremony_required": ceremony_required,
    "breaking": is_breaking(entries),
    "blocking": ceremony_required and is_breaking(entries),   # what actually gates approve
    "entries": [...],
}
```

### B2. `GET /{product}/diff/active` — `contracts.py:316-348`

Add the same `kind` / `ceremony_required` / `blocking` fields to the response so
the BreakingDiffPanel (UX-N13 version-diff) reflects ceremony state.

---

## Part C — Backend: CI G3-on-PRs Kind-Aware

`PLAN_Remediation_v2.md` R0-7 defines a CI job that runs `dq_core.contract.diff`
against the merge-base and fails on breaking-without-major. Make it skip
`internal_gate` files so gate edits never block a PR.

- The CI script (`.github/workflows/*` / `scripts/` G3 step): for each changed
  `contracts/*.y*ml`, read `kind`; only run the breaking-fail check when
  `kind ∈ {consumer_contract, provider_contract}`.
- Expose a reusable CLI shim — `python -m dq_core.contract.gate_g3 <base> <head>`
  — that loads both sides, reads `kind` from `head`, and exits non-zero only for
  a breaking contract change without a major bump. Keeps the gate logic in one
  place (router + CI share intent).

---

## Part D — Backend: O1 / Stufe-2 — datacontract-CLI Second Opinion (contract-only, advisory)

`PLAN_Remediation_v2.md` R5-2: an **optional advisory** CI job that runs
`datacontract breaking <base-export> <head-export>` over the **ODCS export** and
reports discrepancies vs the homegrown `diff.py`. Because ODCS export already
rejects `internal_gate` (Batch 4 C3), this is inherently contract-only — no extra
gating needed.

- Advisory (non-blocking, like the existing G4 openapi-drift gate at commit
  `24f41cd`): a divergence between `diff.py` and the CLI is surfaced as a PR
  annotation, not a failure.
- Only runs for PRs that change a `*_contract` (skip when the changed artifact's
  `kind == internal_gate`, since there is no ODCS export to diff).

> **Explicitly NOT in scope — type-narrowing** (L-3): `diff.py`'s header notes
> type-narrowing waits until the schema guarantee carries column *types* (v1
> only carries names). That is a schema-v2 workstream, deferred.

---

## Part E — Frontend: ContractWorkbench Ceremony by Kind

### E1. Types — `apps/cockpit/src/types/index.ts`

```typescript
// DiffResult (the /diff + /diff/active response type) — add:
  kind?: ArtifactKind;
  ceremony_required?: boolean;
  blocking?: boolean;
```

### E2. i18n — `apps/cockpit/src/i18n/de.ts`

```typescript
// contracts / workbench section — add:
  gateNoCeremony: 'Internes Gate — frei änderbar, kein Approval nötig.',
  gateChangeHint: 'Änderungen an Gates wirken sofort; SemVer/Breaking-Schutz '
    + 'gelten erst nach „Promote to Contract".',
  breakingBlocked: 'Breaking Change — Major-Version-Bump erforderlich.',
  breakingInfoGate: 'Diese Änderung wäre an einem Contract breaking, an einem '
    + 'Gate ist sie folgenlos.',
```

### E3. BreakingDiffPanel + ApprovalBar — `apps/cockpit/src/pages/ContractWorkbench.tsx`

The workbench (R3-3) calls `POST /diff` before enabling Approve (friction ∝
risk). Make that friction kind-proportional:

- **`internal_gate`**: render the diff for transparency, but show
  `t.contracts.gateNoCeremony`; the Approve/Certify button is **never blocked**
  by `breaking`, and the major-bump banner is hidden. Breaking entries are shown
  as informational (`t.contracts.breakingInfoGate`), not as a gate.
- **`*_contract`**: unchanged — `blocking === true` disables Approve and shows
  `t.contracts.breakingBlocked` with the required-major-bump hint.

The Promote-to-Contract action (Batch 3) is the explicit moment a gate crosses
into the ceremony world — after promotion, the full breaking-diff friction
applies to the new `consumer_contract` draft.

---

## Part F — Tests

### F1. Backend — kind-gated ceremony (`tests/api/test_contract_lifecycle.py`)

```python
def test_internal_gate_breaking_change_certifies_without_major_bump(client, seeded_active_gate):
    """Tightening an active internal_gate (e.g. raise completeness min_pct) with
    NO major bump → certify/approve succeeds (ceremony-free, ADR §3)."""
    # mutate gate to a 'breaking' guarantee, keep version minor-bumped
    resp = client.post(f"/api/contracts/{seeded_active_gate}/certify", json=tightened_gate)
    assert resp.status_code == 200
    assert resp.json()["lifecycle"] == "active"

def test_contract_breaking_change_still_requires_major_bump(client, seeded_active_contract):
    resp = client.post(f"/api/contracts/{seeded_active_contract}/approve")  # breaking, no major
    assert resp.status_code == 409
    assert "major version bump" in resp.json()["detail"]["message"]

def test_approve_internal_gate_seeds_no_compliance(client, seeded_gate_draft):
    client.post(f"/api/contracts/{seeded_gate_draft}/approve")
    assert store.get_compliance(seeded_gate_draft) is None

def test_approve_contract_seeds_unknown_compliance(client, seeded_contract_draft):
    client.post(f"/api/contracts/{seeded_contract_draft}/approve")
    assert store.get_compliance(seeded_contract_draft)["compliance"] == "unknown"

def test_diff_reports_ceremony_required(client, seeded_gate, seeded_contract):
    assert client.post(f"/api/contracts/{seeded_gate}/diff", json=...).json()["ceremony_required"] is False
    assert client.post(f"/api/contracts/{seeded_contract}/diff", json=...).json()["ceremony_required"] is True
```

### F2. Unit — gate_g3 CLI shim (`tests/unit/test_gate_g3.py`)

Breaking contract change w/o major → exit 1; identical change on a gate → exit 0;
non-breaking contract change → exit 0.

### F3. Frontend

`role.test.ts` unaffected; `tsc --noEmit` clean (new fields optional). Visual
verification per acceptance criteria.

---

## Execution order

```
 A1  approve: G3 guard + compliance seed contract-only
 A2  Lite certify: G3 guard contract-only
  ↓
 B1  /diff returns kind + ceremony_required + blocking
 B2  /diff/active returns same
  ↓
 C   CI G3-on-PRs skips internal_gate (+ gate_g3 CLI shim)
 D   datacontract-CLI advisory job (contract-only, non-blocking)
  ↓
 E1  DiffResult type fields
 E2  i18n
 E3  BreakingDiffPanel/ApprovalBar: ceremony proportional to kind
  ↓
 F1–F3  Tests
```

---

## Acceptance criteria

| # | Criterion | How to verify |
|---|-----------|---------------|
| A1 | Breaking change to an **active internal_gate** with no major bump → certify/approve **200** | API test |
| A2 | Breaking change to an **active contract** with no major bump → **409** (unchanged) | API test |
| A3 | Approving an **internal_gate** seeds **no** `dq_compliance` row | API test / inspect store |
| A4 | Approving a **contract** still seeds `compliance: unknown` | API test |
| B1 | `POST /diff` returns `kind`, `ceremony_required`, `blocking` | curl |
| B2 | `GET /diff/active` returns the same fields | curl |
| C1 | CI G3 job fails on a breaking **contract** PR w/o major bump | CI dry-run |
| C2 | CI G3 job passes a breaking **internal_gate** PR | CI dry-run |
| D1 | datacontract-CLI job is advisory (non-blocking) and skips gate-only PRs | CI dry-run |
| E1 | Workbench shows "Gate — frei änderbar" and never blocks Approve for a gate | Visual |
| E2 | Workbench still blocks Approve + shows major-bump hint for a breaking contract | Visual |
| F1 | All Python tests pass (`pytest`) | CLI |
| F2 | `npm run test` green; `tsc --noEmit` clean | CLI |

---

## Out of scope (later batches)

- **Type-narrowing in `diff.py`** (L-3): needs the schema guarantee to carry
  column *types* (schema v2). The level-1 breaking set stays as-is.
- **Counterparty + `depends_on` chains** (ADR §10): transitive breaking-change
  visibility upstream, pinned-version enforcement at consumer inbound points.
- **Garantie-level `kind` override** (ADR §9 OP-2 phase 2): mixed gate+contract
  guarantees in one dataset → per-guarantee ceremony.
- **Deprecation impact analysis**: warning when deprecating a contract that a
  downstream consumer pins (depends on §10 chains).
- **Auto major-bump suggestion**: when the FE detects a breaking contract edit,
  pre-fill the next major version (UX nicety, not correctness).
