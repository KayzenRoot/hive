# HIVE 1.6.0 — Temporal Memory & Verified Engineering Learning

## Status
PLANNING CANDIDATE. Extends the existing PostgreSQL project-scoped memory lifecycle/provenance foundation. Redis remains HOT/noncanonical. Model/executor output remains staged/noncanonical by default.

## Objective
Make HIVE memory temporally correct, contradiction-aware and safely learn from verified engineering outcomes without allowing derived learning to overwrite canonical project truth.

## Existing foundation verified
- durable project-scoped memory in PostgreSQL;
- memory classes/lifecycle/provenance/history;
- qualified canonical promotion boundary;
- staged model/executor output noncanonical by default;
- restart and Redis-loss durability;
- MCP exposes memory provenance/status read-only.

## MEM-01 — Temporal Memory Contract
Every durable memory can express:
- valid_from;
- valid_to when known;
- observed_at;
- recorded_at;
- source revision/basis;
- lifecycle status;
- supersedes/superseded_by;
- provenance;
- authority/validity.

Do not equate newest record with most authoritative truth.

## MEM-02 — Temporal Query Semantics
Support bounded questions:
- current memory;
- memory valid at time/revision;
- history;
- superseded facts;
- contradictory candidates;
- provenance lineage.

Default current query excludes invalid/quarantined material unless explicitly requested for audit.

## MEM-03 — Contradiction Detection
Deterministic contradiction rules first for structured memory classes.

Semantic/LLM contradiction detection, if used, remains derived candidate evidence requiring validation.

Contradictions do not silently delete either source.

## MEM-04 — Supersession
Promotion of a newer valid fact:
- records explicit relation;
- preserves history;
- invalidates affected derived cache/index;
- never rewrites provenance;
- is project scoped.

## MEM-05 — Quarantine / Poisoning Containment
Memory may be quarantined for:
- untrusted source;
- failed verification;
- contradiction requiring review;
- source disappearance/invalidation;
- suspected injection/poisoning;
- schema incompatibility.

Quarantined memory cannot silently feed normal context/learning.

## MEM-06 — Memory Compaction
Compact repeated history without losing canonical facts/provenance.

Allowed:
- content-addressed dedup;
- lossless structural compression;
- derived summaries referencing canonical source.

Not allowed:
- summary replacing canonical source;
- destructive deletion solely for token savings.

## VEL-01 — Verified Engineering Learning
Learning input must originate from verified engineering outcomes, not raw conversation/model claims.

Candidate inputs:
- accepted test outcomes;
- exact-head review evidence;
- approved release evidence;
- validated benchmark results;
- verified failure/fix pairs;
- recovery outcomes.

## VEL-02 — Learning Candidate
A candidate contains:
- hypothesis/pattern;
- supporting evidence identities;
- applicability scope;
- confidence/coverage;
- counterevidence;
- source projects if cross-project transfer is allowed;
- expiry/revalidation trigger.

Candidate learning is derived and noncanonical.

## VEL-03 — Promotion Ladder
States:
OBSERVED → CANDIDATE → VERIFIED_LOCAL → VERIFIED_REUSABLE → DEPRECATED/REJECTED.

Promotion requires objective evidence appropriate to the learning type. No model self-promotion.

## VEL-04 — HCELB
HIVE Continuous Engineering Learning Benchmark.

Measure whether learned guidance improves:
- task success/correctness;
- defects/regressions;
- verification time;
- token/context use;
- tool/provider calls;
- recovery;
- false/generalized advice rate.

Compare learning-enabled vs learning-disabled controlled workloads.

## VEL-05 — Counterevidence
Learning must retain evidence that contradicts or limits a pattern.

A rule with repeated counterevidence is downgraded, narrowed or quarantined rather than endlessly reinforced.

## VEL-06 — Applicability Fingerprint
Before reuse, compare:
- project/domain;
- language/framework;
- architecture;
- task kind;
- relevant policy;
- dependency/version;
- evidence age.

Avoid transferring a successful pattern into an incompatible project merely because text is similar.

## VEL-07 — Organizational Transfer Boundary
Cross-project reusable learning is IMPORTANT/experimental unless explicit policy permits it.

Requirements:
- no project-secret/content leakage;
- abstracted evidence where possible;
- provenance retained;
- opt-in policy if canonical source boundaries require it;
- project-specific truth never becomes global truth.

## VEL-08 — Learning Injection into Context
C³ receives compact verified learning candidates only when applicable.

Ordering:
canonical/current project truth > verified project evidence > applicable verified learning > speculative candidates.

Learning cannot override checkpoint/scope/architecture.

## VEL-09 — Decision/Orchestration Integration
Decision Fabric may use verified learning as evidence.
Orchestration may use it to suggest:
- likely verification paths;
- known failure patterns;
- recovery strategy candidates;
- context/retrieval hints.

All remain bounded by current policy/evidence.

## MEM/VEL-10 — Telemetry & Control Center
Expose:
- memory lifecycle/status;
- contradictions;
- quarantines;
- supersession;
- learning candidates by state;
- reuse events;
- applicability rejections;
- counterevidence;
- HCELB results;
- estimated token/time savings;
- false-learning incidents.

## HIVE-original candidates
### Temporal Truth Window
Resolve memory using both validity interval and source revision, preventing "latest timestamp wins" errors.

### Contradiction Budget
Repeated unresolved contradictions increase retrieval/review priority rather than being buried by more memories.

### Learning Half-Life
Reusable learning decays in confidence/applicability when dependencies, policies or architecture drift, forcing revalidation.

### Counterfactual Replay
For selected verified historical tasks, replay planning with/without a learning candidate to estimate whether it would have helped before broad promotion.

### Learning Firewall
A deterministic boundary prevents learned/semantic material from altering canonical governance, secrets policy or project authority.

### Minimal Experience Capsule
Store a compact pattern + proof references instead of full conversational traces, reducing token/storage while retaining auditability.

## Work orders
- WO-1.6-01 temporal schema/query semantics
- WO-1.6-02 contradiction/supersession/quarantine
- WO-1.6-03 compaction/invalidation
- WO-1.6-04 learning candidate/provenance
- WO-1.6-05 promotion/counterevidence/applicability
- WO-1.6-06 C³/Decision/Orchestration integration
- WO-1.6-07 HCELB harness
- WO-1.6-08 learning shadow/replay
- WO-1.6-09 telemetry + Control Center
- WO-1.6-10 migration/security/release hardening

## Absolute gates
- canonical governance overwritten by learning = 0;
- quarantined memory used as normal current truth = 0;
- cross-project secret/content leakage = 0;
- provenance loss on supersession = 0;
- model self-promotion = 0;
- HCELB must report negative/no benefit honestly;
- Redis loss must not lose canonical memory.

## Release condition
Verified Learning may ship partially shadow-only if its control/reuse path has not proven benefit. Temporal memory correctness is not contingent on learning showing positive benefit.

## Stop condition
1.6.0 is releasable when temporal memory is correct/auditable and any enabled learning path demonstrates bounded verified benefit without becoming a competing source of canonical truth.
