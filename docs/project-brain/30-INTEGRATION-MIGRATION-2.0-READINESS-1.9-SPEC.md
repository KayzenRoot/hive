# HIVE 1.9.0 — Integration, Migration & 2.0 Readiness

## Status
PLANNING CANDIDATE. Final 1.x capability-integration release before the governed 2.0 completion boundary.

## Objective
Prove that the independently delivered 1.1–1.8 capabilities operate as one coherent local-first HIVE system, preserve the supported stable upgrade chain, complete bounded MCP/IDE integration, and produce objective evidence for or against 2.0 readiness.

## INT-01 — Capability Compatibility Matrix
For each stable capability family record:
- owning release/module;
- public/internal contracts;
- durable-state dependencies;
- event vocabulary;
- policy dependencies;
- Control Center surface;
- upgrade/rebuild requirements;
- failure/degraded behavior.

Detect incompatible assumptions rather than papering over them with adapters.

## INT-02 — End-to-End Engineering Flow
Prove the integrated path:
project identification → Git/checkpoint basis → HUE intelligence → C³ context → Decision Fabric where eligible → governed orchestration → staged mutation → verification/UADS evidence → temporal memory/verified learning candidate → telemetry/Control Center → release/recovery evidence.

Every transition retains project/provenance identity.

## INT-03 — MCP/IDE-Native Completion
Preserve the stable read-only MCP contract and add only previously governed surfaces.

Rules:
- thin adapters;
- core persistence remains HIVE;
- capability/policy gates for any mutation/execution;
- no duplicate state inside MCP;
- bounded tool schemas;
- provider/IDE independence;
- degraded read-only/local operation when executor unavailable.

## INT-04 — Stable Upgrade Chain
Prove supported chain from released 1.0.0 through the current 1.x stable state.

For each hop:
- migration head;
- persistent state classification;
- derived rebuild;
- config delta;
- health;
- rollback class;
- evidence manifest.

A clean latest-version install does not substitute for upgrade testing.

## INT-05 — Representative State Migration
Migration fixtures include:
- multiple projects;
- PostgreSQL memory/telemetry;
- CAS data;
- Redis disposable state;
- indexes/derived state;
- checkpoints/governance;
- historical run/evidence data introduced by 1.x.

## INT-06 — Source/Hash Identity Preservation
Canonical source and CAS identities survive compatible migrations. If representation changes, content identity/provenance mapping is explicit and verified.

## INT-07 — Derived Rebuild Classification
Every derived family is registered with:
- canonical basis;
- recipe/version fingerprint;
- rebuild command/path;
- invalidation semantics;
- expected cost;
- failure behavior.

No canonical user state may be mislabeled derived to simplify migration.

## INT-08 — Cross-Capability Fault Matrix
Inject failures at boundaries:
- stale HUE → C³;
- missing authority → Decision Fabric;
- provider failure → orchestration;
- interrupted run → evidence/memory;
- invalid learning → context;
- resource pressure → background work;
- disk/Redis failure → recovery;
- migration mismatch → startup.

Expected outcome is safe fallback, explicit BLOCKED/UNKNOWN, quarantine or recovery. Never silent success.

## INT-09 — Policy Coherence Audit
Verify precedence remains coherent across:
security/governance → capability/tool policy → validity/evidence → decision/escalation → orchestration → optimization.

No release-local policy may create a bypass.

## INT-10 — Event/Telemetry Coherence
- one canonical Event Bus;
- versioned event vocabulary;
- frontend/backend vocabulary parity;
- project-scoped ordering/provenance;
- bounded retention/aggregation;
- no fabricated metrics.

## INT-11 — Control Center 2.0 Readiness
Final integrated views must cover:
project fleet, runs, tokens, cache, context, storage, retrieval/HUE, memory/learning, decisions, tests/evidence, resources/health, events, alerts, release/migration/recovery.

A view may show UNKNOWN/UNAVAILABLE, but required domains cannot silently disappear.

## INT-12 — Provider Independence Audit
Test at least:
- provider available;
- provider unavailable;
- provider malformed/timeout;
- optional provider adapter absent.

Core local HIVE remains usable within its documented degraded envelope.

## INT-13 — Performance Regression Budget
Compare 1.9 integrated system against stable baselines:
- startup;
- idle resources;
- API/dashboard latency;
- indexing;
- retrieval/context;
- orchestration overhead;
- storage;
- tokens/provider calls.

Regressions require explicit justification or correction.

## INT-14 — Security Regression
Re-run:
- project isolation;
- path normalization;
- tool/capability denial;
- secret redaction;
- network boundaries;
- staged/canonical separation;
- migration/recovery security;
- MCP surface constraints.

## INT-15 — 2.0 Evidence Index
Machine/human-readable index linking every frozen V2 NECESSARY capability and DoD clause to:
- implementing release;
- exact tests;
- benchmark/security/recovery evidence;
- documentation;
- current status;
- unresolved risk.

No prose-only completion claim.

## HIVE-original candidates
### Compatibility Proof Graph
Build a generated graph from contracts, migrations, tests and release evidence showing which compatibility claims have direct proof and which remain UNKNOWN.

### Migration Shadow Twin
Before destructive/irreversible migration steps, reproduce the upgrade against a bounded copy/fixture and compare canonical identities/health where local resources permit.

### Degraded Capability Map
HIVE computes which capabilities remain trustworthy after a dependency/provider failure rather than collapsing system health to one red/green flag.

### Evidence Closure Scorecard
Not a quality score. A deterministic coverage report of required DoD evidence: PROVEN, NOT_APPLICABLE, MISSING, STALE, BLOCKED. It must never convert missing evidence into a percentage-based approval.

## Work orders
- WO-1.9-01 compatibility/contracts matrix
- WO-1.9-02 integrated E2E flow
- WO-1.9-03 MCP/IDE completion
- WO-1.9-04 upgrade-chain fixtures
- WO-1.9-05 representative migration + derived rebuild
- WO-1.9-06 cross-capability fault matrix
- WO-1.9-07 policy/event coherence
- WO-1.9-08 Control Center readiness
- WO-1.9-09 provider/performance/security regression
- WO-1.9-10 2.0 evidence index + release hardening

## Absolute gates
- canonical data loss = 0;
- cross-project leak = 0;
- policy bypass = 0;
- failed migration reports success = 0;
- missing required DoD evidence reported proven = 0;
- provider absence makes documented local degraded core unusable = 0;
- required Control Center domain silently absent = 0.

## Stop condition
1.9.0 is releasable when the 1.x train operates coherently as one system and the generated 2.0 evidence index can identify every remaining gap without inference.
