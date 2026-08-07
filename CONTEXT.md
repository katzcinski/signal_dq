# Signal

Signal is a data-quality and data-contract governance tool for SAP Datasphere / BDC.
It classifies guarantees by *party boundary*, enforces them as SQL checks against a
HANA-reachable surface (the single GX-on-HANA executor), and tracks compliance over
the lineage of a data estate.

## Language

**Data Product**:
The whole of a dataset's pipeline across all layers (raw → core → business) under one
ownership. The unit the catalog/ORD lists. A product *contains* objects; it is not a
single object.
_Avoid_: "dataset" or "object" when you mean the whole product.

**Data Contract**:
A description of only the *edges* (ports) of a product — its promises to a counterparty.
Never describes the interior. On disk: `contracts/<product>.yaml`.
_Avoid_: bare "contract" when an internal gate is meant.

**Product Manifest**:
A thin artifact (`products/<name>.yaml`) declaring only a product's identity, owner hull,
and ports (`output_ports`, `inbound`). It never lists the interior and is not versioned.
The product aggregate is otherwise *derived*, not authored.
_Avoid_: "product file" or treating it as a spec/inventory of members.

**Interior**:
The objects between a product's inbound sources and its output ports (raw / core /
business-core) — *derived* from the lineage walk, never listed in the manifest.
Interior objects get internal gates, not contracts.
_Avoid_: German "Interieur" in code/English prose; "members" (too broad).

**Output Port**:
A boundary where a product's content is consumed across a party line. Defined by
*cross-boundary consumption*, not by topology or layer (a terminal/sink object is not
automatically a port). Signal enforces at the SQL-reachable port.

**Internal Gate**:
A guarantee-set with no agreed counterparty (`kind: internal_gate`). Produces team
incidents only — never a governance compliance state.

**DQ Run**:
An execution of a product/object's quality checks against a configured data surface.
It produces check results and may update compliance or incident state.
_Avoid_: "Operation" when persisted quality-check results are meant.

**Operation**:
A user-triggered background action in Signal that reports progress and produces a
verdict, but is not itself a quality-check execution.
_Avoid_: "Run" when no quality-check results are produced.

**boundary**:
The party-grenze classification of a guarantee-set: `internal | inbound | outbound`.
A *derived, read-side* attribute — computed from manifest intent ⋈ lineage reality
(ADR-0004), never hand-entered. Distinct from `kind`: the two are reconciled against
each other, not renamed into one another (until ADR-0001 §9 unifies them).

**kind**:
The on-disk per-contract discriminator: `internal_gate | consumer_contract |
provider_contract`. Sets the governance weight (ceremony, compliance ampel, SLA, ODCS
export eligibility). Set by seed/promote, not derived.
_Avoid_: conflating with ODCS's own `kind: "DataContract"` field, or with the derived
`boundary`.

**Freshness**:
A consumer-facing promise about **business/event recency** — the newest business fact
is no older than X — measured from a business timestamp column (e.g. `ORDER_DATE`).
_Avoid_: using "freshness" for pipeline liveness — that is **Load-Lag**.

**Load-Lag**:
A **technical** liveness/recency signal: when the pipeline last loaded/merged/replicated
(e.g. `sap_replication_lag`, a catalog modify-time like `M_TABLE_STATISTICS`). An
observability signal, *not* a contract guarantee — green Load-Lag ≠ fresh business data.

**Reconciliation**:
The continuous comparison of *intent* (manifest ports + contract `kind`) against
*reality* (the lineage walk). Its outputs are **findings** — deltas such as
**Boundary-Leak** (reality has a cross-boundary consumer the intent never declared),
**Contested** (two products claim the same object — `scope: port` when both declare
it as an output port, `scope: interior` when the walk assigns it to both interiors →
Foundation-Product candidate for the interior case), and **Dangling-Port** (a declared
port with no governance contract or no lineage node behind it).
_Avoid_: "validation" (that's the structural load gate, a different thing).
_Avoid_: "Contested-Interieur" in code (use `scope: interior` on the unified Contested finding).
