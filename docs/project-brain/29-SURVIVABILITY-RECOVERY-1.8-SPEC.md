# HIVE 1.8.0 — Survivability & Recovery Specification

## Status
PLANNING CANDIDATE. Extends the v1.0 backup/restore, CAS integrity, restart and Redis-loss recovery foundations.

## Objective
Make failure survivable and recovery provable across PostgreSQL, CAS, derived indexes/cache, migrations and interrupted operations, with explicit Known-Good State and read-only survival behavior.

## Existing seams verified
- v1.0 already proves CAS retry/recovery integrity and corruption/truncation fail-closed behavior;
- restart and Redis-loss recovery exist;
- release candidate metadata documents backup/restore rollback;
- PostgreSQL + HIVE_DATA_ROOT are part of canonical recovery procedure;
- disk health is already surfaced in Control Center.

## SUR-01 — Failure Domain Model
Classify:
- Redis loss;
- API/dashboard restart;
- PostgreSQL unavailable/corrupt;
- CAS missing/corrupt;
- disk pressure/full;
- interrupted migration;
- interrupted promotion/run;
- derived index corruption;
- configuration incompatibility;
- partial backup;
- failed upgrade.

## SUR-02 — Known-Good State (KGS)
A KGS receipt binds:
- release/version/commit;
- migration head;
- canonical PostgreSQL backup identity;
- HIVE_DATA_ROOT/CAS manifest identity;
- configuration compatibility fingerprint without secrets;
- validation evidence;
- timestamp;
- artifact hashes.

KGS is evidence of a recoverable point, not a magical snapshot abstraction.

## SUR-03 — Backup Contract
Verified backup must distinguish:
- canonical structured state;
- canonical CAS/user-owned artifacts;
- configuration needed for restore;
- derived/rebuildable state;
- optional Redis state, never required for correctness.

Backup completion is claimed only after integrity verification.

## SUR-04 — Restore Contract
Clean-target restore proves:
- database integrity;
- migration compatibility;
- CAS identity/hash equivalence;
- project isolation;
- canonical source references;
- derived rebuild;
- health/integration.

## SUR-05 — CAS Reconstruction
Detect:
- orphan metadata/blob;
- missing physical content;
- hash mismatch;
- truncation/corruption;
- compression metadata mismatch.

Canonical content hash remains authoritative. Ambiguous reconstruction fails closed.

## SUR-06 — Redis-Loss Recovery
Redis may be deleted/recreated:
- no canonical truth lost;
- HOT caches rebuild;
- stale cache cannot resurrect invalid state;
- service returns to healthy state.

## SUR-07 — Derived-State Rebuild
Explicit registry of rebuildable:
- retrieval indexes;
- embeddings;
- HUE derived relations;
- context/decision cache;
- learning indexes/summaries.

Rebuild basis/provenance is canonical.

## SUR-08 — Disk Pressure Safety
Threshold policy:
- warn before unsafe capacity;
- throttle/pause optional writes;
- preserve room for integrity metadata/logging where feasible;
- block operations that would risk canonical corruption;
- never delete canonical user data automatically for space.

## SUR-09 — Read-Only Survival Mode
When safe mutation cannot be guaranteed, HIVE may enter bounded read-only survival:
- project/status/checkpoint;
- existing canonical reads;
- health/recovery guidance;
- evidence export where safe;
- no mutation/promotion/execution.

Exit requires explicit health/recovery proof.

## SUR-10 — Interrupted Migration Recovery
- startup detects migration state;
- partial/failed migration cannot report healthy target version;
- idempotent continuation only where migration contract allows;
- otherwise restore/repair path explicit.

## SUR-11 — Interrupted Operation Reconciliation
Integrate 1.2 governance + 1.5 orchestration:
- detect partial promotion/run;
- compare exact basis;
- reconcile idempotent states;
- quarantine ambiguity;
- emit recovery receipt.

## SUR-12 — Recovery Point Objective Evidence
Local HIVE does not promise enterprise HA. It reports:
- last verified KGS;
- last verified backup;
- unprotected changes since that point where measurable;
- restore test age;
- backup integrity status.

## SUR-13 — Recovery Telemetry/Control Center
Expose:
- KGS status;
- last backup/restore test;
- disk pressure;
- recovery-required state;
- canonical/derived health;
- corruption/quarantine;
- Redis rebuild;
- migration recovery;
- read-only survival.

## HIVE-original candidates
### Recovery Confidence Envelope
Compute evidence completeness around a recovery point from verified database/CAS/config/release proofs. It reports uncertainty rather than claiming binary recoverability from an untested backup.

### Canonical Survival Budget
Reserve bounded local storage headroom/policy for integrity-critical metadata and recovery operations before optional derived work.

### Rebuild Recipe Fingerprint
Every derived-state family has a deterministic recipe/version fingerprint so HIVE can prove whether existing derived data is compatible or must be rebuilt.

### Failure Injection Ledger
Keep reproducible fault scenarios and exact expected safety invariants as versioned engineering evidence, making survivability continuously testable.

## Work orders
- WO-1.8-01 failure domains/KGS
- WO-1.8-02 verified backup manifest
- WO-1.8-03 clean-target restore
- WO-1.8-04 CAS/derived rebuild registry
- WO-1.8-05 Redis/disk-pressure safety
- WO-1.8-06 read-only survival
- WO-1.8-07 migration/operation reconciliation
- WO-1.8-08 recovery telemetry + Control Center
- WO-1.8-09 fault-injection matrix
- WO-1.8-10 release/upgrade/rollback hardening

## Absolute gates
- canonical data loss in accepted fault fixtures = 0;
- corrupt CAS accepted as healthy = 0;
- Redis required for canonical recovery = 0;
- failed migration reports target healthy = 0;
- automatic disk cleanup deletes canonical user data = 0;
- ambiguous reconciliation silently promotes = 0;
- read-only survival performs mutation = 0.

## Stop condition
1.8.0 is releasable when a clean target can be restored from verified recovery material and representative failures prove either safe recovery, explicit quarantine/blocking, or bounded read-only survival without canonical truth loss.
