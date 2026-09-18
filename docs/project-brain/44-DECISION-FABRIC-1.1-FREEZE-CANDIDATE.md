# HIVE — Post-Jev Decision Fabric Freeze Candidate

## Status
PLANNING / FREEZE CANDIDATE. No implementation authorization.

## Purpose
Consolidate the 1.1 Decision Fabric after the Jev/OpenJev audit and transversal contracts. This document narrows what 1.1 must prove before the first implementation work order can exist.

## 1.1 objective
Introduce a provider-independent bounded-decision runtime that reduces unnecessary generative inference while preserving or improving verified correctness, governance and fail-closed behavior.

## Required modules
### DF-A Contract Kernel
Typed decision request/result/receipt. Declared options only. Project/basis/config/profile/provenance fingerprints.

### DF-B Deterministic Resolver
Git, hashes, AST, policy, static checks, exact comparisons and other deterministic answers execute before semantic scoring.

### DF-C Context Projector
Build the minimum authority-aware decision capsule from C3-compatible sources. No new competing retrieval engine.

### DF-D DecisionProvider
Stable provider seam:
- fixture/deterministic test provider;
- structured generative provider;
- optional remote specialized scorer;
- experimental local direct-logit scorer.

No external provider is core truth.

### DF-E Calibration Firewall
Raw provider confidence is never direct authority. Calibration validity is provider + decision-kind + domain-profile aware.

### DF-F Escalation / Decision Value Router
Deterministic policy chooses AUTO, REVIEW or ESCALATE using risk, evidence quality, uncertainty, calibration, cost/latency/resources and domain profile. Economy cannot bypass mandatory proof.

### DF-G Fingerprint / Cache / Decision Delta
Derived decision cache only. Redis remains noncanonical. Decision Delta may reuse/score only material changes when contract/basis compatibility proves it safe.

### DF-H Confidence Debt
Repeated borderline/unstable decisions accumulate verification pressure rather than being normalized as success.

### DF-I Batch / Shared-State Decision Pack
Batch independent decisions over one bounded state. Shared-prefix/KV optimization remains SHADOW until equivalence/stability evidence passes.

### DF-J Shadow Comparator
Candidate paths run beside baseline without controlling canonical/destructive behavior. Exact disagreements, calibration and cost deltas are retained.

### DF-K Sensitive Boundary
Decision Fabric never independently authorizes canonical mutation, secrets, destructive operations, security-boundary bypass or high-risk external actions.

### DF-L Telemetry / Control Center
Real decision events, provider path, confidence/calibration, escalation, cache/delta, disagreement, tokens/context/latency/resources and quality evidence.

### DF-M Benchmark & Promotion
Frozen corpus, domain/risk strata, critical false-AUTO gate, calibration metrics and economy metrics. Promotion is per decision kind, never all-or-nothing.

### DF-N Upgrade/Rollback
1.0 remains stable. 1.1 schema/config additions must have upgrade, downgrade/rollback classification and user-state preservation evidence.

## Non-goals for 1.1
- replacing C3/HUE/memory;
- general autonomous execution;
- mandatory Jev/TypeSafe dependency;
- making local LLM mandatory;
- Model Router as core;
- free-form reasoning engine;
- security policy delegated to model;
- broad V2 migration.

## Provider precedence
1. deterministic answer when sufficient;
2. local scorer only if calibrated/eligible;
3. specialized remote scorer if configured/eligible;
4. structured generative provider if required;
5. REVIEW/ESCALATE/UNAVAILABLE when no valid provider exists.

The router may choose a more expensive path when risk/quality requires it.

## Minimum benchmark corpus
- deterministic controls;
- bounded semantic classification;
- evidence supports/contradicts/not-addressed;
- missing/stale evidence;
- adversarial/untrusted input;
- cross-project isolation;
- safety-sensitive decisions;
- retry/next-step;
- representative domain-profile cases.

## Quality gates
- deterministic questions routed to LLM when deterministic resolver can answer: 0 in governed fixture set;
- critical false AUTO: 0 in governed critical fixtures;
- malformed/undeclared option accepted: 0;
- cross-project evidence leakage: 0;
- stale calibration silently treated current: 0;
- provider failure converted into success: 0;
- hard policy bypass by provider confidence: 0;
- canonical/destructive authority granted by scorer alone: 0.

## Economy gates
No universal percentage target is frozen before baseline measurement. Report fresh/cached/output tokens, sent context, latency p50/p95, cost, CPU/RAM/GPU/VRAM and cache/delta effects together with quality.

A candidate is not promoted on token savings alone.

## Promotion states per decision kind
SHADOW_ONLY
CONTROL_ELIGIBLE_LOW_RISK
REVIEW_ONLY
DISABLED

Higher-risk promotion requires explicit later evidence and governance.

## Compatibility with Jev research
Jev-compatible remote scoring is optional.
Local direct-logit scoring is experimental.
Prefix/shared-state optimization is experimental and shadow-only initially.
HIVE owns policy, calibration, evidence, routing and fallback.

## Implementation work-order sequence after freeze
1. contract + deterministic resolver;
2. projector + fingerprints;
3. fixture/structured provider seam;
4. calibration + escalation/router;
5. cache + delta;
6. shadow comparator;
7. optional scorer adapters;
8. batch + Confidence Debt;
9. telemetry/Control Center;
10. benchmark corpus and baseline;
11. controlled promotion;
12. release hardening.

Each work order must inspect existing repository seams first and must not create duplicate policy/event/cache/context infrastructure.

## Freeze blockers
Before issuing WO-1.1-01:
- reconcile unresolved legacy names that could materially alter 1.1;
- update Coverage Matrix with Jev audit disposition;
- freeze shared conventions used by 1.1;
- identify exact existing code seams and migrations to extend;
- define benchmark fixture ownership and evidence schema;
- audit 1.1 against current Scope/Architecture/Decisions/DoD.

## Stop condition
1.1 planning becomes FROZEN only when every blocker above is closed and the first executor prompt can be self-contained without asking Codex to invent architecture.
