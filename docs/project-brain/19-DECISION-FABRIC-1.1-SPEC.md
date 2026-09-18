# HIVE 1.1.0 — Decision Fabric Specification

## Status
PLANNING CANDIDATE. No implementation is authorized until governance promotion.

## Objective
Add a provider-independent, bounded decision layer that resolves cheap/high-confidence decisions before generative execution and escalates uncertain, risky, weak-evidence or economically irrational decisions.

## Non-goals
- replacing HIVE retrieval/context/memory;
- making Jev mandatory;
- autonomous canonical approval;
- allowing probabilistic output to bypass deterministic security/policy;
- hiding uncertainty behind a single confidence number;
- weakening local-only operation.

## Architectural position
```text
Task/Event/Tool request
        |
Deterministic prefilter
        |
Decision Context Projector
        |
Decision Policy + Provider (optional)
        |
Evidence/Confidence/Risk/Cost evaluator
        |
+---------+----------+------------+
| AUTO    | REVIEW   | ESCALATE   |
+---------+----------+------------+
        |
Decision receipt + telemetry
```

Deterministic policy always has authority over probabilistic providers for hard constraints.

## Modules and sections

### DF-01 — Typed Decision Contract
Define a versioned `decision-contract-v1`.

Required fields:
- decision_id;
- project_id;
- task/run identity when applicable;
- decision_kind;
- bounded candidate set;
- selected candidate(s);
- confidence/distribution when provider-backed;
- evidence references;
- risk class;
- policy outcome;
- escalation reason(s);
- provider/profile identity without secrets;
- input fingerprint;
- timestamps/validity;
- receipt provenance.

Rules:
- candidates are explicit and bounded;
- provider cannot invent an undeclared action;
- malformed/missing/duplicate candidates fail closed;
- non-finite scores fail closed;
- decision output is derived evidence, not canonical truth by itself.

### DF-02 — Deterministic Prefilter
Resolve decisions that normal code can answer reliably before any decision-provider call.

Examples:
- exact policy match;
- cache/fingerprint hit;
- known capability denial;
- invalid/stale input;
- unsupported decision kind;
- already-satisfied invariant.

Telemetry must distinguish deterministic resolutions from provider resolutions.

### DF-03 — Decision Context Projector
Produce the smallest decision-specific context from already-authorized HIVE evidence.

Rules:
- no arbitrary repository dump;
- project-scoped;
- explicit provenance;
- bounded size;
- stable serialization;
- material input changes alter fingerprint;
- context omission must be visible;
- security/governance evidence cannot be silently evicted when required.

### DF-04 — DecisionProvider Adapter
Provider-independent interface.

Initial provider modes:
1. deterministic-only;
2. test fixture provider;
3. optional Jev-compatible adapter if integration is technically/licensing-compatible;
4. future local provider adapter.

The core contract must not depend on Jev SDK types.

### DF-05 — Escalation Policy
Canonical outcomes:
- `AUTO`: decision may proceed within its explicitly authorized low-risk capability;
- `REVIEW`: insufficient assurance for automatic action, retain for bounded review path;
- `ESCALATE`: stronger reasoning/evidence/provider is required.

Hard security/canonical-promotion constraints cannot be downgraded by provider confidence.

### DF-06 — Escalation Economics
HIVE-original candidate.

Compute an auditable escalation signal from normalized factors:
- uncertainty;
- action risk;
- evidence weakness;
- expected context/inference cost;
- reversibility;
- policy criticality.

No opaque single formula is frozen yet. Calibration must be benchmark-driven. Cost never overrides hard safety/integrity rules.

### DF-07 — Evidence-Weighted Escalation
Confidence is not sufficient.

A high-confidence decision supported by weak/stale/low-authority evidence can still escalate. Evidence evaluation reuses HIVE validity/provenance concepts rather than duplicating canonical truth.

### DF-08 — Decision Fingerprint & Cache
Cache only when semantic inputs, policy version, provider profile, relevant evidence validity and candidate set are compatible.

Rules:
- Redis may hold HOT decision cache;
- Redis remains non-canonical;
- transient provider/security failures are not successful cache entries;
- policy/authority/evidence changes invalidate affected decisions;
- false-hit benchmark required.

### DF-09 — Decision Delta
HIVE-original candidate.

When a previous compatible decision exists, identify material input deltas. Reuse is allowed only if a deterministic compatibility predicate proves unchanged decision semantics. Otherwise perform full evaluation.

### DF-10 — Confidence Debt
HIVE-original candidate.

Repeated borderline automatic decisions accumulate bounded verification debt. Policy may force stronger verification after configurable evidence-backed conditions.

Requirements:
- no hidden long-term behavioral mutation;
- debt state/provenance visible;
- reconstructible durable truth if durable state is required;
- reset/expiry rules explicit.

### DF-11 — Batch Decision Path
Permit bounded batches for independent homogeneous decisions when provider supports it.

Requirements:
- item identity preserved;
- partial/misaligned provider output fails closed;
- per-item provenance/confidence;
- no cross-project batch;
- batch savings measured separately.

### DF-12 — Shadow Mode
Mandatory first production-validation mode for probabilistic Decision Fabric paths.

Behavior:
- baseline HIVE remains authoritative;
- Decision Fabric computes candidate outcomes;
- no shadow outcome changes canonical/execution behavior;
- compare agreement, disagreement, latency, token/cost and evidence quality;
- disagreements retained as bounded evidence.

Promotion from shadow to control path requires benchmark and governance approval.

### DF-13 — Sensitive Action Boundary
Decision Fabric cannot independently authorize:
- canonical governance promotion;
- destructive filesystem operations;
- secret disclosure;
- unsafe network expansion;
- protected-main bypass;
- unbounded execution;
- cross-project access.

Those remain controlled by existing deterministic policy/governance.

### DF-14 — Telemetry & Control Center
Expose real metrics:
- decisions by kind/outcome;
- deterministic resolution rate;
- provider invocation rate;
- AUTO/REVIEW/ESCALATE rate;
- confidence distribution where meaningful;
- evidence-strength distribution;
- shadow agreement/disagreement;
- decision cache hit/miss/invalidations;
- estimated tokens/cost avoided;
- latency avoided/added;
- provider failures/fallbacks;
- confidence-debt events;
- decision-delta reuse;
- project-scoped recent decision traces.

No fake savings metric. Estimated values must be labeled estimates.

### DF-15 — Benchmark Harness
Compare 1.0 baseline behavior against Decision Fabric.

Required dimensions:
- task correctness;
- decision correctness against deterministic/approved fixture truth;
- critical misses;
- false AUTO;
- false cache hit;
- escalation precision/recall where fixture labels support it;
- fresh input tokens;
- cached tokens when measurable;
- output tokens;
- decision-provider calls;
- generative LLM calls avoided;
- latency;
- cost when provider data supports it;
- context bytes/tokens;
- reproducibility;
- shadow disagreement.

Optimization claim is rejected if savings cause material correctness degradation beyond approved threshold.

### DF-16 — Upgrade / Rollback
Upgrade from 1.0.0 must preserve existing project/task/context/memory/CAS data.

If migrations are introduced:
- forward migration tested;
- interrupted migration fails safely;
- rollback limitations documented;
- derived decision state may be rebuildable;
- canonical existing state must not depend on Redis.

Rollback to 1.0.0 must be documented before release promotion.

## Proposed implementation seams
Executor must inspect the actual repository before selecting file paths. Likely conceptual seams:
- decision domain/contracts;
- provider adapters;
- policy/escalation service;
- cache/fingerprint;
- telemetry/events;
- API projection;
- dashboard views;
- benchmark/test fixtures.

Do not create parallel retrieval, provenance, policy or telemetry engines if existing HIVE services can be extended cleanly.

## Acceptance criteria
1. Existing 1.0 tests remain green.
2. Deterministic prefilter proves zero provider/LLM calls for eligible fixtures.
3. Provider-independent contract tested.
4. Jev is optional and absence does not degrade existing HIVE operation.
5. Provider malformed output fails closed.
6. Project isolation tested.
7. Hard policy cannot be overridden by confidence.
8. Shadow mode cannot alter execution/canonical state.
9. Decision cache false-hit fixture count is zero.
10. Provider failure has explicit bounded fallback/escalation.
11. Telemetry is real and project-scoped.
12. Benchmark reports quality and economy together.
13. Upgrade from 1.0.0 is tested.
14. Rollback constraints documented/tested where technically applicable.
15. No secrets appear in receipts/telemetry/provider identity.
16. Decision Fabric does not introduce a mandatory cloud dependency.

## Release evidence
Final 1.1.0 evidence bundle must include:
- base/head SHA;
- changed files;
- architecture decisions;
- migrations;
- unit/integration/E2E results;
- lint/typecheck/build;
- security/project-isolation tests;
- shadow benchmark;
- token/cost/latency benchmark;
- cache/fingerprint benchmark;
- upgrade/rollback evidence;
- provider failure evidence;
- known risks;
- diff;
- proposed checkpoint delta.

## Stop condition
1.1.0 is not releasable until shadow evidence demonstrates that enabling the control path is compatible with accepted quality/safety thresholds and all release gates are green.
