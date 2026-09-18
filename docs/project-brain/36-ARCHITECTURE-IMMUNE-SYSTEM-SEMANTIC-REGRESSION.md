# HIVE V2 — Architecture Immune System & Semantic Regression

## Status
PLANNING CANDIDATE. Reconciles AIS, Living Specification Graph, Semantic Regression Engine and architecture-fitness research from prior V2 generations.

## Objective
Detect architectural drift and behavioral contract regression as early deterministic evidence, before expensive review or LLM reasoning, without freezing legitimate evolution.

## AIS-01 — Architecture Contract Registry
Versioned contracts describe allowed:
- module/layer dependencies;
- database ownership;
- API/schema ownership;
- persistence authority;
- event producers/consumers;
- tool/network boundaries;
- canonical/derived state;
- provider adapters;
- forbidden dependency directions.

Contracts are executable where deterministic validation is possible.

## AIS-02 — Fitness Functions
Run deterministic architecture checks on exact Git basis:
- forbidden imports/dependencies;
- cycles where prohibited;
- direct persistence bypass;
- Redis used as canonical truth;
- unauthorized filesystem/network access;
- duplicate event/policy/cache cores;
- API/schema incompatibility;
- MCP boundary violations.

## AIS-03 — Living Specification Graph
Connect requirements → architecture decisions → contracts → modules/symbols → tests/evidence → release/DoD.

Edges carry provenance and validity. Missing links are UNKNOWN, not fabricated.

## AIS-04 — Architecture Drift
Classify change as:
COMPLIANT, INTENTIONAL_EVOLUTION_PENDING_ADR, VIOLATION, UNKNOWN_COVERAGE.

An intended architecture change requires governance rather than weakening the checker.

## AIS-05 — Semantic Regression Engine
Compare old/new behavior using a hierarchy:
1. exact schema/API/contracts;
2. invariants/fixtures/golden outputs;
3. structured event/state behavior;
4. Test Intelligence results;
5. bounded semantic inference only as derived evidence.

LLM output cannot independently approve compatibility.

## AIS-06 — Compatibility Diff
Generate machine-readable changes to:
- public/internal contracts;
- event vocabulary;
- durable schemas;
- config;
- tool capabilities;
- migration/rollback;
- architecture dependencies.

## AIS-07 — Architecture Immune Response
On violation:
- block affected promotion when policy says mandatory;
- produce smallest causal evidence;
- map impacted contracts/tests;
- suggest correction candidates only in staged scope;
- never auto-edit governance to make code pass.

## AIS-08 — Cognitive CI
Compose deterministic architecture, Test Intelligence, security, evidence and benchmark gates into a risk-adaptive CI plan. Required gates remain mandatory.

## AIS-09 — Architecture Evidence
Each check binds exact source commit, contract version, checker version, result and evidence hash.

## AIS-10 — Control Center
Expose architecture drift, contract coverage, dependency violations, semantic regression candidates and evidence freshness.

## HIVE-original extensions
### Architecture Antibodies
Small deterministic rules generated from approved ADR/contracts and versioned as executable guards. Generated candidates require review before becoming authority.

### Drift Half-Life
Unresolved intentional-evolution markers expire into blocking debt rather than remaining permanent bypasses.

### Contract Blast-Radius Proof
Use HUE to show which modules/tests/releases depend on a changed contract before promotion.

### Semantic Regression Quarantine
Ambiguous semantic changes are quarantined for stronger verification instead of being labeled pass/fail from weak inference.

## Gates
- governance checker self-bypass = 0;
- known forbidden dependency accepted = 0;
- architecture contract changed without explicit provenance = 0;
- semantic-only inference independently approves breaking compatibility = 0;
- cross-project graph leakage = 0.

## Stop condition
AIS is ready when architecture intent is executable enough to detect representative violations, legitimate evolution has an explicit ADR path, and semantic regression evidence is integrated with Test Intelligence rather than acting as an unsupervised reviewer.
