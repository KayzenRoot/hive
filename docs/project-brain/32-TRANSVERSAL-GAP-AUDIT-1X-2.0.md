# HIVE 1.x → 2.0 — Transversal Gap Audit

## Status
PLANNING AUDIT. First-pass release architecture exists in documents 17–31. This audit identifies cross-release gaps before any 1.1 implementation prompt is authorized.

## Audit method
Checked the release plan against:
- v1.0 canonical architecture and accepted boundaries;
- frozen V2 NECESSARY capability groups;
- release specifications 1.1–1.9;
- 2.0 completion gate;
- existing GEF adoption directions: compiled execution packs, HEDS delta-first review, Evidence Validity Fingerprint/carry-forward shadow, machine evidence manifest, source/module→tests/evals mapping and telemetry.

Classification:
- BLOCKING: must be resolved before relevant implementation;
- REQUIRED: necessary for the release train/2.0;
- EXPERIMENTAL: benchmark/shadow before promotion;
- FUTURE: not required for 2.0.

## Cross-release dependency graph

```text
1.0 stable foundation
 ├─> 1.1 Decision Fabric
 ├─> 1.2 Governance/Validity/Provenance
 │    ├─> 1.3 HUE/EET
 │    │    ├─> 1.4 C³
 │    │    └─> 1.5 Verification impact/evidence reuse
 │    ├─> 1.5 Orchestration/UADS/Verification
 │    └─> 1.6 Temporal Memory/Learning
 ├─> 1.7 Resources/Observability (integrates prior stable contracts)
 ├─> 1.8 Recovery (depends materially on 1.2 + 1.5 + durable-state families)
 └─> 1.9 Integration/Migration (depends on all stable prior releases)
      └─> 2.0 evidence closure
```

Important correction: release numbering is delivery order, not a license for circular dependency. A release may consume only stable earlier contracts or local contracts implemented in its own governed increment.

## Gap G-01 — Shared contract naming/versioning
Severity: REQUIRED before 1.2.

Multiple specs define fingerprints, receipts, validity and evidence envelopes. Without a naming/version registry, implementations could create near-duplicate schemas.

Resolution:
- 1.1 owns Decision-specific contracts;
- 1.2 introduces shared governance/validity/provenance contract registry;
- later releases reference shared contracts rather than clone fields;
- generated contract inventory becomes a validation artifact.

## Gap G-02 — Event vocabulary growth
Severity: REQUIRED.

1.1–1.9 propose many event families. Unbounded event proliferation could create dashboard/backend drift.

Resolution:
- existing Event Bus remains sole canonical event seam;
- domain-prefixed, versioned vocabulary;
- generated backend/frontend parity check;
- bounded payload schema;
- deprecation policy;
- aggregation events do not replace raw durable evidence where raw evidence is required.

## Gap G-03 — Migration ownership
Severity: BLOCKING before durable 1.1/1.2 changes.

Every release mentions migrations, but ownership must be singular.

Resolution:
- one Alembic lineage;
- migration author declares durable-state classification and rollback class;
- release evidence binds exact migration head;
- no feature-local migration runner.

## Gap G-04 — Cache taxonomy
Severity: REQUIRED before 1.1 cache implementation.

Existing context/provider caches plus future decision/HUE/C³ caches risk inconsistent invalidation.

Resolution:
define cache classes:
- EXACT_DERIVED;
- SEMANTIC_DERIVED;
- PROVIDER_HINT;
- EPHEMERAL_UI.

Every cache declares canonical basis, fingerprint/version, TTL if applicable, invalidation, rebuild and Redis-loss behavior.

Redis remains noncanonical for all classes.

## Gap G-05 — Policy taxonomy
Severity: BLOCKING before 1.5.

ToolPolicy, security, governance, decision and optimization policy must not become competing authorities.

Resolution:
freeze policy precedence in 1.2 and make 1.5 composition consume it. Optimization never overrides authority/security.

## Gap G-06 — Risk vocabulary
Severity: REQUIRED before Decision Fabric control promotion.

Specs use LOW/HIGH/CRITICAL and reversibility concepts without one shared contract.

Resolution:
create versioned ActionRisk:
- impact domain;
- reversibility;
- blast radius;
- canonicality;
- secret/network/tool exposure;
- evidence requirement.

Do not reduce risk to one opaque numeric score.

## Gap G-07 — Evidence identity
Severity: REQUIRED.

Review Evidence, UADS, Decision receipts, HUE edges and recovery receipts need a common reference pattern.

Resolution:
1.2 provenance envelope supplies shared evidence identity/lineage; domain schemas extend it.

## Gap G-08 — Evidence retention/storage growth
Severity: REQUIRED by 1.7/1.8.

More receipts/events/learning can grow indefinitely.

Resolution:
- canonical evidence retention policy;
- content-addressed dedup where appropriate;
- bounded indexes;
- derived aggregation;
- archival/compaction only with provenance;
- storage metrics and pressure behavior;
- never delete required release/recovery proof merely for optimization.

## Gap G-09 — Configuration/version compatibility
Severity: REQUIRED.

Feature flags, shadow modes, provider profiles and release settings need explicit compatibility.

Resolution:
configuration schema/version fingerprint; migration/default policy; unknown setting fail behavior; secrets excluded from fingerprints/logs.

## Gap G-10 — Clock/time semantics
Severity: REQUIRED before temporal memory and durable orchestration.

Observed/recorded/valid times and event ordering cannot rely on wall-clock equality.

Resolution:
- UTC timestamps for observation;
- durable ordering identity for canonical event sequence;
- temporal validity separate from ingestion time;
- no security/authority decision based only on client-provided time.

## Gap G-11 — Cancellation/idempotency
Severity: REQUIRED before 1.5.

Durable runs need explicit cancellation and retry semantics.

Resolution:
idempotency keys for supported operations, attempt identity, cancellation-safe points, irreversible-step declaration, recovery receipts.

## Gap G-12 — External/untrusted content boundary
Severity: REQUIRED before expanded autonomous/context integration.

Retrieved docs/tool/web/provider outputs can contain instructions.

Resolution:
content trust label + provenance; untrusted instructions treated as data; authority is derived only from HIVE policy/canonical governance.

## Gap G-13 — Benchmark corpus governance
Severity: BLOCKING before optimization promotion.

Benchmarks can be gamed accidentally if fixtures change with implementation.

Resolution:
- versioned benchmark corpus;
- train/tune vs holdout where learning/calibration occurs;
- exact fixture hashes;
- baseline release identity;
- quality + economy together;
- changes to corpus produce new benchmark version.

## Gap G-14 — Statistical uncertainty
Severity: REQUIRED for variable provider/performance benchmarks.

Single-run latency/token/provider outcomes can be noisy.

Resolution:
report sample count/distribution/variance or bounded summary appropriate to metric; deterministic fixtures remain exact. Do not turn noisy improvement into a hard claim from one run.

## Gap G-15 — GEF integration
Severity: REQUIRED, already directionally adopted.

Map:
- compiled Execution Packs → all executor WOs;
- HEDS delta-first review → Sol audits;
- Evidence Validity Fingerprint → 1.5;
- carry-forward graph → 1.3/1.5 shadow;
- machine evidence manifest → 1.5/1.9;
- source→tests/evals → 1.3;
- token/search/time telemetry → 1.4/1.7.

No separate GEF persistence core.

## Gap G-16 — Feature flag lifecycle
Severity: REQUIRED.

Experimental flags can become permanent debris.

Every flag declares:
- owner;
- default;
- introduced version;
- telemetry;
- promotion criterion;
- removal/expiry review version.

## Gap G-17 — API/MCP compatibility
Severity: REQUIRED.

Public API/MCP contract changes need explicit compatibility class and tests. Existing seven read-only MCP tools remain stable unless separately governed.

## Gap G-18 — Windows/Linux parity
Severity: REQUIRED.

HIVE local deployment targets both. New path/process/resource/recovery features require parity fixtures where OS behavior differs.

## Gap G-19 — Dependency/supply-chain governance
Severity: REQUIRED.

New libraries/providers must declare:
- license compatibility;
- pinned/bounded version policy;
- security maintenance;
- offline/local behavior;
- transitive risk;
- removal/fallback.

A useful GitHub project is not adopted merely because it benchmarks well.

## Gap G-20 — Jev audit not yet closed
Severity: BLOCKING only for Jev-specific 1.1 adapter, not for provider-independent Decision Fabric.

Need exact upstream identity, license, API stability, benchmark reproducibility and coupling analysis before WO-1.1-07 is promoted. Core 1.1 must not wait for Jev.

## Gap G-21 — 2.0 marketing claims
Severity: REQUIRED.

Performance/token/storage claims must be generated from reproducible evidence and carry benchmark/version provenance. No unsupported percentage in README/release notes.

## Gap G-22 — Backpressure/event storms
Severity: REQUIRED by 1.7.

Near-live telemetry plus orchestration/HUE can create event bursts.

Resolution:
bounded producers, pagination/stream reconnect, aggregation, rate-limited alerts, durable truth preservation.

## Gap G-23 — Database growth/index maintenance
Severity: REQUIRED by 1.7/1.8.

Plan table/index growth, vacuum/analyze operational guidance, event/evidence query bounds and migration performance fixtures. Do not add a second database for convenience.

## Gap G-24 — Degraded capability semantics
Severity: REQUIRED.

A service health light is insufficient. 1.9 must expose which capabilities remain trustworthy when Redis/provider/GPU/index/recovery dependencies fail.

## Gap G-25 — Release dependency rollback
Severity: REQUIRED.

If 1.6 depends on schema from 1.5, rollback documentation must state whether downgrade crosses incompatible migration state and whether restore is required. This is handled per release, not assumed globally safe.

## Scope disposition
NECESSARY for current 2.0 train: G-01 through G-25 except experimental implementations explicitly noted.
EXPERIMENTAL: learned escalation weights, semantic edge promotion, evidence carry-forward control path, cross-project learning, advanced provider-specific optimizations.
FUTURE: distributed consensus, Kubernetes, multi-tenant enterprise control plane, general graph database, autonomous canonical approval.

## Audit result
No architectural blocker invalidates the release train. The first pass is coherent, but G-03, G-05, G-13 and Jev-specific G-20 must be resolved before their affected implementation WOs.

## Next closure sequence
1. create shared 1.x contract/risk/cache/config/benchmark conventions;
2. close exact Jev technology audit;
3. freeze 1.1 dependency/WOs/acceptance matrix;
4. audit planning PR exact head;
5. promote approved planning into canonical project truth through governance;
6. only then generate WO-1.1-01 executor prompt.

## Stop condition
Do not issue a 1.1 implementation prompt until the shared conventions, Jev audit and 1.1 freeze are complete and the planning PR has an auditable promotion path.
