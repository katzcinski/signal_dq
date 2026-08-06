# ADR-0007 - Generic Operation Progress Channel

**Status:** accepted - grilled against the code on 2026-06-22.

> **Numbering note (2026-07-23):** originally filed as "ADR-0005", colliding with `ADR-0005_Scheduling.md`; renumbered to **ADR-0007**. Older references to "ADR-0005" in the context of the operation/progress channel mean this ADR.

Signal distinguishes a **DQ Run** from an **Operation**. A DQ Run executes quality checks and can produce persisted check results, compliance changes, and incidents; an Operation is user-triggered background work that reports progress and returns a verdict without being a quality-check execution.

We will persist progress in a generic progress stream, not by overloading `dq_run_progress.run_id` for non-run work. Existing run progress is migrated forward into the generic stream, and all new run and operation progress reads/writes go through the result-store interface. The old run-specific table can remain as legacy migration input, but new code does not dual-write to it.

The first Operation consumer is the HANA/Datasphere connection test. Its expected connection failures finish with a verdict (`ok=false`) rather than marking the Operation itself as failed; Operation `error` is reserved for Signal infrastructure failures such as worker crashes or result persistence failures. Operation poll and SSE reads are restricted to admins or the principal that created the Operation.
