# HIVE 1.1.0 — Integration Contracts and Benchmark Gates

## Status
PLANNING CANDIDATE. Refines `19-DECISION-FABRIC-1.1-SPEC.md` against the actual v1.0.0 repository seams.

## Existing seams verified on v1.0.0
Decision Fabric should extend, not duplicate:
- `backend/app/context_fingerprints.py` for SHA-256/versioned fingerprint patterns and bounded Redis HOT cache semantics;
- `backend/app/delta_context.py` for compatible derived-delta patterns;
- `backend/app/provider_prompt_cache.py` for provider-independent semantic source/profile patterns;
- `backend/app/telemetry.py` and migration `0007_telemetry_events.py` for canonical project-scoped durable events;
- `dashboard/src/eventVocabulary.ts` for the frontend mirror of canonical event vocabulary;
- `backend/app/runner.py::ToolPolicy` for deterministic fail-closed executable/tool authority;
- `backend/app/execution_orchestrator.py` for staged execution boundaries;
- `scripts/context_manager_integration.py` and `docs/atlas/WO-023-BENCHMARK-REPORT.md` for benchmark/economy methodology;
- deterministic Atlas/Module Registry/Test Map generation.

No implementation should create a second event bus, second generic cache framework, second tool-policy authority or parallel context engine without an approved ADR.

## Contract family

### decision-contract-v1
Semantic input:
- project identity;
- decision kind;
- bounded candidates;
- material evidence identities/validity;
- policy version;
- risk/reversibility class;
- decision context fingerprint;
- provider profile if invoked.

Semantic output:
- outcome AUTO/REVIEW/ESCALATE;
- selected candidate(s) where applicable;
- score/distribution where applicable;
- evidence strength;
- escalation reasons;
- receipt identity.

### decision-input-v1
Stable serialization requirements:
- deterministic key order;
- no timestamps/non-semantic trace IDs in semantic hash;
- explicit schema/policy versions;
- no secrets;
- project identity mandatory;
- candidate order semantics explicitly declared by decision kind.

### decision-fingerprint-v1
Algorithm: SHA-256 unless a later ADR changes the project-wide hashing policy.

Must change when any material input changes:
- candidate set/semantics;
- policy;
- evidence identity/validity;
- risk class;
- provider semantic profile;
- projected decision context.

Must remain stable for semantically identical rebuilds.

### decision-receipt-v1
Audit payload:
- semantic input fingerprint;
- path: deterministic/provider/cache/delta;
- policy outcome;
- provider identity/profile without credentials;
- evidence references;
- confidence/distribution if applicable;
- estimation provenance;
- timings;
- shadow/baseline comparison identity when applicable.

A receipt is evidence, not canonical authorization.

## Event vocabulary proposal
Extend the existing canonical Telemetry/Event Bus only after implementation review.

Candidate events:
- `decision.started`
- `decision.prefiltered`
- `decision.provider_called`
- `decision.cache_hit`
- `decision.cache_miss`
- `decision.delta_reused`
- `decision.auto`
- `decision.review`
- `decision.escalated`
- `decision.shadow_compared`
- `decision.failed`

Rules:
- project scoped;
- bounded payload;
- no secrets/raw large context;
- event vocabulary backend/frontend drift remains deterministically tested;
- unknown values remain UNKNOWN/UNAVAILABLE, never invented zero.

## Authority precedence
Highest to lowest:
1. hard security / project isolation / canonical governance;
2. deterministic ToolPolicy and explicit capability constraints;
3. authoritative validity/provenance evidence;
4. Decision Fabric escalation policy;
5. provider confidence/distribution;
6. economic optimization.

Lower layers can force escalation upward but cannot override higher-layer denial.

## Shadow-mode comparison contract
For every eligible shadow fixture capture:
- baseline action/outcome;
- shadow decision;
- agreement class;
- whether shadow would have changed behavior;
- evidence strength;
- baseline context/token estimate;
- shadow context/token estimate;
- baseline generative/provider calls;
- shadow decision-provider calls;
- latency;
- failure/fallback;
- criticality.

Shadow output has no mutation authority.

## Benchmark gates

### Gate A — Safety
Required:
- critical false AUTO = 0;
- cross-project leakage = 0;
- hard-policy overrides by provider = 0;
- secret leakage = 0;
- malformed-provider accepted outputs = 0;
- shadow mutations = 0.

Any nonzero result blocks control-path promotion.

### Gate B — Correctness
Before benchmark fixtures are frozen, establish labelled expected outcomes from deterministic truth or explicitly approved fixture truth.

Required:
- no regression on existing v1.0 accepted tests/benchmarks;
- Decision Fabric decision accuracy must meet the frozen fixture threshold;
- every disagreement in HIGH/CRITICAL fixture classes must be individually auditable.

No universal percentage is invented before representative fixtures exist.

### Gate C — Economy
Report, do not hide:
- fresh input tokens;
- cached tokens when provider exposes them;
- output tokens;
- context bytes and estimated context tokens;
- decision-provider calls;
- generative calls avoided;
- wall-clock latency;
- provider cost where available;
- estimated avoided cost with provenance.

Promotion requires a positive economy result on at least one representative workload without violating Gates A/B. A claimed saving without quality evidence is invalid.

### Gate D — Cache / Delta
Required:
- false decision cache hits = 0;
- incompatible delta reuse = 0;
- Redis-loss rebuild succeeds;
- policy/evidence/profile changes invalidate affected entries;
- transient provider/security failures are not cached as success.

### Gate E — Reliability
Required:
- provider unavailable path bounded;
- provider timeout bounded;
- malformed result bounded;
- Redis unavailable/lost path preserves canonical truth;
- API/container restart preserves durable evidence where required;
- repeated equivalent run reproducible within declared deterministic boundaries.

### Gate F — Upgrade
Required:
- clean upgrade from released 1.0.0;
- persistent user-owned data preserved;
- migration head coherent;
- startup gating detects incomplete migration;
- rollback limitations explicit;
- post-upgrade health/integration pass.

## Control-path promotion policy
Do not promote all decision kinds at once.

Each decision kind receives one of:
- SHADOW_ONLY;
- CONTROL_ELIGIBLE_LOW_RISK;
- REVIEW_ONLY;
- DISABLED.

Promotion requires:
1. fixture coverage;
2. Gate A pass;
3. Gate B pass;
4. economy evidence;
5. Sol exact-head audit;
6. explicit governance delta.

## Innovation incubation
The following remain experimental until measured:
- Confidence Debt;
- Decision Delta beyond exact compatibility;
- batch-provider optimization;
- Jev-specific adapter;
- learned/calibrated Escalation Economics weights.

Experimental features should default to disabled or shadow mode and must not be required for local-only HIVE.

## Executor implementation constraints
- inspect existing modules before selecting file paths;
- reuse telemetry/fingerprint/cache/policy patterns;
- migrations only when durable semantics require them;
- avoid generic abstraction frameworks unless two real seams justify them;
- add Atlas/Module Registry/Test Map entries through the existing deterministic generator;
- focused tests first, complete required gates before executor completion.

## Stop condition
This planning artifact is complete when it can be used to freeze WO-1.1-01 through WO-1.1-06 without requiring the executor to invent core contracts, authority precedence or benchmark semantics.
