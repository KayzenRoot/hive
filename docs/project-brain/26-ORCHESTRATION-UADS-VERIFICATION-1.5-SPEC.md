# HIVE 1.5.0 — Governed Orchestration, Policy, UADS & Verification

## Status
PLANNING CANDIDATE. Extends the existing v1.0 ExecutionOrchestrator, ExecutorAdapter, Local Verified Runner, ToolPolicy, staged/noncanonical ChangeSet behavior and Review Evidence schema. It must not duplicate those seams.

## Objective
Evolve HIVE from a bounded execution foundation into durable, recoverable, policy-governed engineering orchestration with explicit proof obligations and UADS-compatible evidence, while preserving staged execution and human/canonical governance boundaries.

## Existing seams verified
- `ExecutionOrchestrator` coordinates project/task identity, checkpoint-first context, provider-independent `ExecutorAdapter` and Runner;
- `runner.py::ToolPolicy` is fail-closed;
- current orchestrator deliberately has no Git promotion and no durable execution-run store;
- Review Evidence is versioned and validation-gated;
- generated Module Registry/Test Map already describes Runner verification/evidence;
- UADS evidence lineage already exists in project history.

## ORC-01 — Durable Run Model
Versioned durable identities:
- task;
- run;
- attempt;
- step;
- evidence bundle;
- executor/provider profile.

Candidate run states:
QUEUED, PLANNING, READY, EXECUTING, VERIFYING, REVIEW_REQUIRED, BLOCKED, SUCCEEDED_STAGED, FAILED, CANCELLED, RECOVERING.

Durable state belongs in PostgreSQL. Redis may accelerate but never define run truth.

## ORC-02 — Attempt Isolation
A retry is a new attempt bound to:
- exact task;
- exact repository/head basis;
- context fingerprint;
- policy version;
- executor profile;
- prior-attempt lineage.

A retry cannot silently inherit stale success claims.

## ORC-03 — Step Contract
Bounded step kinds:
- inspect;
- deterministic analysis;
- context/retrieval;
- executor invocation;
- staged mutation;
- test/validation;
- evidence collection;
- review gate.

Avoid an unrestricted arbitrary workflow language in 1.5.

## ORC-04 — Capability Envelope
Every run/step receives least-authority capabilities:
- project/path scope;
- executable/tool allowlist;
- network policy;
- secret access policy;
- resource/time bounds;
- mutation class;
- expiry/revocation.

Capabilities are explicit data and fail closed.

## ORC-05 — Policy Composition
Compose existing ToolPolicy with:
- security boundary;
- project policy;
- release/work-order policy;
- capability envelope;
- governance authority;
- Decision Fabric outcome where allowed.

Decision Fabric may escalate but cannot override a deterministic denial.

## ORC-06 — HAZF Boundary
Simplified hardened execution zone:
- normalized path checks;
- no cross-project filesystem access;
- explicit subprocess environment;
- bounded stdout/stderr;
- network default-deny unless capability allows;
- secret minimization/redaction;
- no shell bypass;
- no canonical Project Brain mutation from executor;
- no Git promotion from executor.

## ORC-07 — UADS Contract
Map HIVE task/run/attempt/evidence into compact UADS-compatible software-quality evidence.

Required:
- work-order identity;
- scope/acceptance criteria;
- files changed;
- tests/validation;
- defects fixed;
- residual risks;
- diff/head basis;
- checkpoint proposal;
- proof validity.

UADS integration is evidence/quality coordination, not a second canonical persistence engine.

## ORC-08 — Proof Obligations
Before a run can claim staged success, applicable obligations are known.

Candidate profiles:
- CODE_CHANGE;
- DOCS_GOVERNANCE;
- MIGRATION;
- SECURITY_SENSITIVE;
- RELEASE;
- BENCHMARK.

Each profile defines required evidence classes, not hard-coded provider prose.

## ORC-09 — Verification Claim Model
Claims are typed:
- TEST_PASS;
- BUILD_PASS;
- TYPECHECK_PASS;
- LINT_PASS;
- SECURITY_PASS;
- MIGRATION_PASS;
- BENCHMARK_RESULT;
- FILE_CHANGED;
- REQUIREMENT_SATISFIED.

Every claim binds evidence, exact basis and validity. Unsupported claims are UNKNOWN/UNVERIFIED.

## ORC-10 — Evidence Validity Fingerprint
Fingerprint proof compatibility from:
- exact source/head;
- relevant files/impact cone;
- test/tool version;
- policy/config;
- environment/profile;
- evidence artifact hash.

Allows safe evidence carry-forward research with HUE 1.3, but starts in shadow mode against required full verification.

## ORC-11 — Verification Planner
Use deterministic/HUE evidence to select focused verification during iteration.

Canonical release/security/migration gates remain policy-controlled. Uncertain impact expands verification rather than shrinking it.

## ORC-12 — Failure Taxonomy
Classify:
- POLICY_DENIED;
- EXECUTOR_FAILED;
- PROVIDER_UNAVAILABLE;
- TOOL_FAILED;
- VALIDATION_FAILED;
- STALE_BASIS;
- EVIDENCE_INCOMPLETE;
- RESOURCE_LIMIT;
- RECOVERY_REQUIRED;
- INTERNAL_ERROR.

No generic "failed" when a bounded reason is knowable.

## ORC-13 — Recovery
On restart/interruption:
- detect incomplete run/attempt;
- inspect staged state;
- revalidate exact basis;
- resume only idempotent/safe steps;
- otherwise create a recovery attempt or block;
- never infer success from partial evidence.

## ORC-14 — Provider-Unavailable Mode
HIVE remains useful without executor/LLM provider:
- deterministic inspection;
- project/status/checkpoint;
- HUE/retrieval/context where local seams permit;
- validation/review evidence;
- queued/blocked state visible.

Provider outage cannot corrupt canonical state.

## ORC-15 — MCP/IDE Integration
Expose only bounded orchestration surfaces approved for 1.5.

Read-only MCP baseline remains intact until write/execute surfaces have explicit capability, auth/policy, evidence and revocation contracts.

## ORC-16 — Telemetry & Control Center
Expose:
- task/run/attempt/step states;
- active capability envelope summary;
- blocked reason;
- executor/provider profile;
- verification obligations;
- evidence validity;
- retries/recovery;
- token/context/tool/resource metrics;
- recent policy denials;
- staged vs canonical distinction.

## ORC-17 — Benchmark
Measure:
- task completion correctness;
- recovery success;
- stale-basis rejection;
- focused verification savings;
- evidence carry-forward validity;
- provider-unavailable behavior;
- orchestration overhead;
- tokens/context/tool calls;
- false success claims;
- project isolation.

## HIVE-original candidates
### Proof-Carrying Run
A run cannot move to a stronger state unless it carries the exact evidence required for that state transition.

### Capability Lease
Execution authority is a short-lived, project-scoped lease with deterministic expiry/revocation, reducing ambient authority.

### Verification Gradient
During iteration HIVE uses the cheapest sufficient proof set, then progressively strengthens proof as the run approaches release/canonical gates.

### Recovery Capsule
Persist a compact deterministic recovery descriptor, not executor conversational history, so interrupted work can be reconstructed with minimal context.

### Evidence Carry-Forward Shadow
Use HUE impact + validity fingerprints to predict reusable proofs, compare against full validation, and promote only after measured zero-critical-invalid-reuse thresholds.

## Work orders
- WO-1.5-01 durable run/attempt schema
- WO-1.5-02 step/capability contracts
- WO-1.5-03 policy/HAZF composition
- WO-1.5-04 UADS + proof obligations
- WO-1.5-05 verification claims/evidence fingerprints
- WO-1.5-06 verification planner + HUE integration
- WO-1.5-07 interruption/recovery
- WO-1.5-08 provider-unavailable + MCP/IDE bounded integration
- WO-1.5-09 telemetry + Control Center
- WO-1.5-10 shadow evidence carry-forward benchmark
- WO-1.5-11 migration/security/release hardening

## Absolute gates
- false staged success with missing required proof = 0;
- executor canonical promotion = 0;
- hard-policy bypass = 0;
- cross-project access = 0;
- stale-basis mutation acceptance = 0;
- secret leakage = 0;
- recovery cannot invent completed steps;
- provider outage cannot corrupt canonical state.

## Stop condition
1.5.0 is releasable only when durable orchestration can be interrupted, recovered, audited and verified without weakening existing ToolPolicy, staged-output or canonical governance boundaries.
