# HIVE 1.1.0 — Pre-Codex Implementation Map

## Purpose
Minimize executor discovery/reasoning work without prescribing repository changes that have not been inspected at implementation time.

## Executor source order
Before changing code:
1. latest `13-CHECKPOINT.md`;
2. `16-DECISIONS-LEDGER.md`;
3. `03-SCOPE.md`;
4. `15-DEFINITION-OF-DONE.md`;
5. `04-ARCHITECTURE.md`;
6. `02-REQUIREMENTS.md`;
7. `17-POST-1.0-EVOLUTION-ROADMAP.md`;
8. `18-V2-INCREMENTAL-RELEASE-MAP.md`;
9. `19-DECISION-FABRIC-1.1-SPEC.md`;
10. repository code/tests/module registry/migrations/dashboard.

If planning documents are not canonical yet, stop rather than treating candidates as approved implementation authority.

## Proposed work-order decomposition

### WO-1.1-01 — Contract + deterministic prefilter
Deliver:
- typed/versioned decision contract;
- candidate validation;
- deterministic prefilter;
- fail-closed malformed inputs;
- focused unit tests;
- no provider dependency.

STOP when deterministic fixtures pass and no probabilistic provider exists in the control path.

### WO-1.1-02 — Context projector + fingerprints
Deliver:
- bounded project-scoped decision context;
- stable serialization;
- input fingerprint;
- validity-sensitive invalidation inputs;
- focused tests.

STOP when material changes alter fingerprint and equivalent inputs reproduce identity.

### WO-1.1-03 — Provider adapter + fixture provider
Deliver:
- provider-independent interface;
- deterministic test provider;
- strict output validation;
- provider failure classification;
- no mandatory cloud provider.

STOP when malformed/missing/duplicate/non-finite outputs fail closed.

### WO-1.1-04 — Escalation policy
Deliver:
- AUTO/REVIEW/ESCALATE contract;
- hard policy precedence;
- evidence-weighted escalation;
- initial auditable Escalation Economics policy;
- risk/reversibility inputs;
- tests.

STOP when high confidence cannot override hard policy and weak evidence can force escalation.

### WO-1.1-05 — Cache + Decision Delta
Deliver:
- Redis HOT decision cache;
- deterministic compatibility predicate;
- invalidation;
- Decision Delta reuse;
- transient failure exclusion;
- false-hit benchmark.

STOP at zero false hits in accepted fixtures.

### WO-1.1-06 — Shadow Mode
Deliver:
- shadow-only execution path;
- baseline-vs-shadow comparison receipt;
- no control/canonical mutation;
- disagreement capture;
- focused integration tests.

STOP when shadow output is proven unable to change baseline execution behavior.

### WO-1.1-07 — Optional Jev adapter
Only execute if research/licensing/API stability and repository architecture still support it.

Deliver:
- optional adapter behind DecisionProvider;
- explicit configuration;
- graceful absence/failure;
- no Jev types in core domain;
- provider-specific tests/mocks.

STOP if Jev requires architecture coupling, mandatory cloud behavior, unacceptable licensing, or weak reproducibility. In that case record BLOCKED/NOT PROMOTED and preserve generic provider seam.

### WO-1.1-08 — Batch decisions + Confidence Debt
Deliver:
- bounded homogeneous batching;
- per-item identity/provenance;
- confidence debt state/rules if benchmark evidence supports promotion;
- tests.

Confidence Debt remains experimental until its state/lifecycle value is demonstrated.

### WO-1.1-09 — Telemetry + Control Center
Deliver:
- structured decision events;
- metrics;
- project-scoped traces;
- dashboard decision view/panels;
- estimate labels;
- no fake cost/token data;
- frontend tests.

### WO-1.1-10 — Benchmark + production-shadow validation
Deliver:
- baseline 1.0 comparison;
- correctness;
- critical misses/false AUTO;
- tokens/context/provider calls;
- latency/cost where measurable;
- cache/delta;
- shadow agreement;
- reproducibility.

This Work Order determines whether control-path promotion is justified.

### WO-1.1-11 — Control-path promotion
CONDITIONAL. Execute only after Sol audit approves WO-1.1-10 evidence.

Deliver:
- narrowly approved decision kinds switched from shadow to control;
- fallback/escalation;
- security regression;
- E2E proof.

No blanket global AUTO enablement.

### WO-1.1-12 — Release hardening
Deliver:
- upgrade from 1.0.0;
- rollback documentation/proof;
- full regression;
- security;
- docs;
- release metadata;
- final evidence.

STOP before merge/release for Sol exact-head audit.

## Test matrix prepared in advance

| Area | Minimum proof |
|---|---|
| contract | schema/version/candidate invariants |
| deterministic | zero provider/LLM calls |
| isolation | no cross-project decision/evidence/cache access |
| provider | malformed/timeout/unavailable fail safely |
| policy | hard constraints outrank confidence/cost |
| evidence | stale/weak evidence escalates where required |
| cache | zero accepted false hits |
| delta | incompatible material change forces full evaluation |
| shadow | cannot alter authoritative behavior |
| batch | no item swap/drop/cross-project mixing |
| security | no secret/path leakage; sensitive boundary intact |
| telemetry | real project-scoped events/metrics |
| benchmark | savings + quality reported together |
| upgrade | 1.0.0 persistent state preserved |
| rollback | constraints explicit and verified where possible |

## Executor token-economy rules
- inspect targeted seams before broad repository reading;
- use deterministic repository search/AST/Git before LLM reasoning;
- do not reread unchanged large governance documents after establishing exact hashes unless needed;
- keep stable prompt/work-order prefixes;
- report only material evidence;
- avoid generated prose files not required by canonical docs/tests;
- reuse existing services/contracts rather than parallel implementations;
- run focused tests during iteration, full required gates at completion.

## Stop condition
This map prepares execution but does not authorize WO-1.1-01 until planning is promoted into canonical governance.
