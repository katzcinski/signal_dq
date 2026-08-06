# Handover — Iteration 1: Full check library in the internal DQ-Checks frame

**Status:** **implemented** (historisch; Compiler-`checks:`-Pfad, `contracts.py`-Persistenz, `GateCheck`-Typ, Library v6 — siehe `OPEN_TASKS.md` „Bereits geschlossen") · **Branch:** `claude/check-library-classification` · **PR:** [#32](https://github.com/katzcinski/signal/pull/32) · **Baseline commit:** `3bd41d5`

This document hands off **Iteration 1** of the "internal checks" design. It is self-contained: an implementer should be able to start from here without the originating conversation.

---

## 1. Problem & baseline

The Checks Workbench editor only authors the **7 declarative guarantee families** (`schema, keys, referential, freshness, volume, completeness, not_null`), which the compiler maps to ~8 library templates. But `packages/dq_core/library/check_library.json` holds **~20 checks**. The remainder — `value_range, allowed_values, pattern_match, string_length, invalid, cross_field_consistency, aggregate_range, duplicate_approx, type_conformance, volume_anomaly, sap_replication_lag, custom_sql` — have **no GUI authoring path**; today they're only reachable via hand-edited `checks/<dataset>/checks.yml` (preserved by the compiler's "existing-wins" merge).

That gap is felt in the **internal DQ-Checks** frame (added in PR #32), where engineering-style checks (ranges, regex, allowed sets, cross-field rules) are exactly what's needed.

**Already in place on this branch (PR #32):**
- Frame split of the Checks Workbench into *Interne DQ-Checks* / *Contracts* (`apps/cockpit/src/pages/ContractWorkbench.tsx`), kind-derived frame, in-place promote, rename to "Checks Workbench".
- Library classification: each check carries `family` (observability|quality) and `gating` (gate|expensive|standard); library at `version: 4`; `volume_anomaly` added and wired into baselines + the volume metric family.
- The read-only catalog page `apps/cockpit/src/pages/CheckLibrary.tsx` (renders all check metadata — reuse it).

---

## 2. Agreed design (decisions locked)

1. **Softened G1, internal only.** Boundary **contracts keep hard G1** (no raw SQL — needed for BDC export + breaking-diff). For **internal gates**, relax the invariant to: *every check must be **classified** (family/gating/unit) and **scalar-shape-validated***. Raw SQL becomes admissible under those constraints — but is **deferred** (see §5), gated to platform/admin with value redaction + query timeout when it lands.
2. **`checks:` array on the gate document** is the canonical authoring form (one source, one `compiler_hash`, compiled after guarantees). Only on `internal_gate`.
3. **"Everything is a library check" at runtime.** Guarantees remain presets / a typed overlay (typed only for contracts, where diff + export need the structure). For Iteration 1, guarantees stay as-is and the builder is **additive** — see overlap rule in §4.

---

## 3. Document shape

Add an optional top-level `checks:` array to the gate document:

```yaml
product: DEMO_SRC_01
kind: internal_gate
dataset: DEMO_SRC_01
owned_by: platform
version: 0.1.0
guarantees: { ... }        # unchanged — still the 7 families
checks:                    # NEW — library-instantiated checks
  - id: value_range        # must exist in check_library.json
    params:
      "<SPALTE>": NET_AMOUNT
      "<MIN>": "0"
      "<MAX>": "100"
    expect: "= 0"          # prefilled from default_expect
    severity: fail         # prefilled from default_severity
```

`compiler_hash` (`yaml.safe_dump(contract)`) already covers `checks:` — no change needed for determinism.

---

## 4. Iteration 1 scope (file by file)

### Backend

**`packages/dq_core/library/check_library.json` — add a `type` to every param.**
The generic path must know per-param whether a value is an identifier or a literal, to apply S2 safely. Extend each `params[]` entry with `"type"`:
- `identifier` — column/table name → `_ident()` (regex + inventory existence + quote-escape).
- `number` — `<MIN>`, `<MAX>` → validate numeric, inject literally.
- `string` / `regex` — `<REGEX>` → escape single quotes (`'` → `''`); template already supplies the surrounding quotes.
- `value_list` — **restructure needed.** Today `allowed_values` uses one token `'<WERT1>', '<WERT2>'` that bakes in quotes. Change to a list-valued param the compiler assembles into `'a','b'` with per-item quote-escaping. (Until restructured, `allowed_values` should be excluded from the builder.)

**`packages/dq_core/contract/compiler.py` — add a `checks:` pass** in `compile_contract`, after the `not_null` loop (~line 173, before `return DatasetConfig(...)`):
- For each entry: `entry = check_by_id(chk["id"])`; reject unknown/empty `sql_template` (this naturally excludes `custom_sql`, whose template is empty — keeps it deferred for free).
- Bind params **by type**: `identifier` → existing `_ident(v, where, cols)`; `number`/`string`/`regex`/`value_list` → new typed escaping helpers. Then `_bind(...)`. Reuse `_mk(...)` but pass `unit` from the library entry and `expect`/`severity` from `chk`.
- The resulting `CheckDef.type` must equal the library `id` so the store's type→family/metric lookup keeps working (verify rollup, see §6).

**`packages/dq_core/contract/validator.py` — two changes (both load-bearing):**
1. `CONTRACT_SCHEMA` has `additionalProperties: false`, so add a `checks` property: an array of objects `{ id: string, params: object, expect: string, severity: enum }` (`additionalProperties: false` per item). Structural shape only.
2. **The SQL-smuggle linter (`_SQL_SMUGGLE` / `_lint_strings`) flags single quotes and SQL keywords.** `allowed_values`/`pattern_match` param values legitimately contain `'` and regex. **Exempt `checks[].params` values from `_lint_strings`** — their safety is enforced by the compiler's type-aware binding, not by the prose linter. Without this, valid checks are rejected as `[G1] SQL-verdaechtiges Muster`.
3. Keep **semantic** validation (id exists, all required param tokens present, type-correct) in the **compiler** (raises `CompileError` → surfaced as 422 in the dry-run/compile path), since the validator is library-agnostic by design. Don't duplicate it.

**`services/api/routers/contracts.py` — persist `checks:`.**
The PUT handler assembles the contract dict field-by-field (~line 76–91, ending `guarantees=data.get("guarantees") or {}`) and `certify_contract` does the same (~line 660–744). **Add `checks=data.get("checks") or []` to both assembly points** so it round-trips through `GitRepo(...).write_contract(...)`. `compile`/`dry-run` pick it up automatically via the compiler. Diff/BDC-export read `guarantees` only — leave them unchanged (internal `checks:` are not exported, by design).

### Frontend

**`apps/cockpit/src/types/index.ts`** — add `GateCheck = { id: string; params: Record<string,string>; expect: string; severity: Severity }` and `checks?: GateCheck[]` to `Contract`, `ContractOut`, `ContractPutBody`. Mirror in `toPutBody` (`ContractWorkbench.tsx`).

**`apps/cockpit/src/pages/ContractWorkbench.tsx`** — a **check builder** in the internal frame (`EditorPane`, below the guarantee editor; render only when `draft.kind === 'internal_gate'`):
- Source from `useLibrary()` (`apps/cockpit/src/api/library.ts`), grouped by `category`/`family`.
- **Overlap rule:** exclude the guarantee-covered template ids so no double-authoring is possible: `schema, duplicate, duplicate_composite, reference_integrity, freshness, row_count, completeness_pct, missing`. Also exclude `custom_sql` (deferred). Builder then offers ~11 checks.
- Param form from the library `params` metadata (labels/hints already there). `identifier` params use the inventory `Combobox` (as guarantees do); literals use typed inputs. Prefill `expect`/`severity` from `default_*`.
- Added checks render as removable rows; wire into `draft.checks`. Save goes through the existing PUT/certify path.

### Tests
- `tests/unit/test_compiler.py`: binds a `checks:` entry; per-type escaping (identifier via `_ident`, number, string/regex quote-escape, value_list assembly); rejects unknown id, missing/extra param tokens, unsafe identifier, empty `sql_template` (custom_sql).
- `tests/unit/test_validator.py`: accepts a well-formed `checks:` array; rejects malformed shape; confirms `checks[].params` values with quotes/regex are **not** flagged by the SQL-smuggle lint.
- Cockpit (`ContractWorkbench` test): builder renders in the internal frame, excludes guarantee-covered ids, adds a check into the draft.

---

## 5. Deferred (NOT in Iteration 1)
- **`custom_sql` / raw `sql` body.** The model carries it (a library-shaped check with author SQL + mandatory family/gating/unit + scalar-shape validation), but ship it later behind a platform/admin gate with value **redaction** + query **timeout**. The compiler's empty-`sql_template` rejection keeps it out for free until then.
- **Collapsing guarantees into pure `checks:` presets** (the "north star" of decision 3). Not needed for coverage.

---

## 6. Verification & gotchas
- **Run backend:** `make dev-backend` (uvicorn :8000). **Frontend:** `make dev-frontend` (vite :5173, proxies `/api`). Note: this is Windows; the Makefile env-var syntax runs under Git Bash.
- **Tests:** `python -m pytest tests/ -q` (366 green at baseline) and `cd apps/cockpit && npm run test` (76 green at baseline) + `npm run typecheck` + `npm run lint` (`--max-warnings 0`).
- **Family/gating rollup:** generic checks must roll into the cockpit's observability/quality status. The store maps by check `type` (`packages/dq_core/store/sqlite_store.py` `_METRIC_FAMILY`, and the family lookup). Verify a `value_range`/`pattern_match` check shows up under the right family after a run.
- **Line endings:** repo is `core.autocrlf=true`, no `.gitattributes` → commits normalize to LF; the "LF will be replaced by CRLF" warnings are noise.
- **`gh` is not installed** in the dev environment — PR #32 can't be updated via CLI here. Attach/link this doc manually, or install `gh` first.

---

## 7. Suggested order
1. Library param `type` + (optional) `value_list` restructure.
2. Compiler `checks:` pass with typed binding + unit tests → **green compiler is the gate before frontend.**
3. Validator schema + lint exemption + tests.
4. `contracts.py` persistence (PUT + certify).
5. Frontend types + builder + cockpit test.

Backend-first so the secure compile path exists before the UI sits on top of it.
