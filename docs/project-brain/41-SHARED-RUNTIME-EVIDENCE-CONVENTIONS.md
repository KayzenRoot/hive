# HIVE V2 — Shared Runtime & Evidence Conventions

## Status
ADOPTED FOR HIVE 1.x PLANNING. The subset below is mandatory for 1.1 and subsequent 1.x release specifications unless superseded by an accepted ADR. Closes transversal gaps that otherwise create incompatible vocabularies across releases.

## Objective
One vocabulary for contracts, risk, cache, configuration, benchmark evidence, time, idempotency and degraded capability.

## SC-01 Contract naming
All machine contracts use stable id + schema_version + producer_version + project scope + validity/provenance where relevant. Breaking schema changes require migration/version transition.

## SC-02 Risk
Canonical planning vocabulary:
LOW, MEDIUM, HIGH, CRITICAL, UNKNOWN.
UNKNOWN cannot be treated as LOW. Domain profiles may strengthen risk.

## SC-03 Cache taxonomy
- DERIVED_REBUILDABLE
- PROVIDER_PREFIX
- DECISION
- CONTEXT
- RETRIEVAL
- RESPONSE/SEMANTIC experimental
No cache is canonical truth. Cache key includes material project/basis/config/contract fingerprints. Redis loss must not corrupt canonical state.

## SC-04 Configuration
Configuration has source, scope, version/compatibility, secret classification and effective-value evidence. Unknown/incompatible config fails closed when safety/canonical behavior depends on it.

## SC-05 Time
Persist UTC instants for machine truth; preserve source timezone/offset when semantically relevant. Distinguish observed_at, occurred_at, recorded_at, valid_from/to and monotonic duration. Clock uncertainty is explicit for distributed/external evidence.

## SC-06 Idempotency/cancellation
Durable operations expose operation identity, attempt identity, idempotency semantics, cancellation state and recovery/reconciliation behavior.

## SC-07 Feature flags
Lifecycle: EXPERIMENTAL_DISABLED → SHADOW → LIMITED → ENABLED, or REJECTED/REMOVED. Flag state is evidence and cannot silently change canonical semantics.

## SC-08 Degraded capability
States:
AVAILABLE, DEGRADED_SAFE, UNAVAILABLE, UNKNOWN.
Degraded mode declares lost capabilities and forbidden claims. Silent fallback that changes correctness/security is prohibited.

## SC-09 Benchmark corpus governance
Corpus/fixture set has version, hashes, provenance, domain/profile, risk class, expected invariants and change review. Freeze before comparing candidate vs baseline.

## SC-10 Statistical evidence
Report sample count, distribution/variance where relevant, warm/cold conditions and confidence/uncertainty. Do not convert noisy single runs into universal percentage claims.

## SC-11 Evidence identity
Evidence binds project, source commit/snapshot, run/attempt, contract/checker/provider version, config fingerprint, timestamp, validity and content hash.

## SC-12 Retention
Canonical evidence retention follows governance. Large raw/derived evidence may use CAS/Zstd/dedup with references. Retention policy cannot delete the only proof for a still-current release claim.

## SC-13 Events/backpressure
Shared event vocabulary is versioned. Producers must tolerate bounded buffering/backpressure; event storms cannot exhaust local resources. Telemetry loss is surfaced, not silently treated as healthy.

## SC-14 Database growth
Measure logical/physical growth, indexes, vacuum/maintenance signals and retention impact. Optimizations require data-integrity proof.

## SC-15 API/MCP compatibility
Public contracts publish compatibility range and deprecation path. MCP remains read-only seven-tool baseline until an approved release explicitly evolves the contract.

## SC-16 Platform parity
Windows + Docker Desktop is first-class for current local installation. Linux/container paths remain covered where supported. Path/newline/permission differences receive fixtures.

## SC-17 Release dependency rollback
Each release records dependency on prior stable capabilities and rollback classification. A minor release cannot silently make rollback impossible.

## Stop condition
No release-specific spec may invent a conflicting risk/cache/evidence/time/config vocabulary after this convention is frozen.


## 1.1 mandatory subset
For Decision Fabric 1.1 the following conventions are FROZEN planning dependencies: SC-01 contract naming, SC-02 risk, SC-03 cache taxonomy, SC-04 configuration, SC-05 time, SC-07 feature flags, SC-08 degraded capability, SC-09 benchmark corpus, SC-10 statistical evidence, SC-11 evidence identity, SC-13 event/backpressure, SC-15 API/MCP compatibility, SC-16 platform parity and SC-17 release rollback.

SC-06, SC-12 and SC-14 remain adopted shared conventions and become directly binding whenever a 1.1 work order introduces durable operations, retention behavior or database-growth impact.
