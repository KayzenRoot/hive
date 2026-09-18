# HIVE 1.1 — DECISION FABRIC PLANNING FREEZE

## Status
FROZEN — IMPLEMENTATION MAY BE SPECIFIED, NOT YET CLAIMED COMPLETE.

## Frozen basis
Stable runtime baseline: HIVE 1.0.0 at a53b5b9fcf55c32a5696180fb1b1ef80ccd1edcf.
Planning branch: planning/post-1.0-roadmap.

Canonical authority remains:
13-CHECKPOINT → 16-DECISIONS-LEDGER → 03-SCOPE → 15-DEFINITION-OF-DONE → 04-ARCHITECTURE → 02-REQUIREMENTS.

This freeze incorporates post-1.0 planning through documents 17–48 plus the adopted shared-convention and coverage-matrix corrections committed immediately before this declaration.

## Closure evidence
PASS — Jev/OpenJev technology audit and non-mandatory disposition.
PASS — Decision Fabric typed architecture and work-order decomposition.
PASS — benchmark/evidence ownership contract.
PASS — v1.0 existing seam/migration map.
PASS — legacy capability reconciliation with no silent drop.
PASS — FTI/FVCR identifier collision resolved:
FTI = Flaky Test Intelligence.
FVCR = Feature Verification Contract Registry.
PASS — Shared Runtime & Evidence Conventions adopted for HIVE 1.x, with explicit 1.1 mandatory subset.
PASS — canonical cross-audit found no approved-decision override or incompatible canonical store.
PASS — HIVE-first executor prompt contract adopted.

## Frozen 1.1 scope
NECESSARY:
typed Decision Contract;
Deterministic Resolver;
bounded Context Projector;
provider-independent DecisionProvider seam;
Calibration Firewall;
Decision Value Router/escalation;
fingerprint/cache/Decision Delta;
Confidence Debt;
Shadow Comparator;
sensitive/hard-policy boundary;
decision telemetry/Control Center integration;
governed benchmark/promotion;
upgrade/rollback evidence.

CONDITIONAL/EXPERIMENTAL:
local direct-logit scorer;
Jev-compatible remote scorer;
shared-state/prefix decision pack;
Change Risk Predictor integration.

OUT OF 1.1:
replacement of HUE/C3/memory;
general Model Router core;
new canonical database;
security delegated to model;
broad 2.0 migration;
distributed/multi-user/cloud/Kubernetes work.

## Frozen invariants
deterministic before LLM;
quality/security before economy;
PostgreSQL/Git/CAS canonical responsibilities preserved;
Redis decision cache derived/reconstructible;
no second event bus/registry/context manager/retrieval engine/provider-prefix cache;
ToolPolicy cannot be bypassed;
provider confidence is not proof;
critical/UNKNOWN risk cannot be lowered by scorer alone;
project isolation is mandatory;
malformed/undeclared decision options fail closed;
provider failure is not success;
promotion is per decision kind and evidence-bound.

## Implementation sequence
WO-1.1-01 Contract Kernel + Deterministic Resolver.
WO-1.1-02 Context Projector + fingerprints.
WO-1.1-03 fixture + structured provider seam.
WO-1.1-04 Calibration Firewall + Decision Value Router.
WO-1.1-05 decision cache + Decision Delta.
WO-1.1-06 Shadow Comparator.
WO-1.1-07 optional scorer adapters, benchmark-gated.
WO-1.1-08 batch/shared-state shadow + Confidence Debt.
WO-1.1-09 telemetry + Control Center.
WO-1.1-10 governed corpus + baseline/candidate benchmark.
WO-1.1-11 controlled low-risk promotion where evidence permits.
WO-1.1-12 release hardening, regression, upgrade/rollback and 1.1 release evidence.

## Executor rule
Every WO uses 47-HIVE-FIRST-EXECUTOR-PROMPT-CONTRACT.md.
The installed 1.0.0 HIVE may be used only through capabilities actually available in that stable release. A WO must not assume the unreleased 1.1 feature it is implementing.

## Change control after freeze
A change to frozen NECESSARY scope, authority precedence, canonical storage, security boundary, provider authority, public compatibility or release gates requires an explicit freeze-delta/ADR and audit before implementation.
Clarifications that do not alter those contracts may be appended with provenance.

## First implementation authorization
Planning is now sufficiently frozen to SPECIFY WO-1.1-01.
This declaration does not itself authorize arbitrary 1.1 implementation. The executor receives only the scope explicitly defined in each WO.

## Stop condition
The next artifact is the self-contained HIVE-first WO-1.1-01 executor prompt. No later WO is generated until WO-1.1-01 is executed, reviewed and APPROVED.
