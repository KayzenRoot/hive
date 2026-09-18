# HIVE 1.4.0 — C³ Context Intelligence Specification

## Status
PLANNING CANDIDATE. Builds on the existing v1.0 Context Manager, adaptive token budget, fingerprints, delta context, provider prompt cache, progressive disclosure and retrieval stack. HUE 1.3 enriches inputs but is not allowed to replace canonical source.

## Objective
Make context construction an explicit, auditable compile pipeline that maximizes task-relevant signal per token while preserving required governance, security, correctness and provenance.

## C3-01 — Context Request Contract
Versioned task-context request:
- project/task/run;
- objective/task kind;
- risk class;
- required authority classes;
- known exact Git/checkpoint basis;
- budget envelope;
- allowed retrieval/tool surfaces;
- provider/model profile when relevant;
- requested output contract.

## C3-02 — Context Planner
Deterministically plan context sources before fetching large content.

Plan may include:
- governance/checkpoint;
- exact Git delta;
- HUE impact/symbol evidence;
- retrieval candidates;
- memory;
- test/review evidence;
- external/tool results;
- progressive disclosure level.

Planner must explain why each source family is requested or omitted.

## C3-03 — Context Compiler
Compile authorized evidence into a stable context capsule.

Pipeline:
```text
request
 -> authority/required-source admission
 -> deterministic/HUE retrieval
 -> hybrid retrieval
 -> validity/provenance filter
 -> dedup
 -> relevance/value scoring
 -> progressive disclosure
 -> budget allocation
 -> stable ordering/prefix
 -> fingerprint
 -> capsule + omission manifest
```

## C3-04 — C³ Capsule Contract
Capsule sections are typed rather than a single prose blob.

Candidate sections:
- invariant/governance prefix;
- task delta;
- repository intelligence;
- retrieved evidence;
- memory;
- tests/review evidence;
- tool/external evidence;
- explicit unknowns;
- omitted/deferred references.

Each item retains identity/provenance/validity.

## C3-05 — Context Value Accounting
Measure each admitted context item's approximate value/cost:
- relevance;
- authority/necessity;
- freshness;
- uniqueness;
- estimated token cost;
- downstream utility proxy;
- risk of omission.

Cost alone cannot evict mandatory governance/security evidence.

## C3-06 — Signal Ratio
Define auditable metrics:
- required-signal retention;
- duplicate/redundant context;
- sent vs retrieved;
- deferred vs expanded;
- useful evidence referenced by final proof where measurable;
- context bytes/tokens per successful task.

Avoid claiming semantic "signal" from an unvalidated model score alone.

## C3-07 — Progressive Disclosure 2
Extend existing levels:
- L0 identity/metadata;
- L1 module/object summary;
- L2 symbol/signature/dependency;
- L3 relevant excerpts;
- L4 full artifact only when justified.

Tool schemas/results follow the same disclosure principle where technically possible.

## C3-08 — Context Delta 2
Reuse prior compatible capsule structure:
- unchanged stable prefix;
- changed task/Git/evidence delta;
- invalidated sections rebuilt;
- exact compatibility fingerprint;
- deterministic fallback to full compile.

No stale delta reuse.

## C3-09 — Stable Prefix / Provider Cache Optimization
Separate:
- stable project/governance prefix;
- semi-stable task family material;
- volatile delta.

Provider-specific cache hints stay behind adapters. HIVE semantics cannot depend on a provider cache being available.

## C3-10 — Retrieval Escalation Ladder
Start cheap and deterministic:
1. exact identity/Git/HUE;
2. lexical/structured retrieval;
3. vector/hybrid;
4. rerank;
5. broader/deeper retrieval;
6. optional expensive reasoning/tool path.

Escalate only when sufficiency/coverage requires it.

## C3-11 — Sufficiency Contract
Context compiler reports:
- SUFFICIENT;
- PARTIAL;
- BLOCKED_MISSING_AUTHORITY;
- BLOCKED_STALE_EVIDENCE;
- UNKNOWN_COVERAGE.

Decision Fabric may assist bounded escalation, but cannot label missing mandatory evidence sufficient.

## C3-12 — Omission Manifest
Every deliberate omission/deferment can be audited:
- identity/reference;
- reason;
- estimated size;
- disclosure level available;
- trigger for expansion.

This allows aggressive compression without invisible information loss.

## C3-13 — Context Safety
- project isolation;
- secret/path redaction policies;
- prompt/tool-result provenance;
- untrusted external content marked;
- no derived summary may silently replace canonical source where exact source is required;
- injection-sensitive external instructions remain data, not authority.

## C3-14 — Telemetry & Control Center
Metrics:
- retrieved/sent tokens/bytes;
- context reduction;
- required retention;
- fingerprint/delta hits;
- provider cache eligibility/hits where known;
- disclosure expansion;
- omission reasons;
- retrieval escalation depth;
- compilation latency;
- UNKNOWN/PARTIAL rate;
- task outcome correlation.

## C3-15 — Benchmark Harness
Compare against v1.0 Context Manager and previous stable:
- task outcome/correctness;
- critical-context misses;
- required-item retention;
- retrieval recall/precision/MRR where applicable;
- fresh/cached/output tokens;
- retrieved/sent context;
- latency;
- provider calls;
- cache/delta hit rate;
- reproducibility;
- context signal ratio proxies.

## HIVE-original research candidates

### Context Futures
Instead of fetching all plausible evidence immediately, compiler emits cheap deferred references that can be expanded on demand. Similar to lazy evaluation for context.

### Proof-Budget Coupling
Allocate more context budget to evidence needed to satisfy proof obligations, not merely to high semantic similarity.

### Context Entropy Guard
Detect near-duplicate/redundant evidence families before sending them, using deterministic hashes/structure first and semantic similarity only as secondary derived evidence.

### Context Value Ledger
Persist bounded aggregate evidence about which context classes contributed to successful verified tasks, without treating correlation as causal truth. Feeds future planning/learning only after validation.

### Adaptive Disclosure Frontier
Choose the shallowest disclosure level that satisfies current evidence needs; expand only specific branches rather than globally increasing context.

## Proposed work orders
- WO-1.4-01 request/planner contracts
- WO-1.4-02 compiler/capsule/omission manifest
- WO-1.4-03 HUE + retrieval admission
- WO-1.4-04 context value + budget integration
- WO-1.4-05 progressive disclosure 2
- WO-1.4-06 delta 2 + stable prefix/cache
- WO-1.4-07 sufficiency/escalation
- WO-1.4-08 safety/provenance hardening
- WO-1.4-09 telemetry + Control Center
- WO-1.4-10 benchmark + release hardening

## Acceptance criteria
1. Required governance/security evidence cannot be budget-evicted.
2. Every sent item has project/provenance semantics.
3. Omitted/deferred material is auditable.
4. Equivalent inputs produce deterministic semantic fingerprint where declared.
5. stale/incompatible delta falls back safely.
6. provider cache absence does not break HIVE.
7. no cross-project context leak.
8. critical-context misses do not regress beyond frozen threshold.
9. savings and quality are reported together.
10. full existing regression remains green.
11. upgrade preserves canonical user state.

## Release gate
1.4.0 requires measurable context/token efficiency improvement on at least one representative workload without violating correctness, critical-context, authority, security or project-isolation gates.

## Stop condition
1.4.0 is releasable only when HIVE can explain what context it retrieved, what it sent, what it deferred, why, how much it cost, and whether the resulting context was sufficient.
