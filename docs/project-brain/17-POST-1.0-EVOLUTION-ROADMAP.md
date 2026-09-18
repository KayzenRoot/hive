# HIVE — Post-1.0 Evolution Roadmap

## Status
PLANNING — canonical candidate, not yet promoted.

## Baseline
- `v1.0.0` remains the stable production baseline.
- The accepted V0.1 lineage is preserved.
- Existing accepted ADRs remain authoritative unless explicitly superseded by an approved ADR.

## Release strategy
HIVE evolves in-place through SemVer instead of cloning V1 into a separate V2 repository.

```text
1.0.0 stable
  -> 1.1.0
  -> 1.2.0
  -> 1.3.0
  -> ...
  -> 2.0.0
```

Rules:
1. Stable releases are immutable.
2. A new backwards-compatible vertical capability normally targets a MINOR release.
3. Corrections to an already released capability normally target a PATCH release.
4. Breaking contracts require explicit architecture/governance approval and appropriate SemVer treatment.
5. Each release must be independently installable/upgradable and objectively tested before promotion.
6. The installed stable version remains usable while the next release is developed.
7. Production feedback may generate corrective PATCH releases without silently expanding scope.
8. No release is promoted solely because a module was planned. It must satisfy its release acceptance criteria and evidence gates.

## Destination
The former "V2" vision is now a destination reached incrementally. `2.0.0` is released only when the complete approved V2 capability set and its final Definition of Done are objectively satisfied.

## Planning model
The post-1.0 program is organized as:

```text
PROGRAM
  -> CAPABILITY AREA
      -> MODULE
          -> SECTION
              -> WORK ORDER
                  -> TEST / EVIDENCE
                      -> RELEASE
```

Every planned item is classified:
- NECESSARY
- IMPORTANT
- FUTURE
- OUT OF SCOPE

Only evidence-backed NECESSARY work enters a release automatically.

## Innovation rule
Every capability-area planning pass must explicitly examine:
- current proven techniques;
- promising new/open-source techniques;
- deterministic alternatives to LLM calls;
- local-first opportunities;
- token/context/storage reduction;
- latency and throughput;
- correctness and retrieval quality;
- security and fail-closed behavior;
- observability and benchmarkability;
- provider independence;
- HIVE-original candidate techniques.

New technology is not adopted because it is fashionable. It must have a measurable hypothesis, bounded integration surface, fallback strategy and benchmark plan. Experimental ideas remain behind adapters/flags until validated.

## Release train — initial map
The exact ordering after 1.1.0 remains subject to source audit and planning freeze.

### 1.0.0 — Stable baseline
Accepted production baseline. No feature changes.

### 1.1.0 — Decision Fabric
Goal: avoid unnecessary generative reasoning by resolving bounded decisions through deterministic rules and/or typed decision providers, with confidence/risk/cost-aware escalation.

Candidate capabilities:
- deterministic decision prefilter;
- typed decision contracts;
- confidence distributions;
- AUTO / REVIEW / ESCALATE policy;
- risk-aware escalation;
- decision fingerprints;
- decision cache;
- batched decisions;
- bounded context projection for decisions;
- provider-independent DecisionProvider adapter;
- optional Jev-compatible adapter, never mandatory;
- local decision-provider seam;
- fail-closed sensitive-action policy;
- decision telemetry in Control Center;
- benchmark comparing baseline versus Decision Fabric.

HIVE-original research candidates:
- Escalation Economics: combine uncertainty, action risk, context cost and expected inference cost before escalation;
- Decision Delta: reuse unchanged decision state and score only material deltas when correctness permits;
- Confidence Debt: accumulate repeated borderline decisions and force periodic stronger verification;
- Evidence-Weighted Escalation: confidence is insufficient alone; provenance strength affects escalation;
- Decision Shadow Mode: run the new fabric without controlling production behavior first, compare it against baseline, then promote only after evidence.

Release gate:
- no measurable regression beyond approved threshold;
- deterministic paths use zero LLM calls;
- sensitive actions fail closed;
- provider failure has explicit fallback;
- token/cost/latency savings measured;
- project isolation and provenance preserved;
- upgrade and rollback from 1.0.0 tested.

### 1.2.0+ — Former V2 capability train
To be frozen after a complete audit of all prior V2 planning sources. Each capability will receive:
- module/section inventory;
- dependency ordering;
- classification;
- architecture impact;
- release target;
- benchmarks;
- migrations and compatibility requirements;
- rollback strategy;
- Control Center surface;
- tests and evidence gates.

## Compatibility contract
Post-1.0 development must preserve:
- local-first operation;
- Docker Compose primary deployment;
- PostgreSQL canonical durable structured state;
- pgvector initial vector layer unless an approved decision changes it;
- Redis as reconstructible HOT cache only;
- Git as canonical source-code history;
- CAS/hash/dedup/Zstd principles;
- deterministic-first execution;
- progressive disclosure;
- provider independence;
- staged executor claims;
- MCP as integration interface rather than persistence core;
- canonical governance and exact-head audit.

## Upgrade contract
Every MINOR/PATCH release must document and test, when applicable:
1. upgrade from the immediately previous stable release;
2. data/schema migration;
3. configuration migration;
4. rollback limitations;
5. persistent-volume preservation;
6. health verification;
7. release provenance;
8. post-upgrade smoke/integration tests.

## Next planning increment
Before implementation:
1. inventory all former HIVE V2 planning artifacts available in canonical/user-provided sources;
2. reconstruct the complete module/section map without inventing missing prior decisions;
3. identify gaps not previously planned;
4. research and propose new technologies per capability area;
5. classify all additions;
6. freeze the release train progressively;
7. fully specify 1.1.0 Decision Fabric;
8. only then issue its implementation Work Order.

## Stop condition
Planning increment stops when the prior V2 inventory, gaps, release mapping and 1.1.0 specification are auditable. No product implementation is authorized by this document alone.
