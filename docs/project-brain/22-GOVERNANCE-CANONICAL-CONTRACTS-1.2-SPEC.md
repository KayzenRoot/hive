# HIVE 1.2.0 — Governance & Canonical Contracts Specification

## Status
PLANNING CANDIDATE. Depends on 1.1 release evidence only where Decision Fabric primitives are reused. Existing accepted ADRs remain authoritative.

## Objective
Create explicit, versioned and auditable contracts for identity, authority, validity, provenance, promotion and reconciliation across HIVE canonical and derived state.

## Non-goals
- replacing Git as source-code history;
- making Redis canonical;
- allowing model output to self-promote;
- building distributed consensus;
- multi-user enterprise tenancy;
- autonomous canonical approval.

## GC-01 — Global Object Identity
Define stable identities for canonical and derived objects.

Minimum semantics:
- object kind;
- project scope;
- immutable identity;
- version/revision where mutable logical objects exist;
- content identity/hash where applicable;
- creation provenance;
- parent/source identities.

Identity must not depend on display names or unstable paths alone.

## GC-02 — Source Authority Hierarchy
Encode explicit authority classes rather than relying on implicit conventions.

Candidate hierarchy:
1. accepted canonical governance;
2. Git canonical source/history;
3. PostgreSQL canonical structured state;
4. validated canonical CAS artifacts;
5. staged/validated evidence;
6. derived indexes/embeddings/summaries;
7. Redis HOT state;
8. unverified external/model output.

Specific domains may refine this hierarchy through approved policy, but lower-authority sources cannot silently supersede higher-authority truth.

## GC-03 — Validity Contract
Versioned validity states for objects/evidence:
- CURRENT;
- STALE;
- SUPERSEDED;
- QUARANTINED;
- INVALID;
- UNKNOWN where evidence is insufficient.

Validity must include reason/provenance and must not be inferred as CURRENT from mere existence.

## GC-04 — Provenance Envelope
Reusable bounded provenance:
- project;
- source object;
- source revision/hash;
- producing component/version;
- policy/schema version;
- timestamps;
- validation evidence;
- lineage/parent references;
- trust/authority class.

No secrets or unnecessary raw content.

## GC-05 — Staged → Canonical Promotion State Machine
Explicit states:
- STAGED;
- VALIDATING;
- VALIDATED;
- PROMOTION_PENDING;
- CANONICAL;
- REJECTED;
- QUARANTINED.

Transitions are deterministic/policy-gated. Model/provider confidence alone cannot promote.

## GC-06 — Cross-Store Commit Protocol
When one logical promotion touches PostgreSQL + CAS + Git-derived identity or other durable seams:
- define preparation;
- write order;
- commit marker;
- idempotent retry;
- interruption detection;
- reconciliation;
- quarantine on ambiguous partial state.

Do not pretend atomicity exists across systems where it does not.

## GC-07 — Reconciliation Engine
Detect and classify:
- orphan CAS blobs/metadata;
- canonical row with missing blob;
- stale derived index;
- mismatched source hash;
- interrupted promotion;
- incompatible schema/policy version;
- Redis-only residue.

Repairs must be deterministic where possible. Ambiguous repair fails closed/quarantines.

## GC-08 — Policy Precedence
Define versioned precedence among:
- security;
- canonical governance;
- project policy;
- capability/tool policy;
- release/migration policy;
- optimization policy.

Conflicts must produce an explicit decision/error, never silent last-write-wins.

## GC-09 — Freshness & Invalidation
Shared primitives for:
- source HEAD/hash change;
- policy version change;
- schema change;
- provider profile change;
- evidence expiration;
- dependency invalidation.

This should reduce bespoke stale logic across context, retrieval, memory, decisions and future learning.

## GC-10 — Schema/Contract Registry
Compact registry for versioned public/internal contracts:
- contract name;
- version;
- owner module;
- compatibility class;
- migration/adapter path;
- deprecation status.

Avoid a heavyweight schema platform. Prefer deterministic repository artifacts generated from real contracts when feasible.

## GC-11 — Governance Telemetry
Extend existing Event Bus with bounded events for:
- validity changed;
- promotion staged/validated/promoted/rejected;
- reconciliation started/completed/blocked;
- policy conflict;
- quarantine entered/exited.

## GC-12 — Control Center Governance View
Expose:
- canonical vs staged counts;
- stale/quarantined objects;
- reconciliation health;
- recent promotions/rejections;
- authority/policy conflicts;
- provenance drill-down;
- migration/schema compatibility warnings.

No write capability is implied by observability.

## GC-13 — Decision Fabric Integration
If 1.1 is available:
- Decision Fabric may classify/escalate bounded governance questions;
- it cannot authorize canonical promotion;
- governance validity/evidence strength may feed Decision Fabric;
- Decision Fabric receipts remain derived evidence.

1.2 must remain architecturally understandable if the optional probabilistic provider path is disabled.

## GC-14 — Migration & Compatibility
Upgrade from 1.1.x:
- preserve existing canonical state;
- backfill only evidence that can be deterministically reconstructed;
- UNKNOWN rather than invented provenance;
- migrations idempotent where applicable;
- interrupted migration startup gate;
- rollback constraints documented.

## HIVE-original research candidates

### Canonical Truth Lattice
Represent authority + validity + provenance as a composable comparison model so modules can answer "which evidence can dominate?" without ad-hoc condition chains.

Candidate only until semantics are proven unambiguous.

### Provenance Compression
Store repeated lineage prefixes/content identities efficiently while retaining lossless reconstructibility and auditability.

Must prove storage benefit before promotion.

### Reconciliation Receipts
Every automatic repair emits before/after identities, rule version and proof so recovery is auditable and replay-safe.

### Validity Propagation Graph
Bounded deterministic invalidation from canonical changes to derived objects. Prefer existing dependency/index evidence rather than a new general graph database.

## Acceptance criteria
1. No existing canonical source loses authority.
2. Redis remains reconstructible/noncanonical.
3. Cross-project authority/provenance mixing is impossible in accepted fixtures.
4. Partial cross-store promotion is detected.
5. Ambiguous reconciliation fails closed.
6. Stale/invalid derived state cannot masquerade as current.
7. Model/provider output cannot self-promote.
8. Provenance absence is UNKNOWN, not fabricated.
9. Existing v1.0/1.1 behavior remains compatible or migration is explicit.
10. Governance telemetry uses the existing Event Bus.
11. Control Center reports real state.
12. Restart/retry behavior is idempotent for supported reconciliation paths.

## Proposed work-order sequence
- WO-1.2-01 identity + provenance contracts
- WO-1.2-02 authority + validity model
- WO-1.2-03 policy precedence + freshness/invalidation
- WO-1.2-04 staged promotion state machine
- WO-1.2-05 cross-store commit/reconciliation
- WO-1.2-06 schema/contract registry
- WO-1.2-07 telemetry + Control Center
- WO-1.2-08 migration/recovery/security integration
- WO-1.2-09 benchmark + release hardening

## Release gates
- zero silent partial promotions in accepted fault fixtures;
- zero cross-project provenance leaks;
- zero unverified self-promotion;
- reconciliation fault matrix green;
- migration/upgrade green;
- full existing regression green;
- performance overhead measured;
- storage overhead measured;
- Control Center truthfulness verified.

## Stop condition
1.2.0 is releasable only when authority, validity, provenance and reconciliation semantics are explicit and fault-tested across the canonical stores actually touched by HIVE.
