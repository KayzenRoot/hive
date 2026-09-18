# HIVE V2 — Test Intelligence Expansion

## Status
PLANNING CANDIDATE. Reconciles the later V2 R21 Test Intelligence work into the incremental release train. This document does not silently invent unresolved legacy acronyms.

## Recovered R21 semantics
Recovered from the latest V2 planning history:
- FIM = Feature Impact Map;
- AITS = Adaptive Impact Test Selector;
- PVR = Proof Validity Reuse;
- FTI / Feature Verification Contract Registry = verification contracts by feature.

Additional R21 names PVR, SFC, RUF, RBG, BCR and DGS were recorded in the prior planning, but the exact expansions/semantics of SFC/RUF/RBG/BCR/DGS are not sufficiently recovered yet. They remain LEGACY-UNRESOLVED and cannot be implemented from acronym inference.

## Objective
Make verification feature-aware, impact-aware, risk-adaptive and evidence-reuse-aware while preserving the rule that uncertain coverage expands verification and critical release/security/migration gates remain policy-controlled.

## TI-01 — Feature Verification Contract Registry
A feature/capability can declare:
- owning module/release;
- relevant source/contracts/schemas;
- required unit/integration/E2E/eval/security/migration evidence;
- critical invariants;
- risk class;
- full-suite requirements;
- benchmark obligations;
- invalidation triggers.

This registry complements, not replaces, the deterministic Test Map.

## TI-02 — FIM: Feature Impact Map
Map an exact Git delta to candidate affected features using HUE/EET evidence:
- changed files/symbols;
- dependency/contract impact;
- schema/API/migration impact;
- test/eval ownership;
- documentation/governance impact;
- coverage uncertainty.

FIM output is derived evidence and retains exact Git basis.

## TI-03 — AITS: Adaptive Impact Test Selector
Select the cheapest sufficient verification set for the current iteration.

Inputs:
- FIM;
- feature verification contracts;
- action/change risk;
- evidence freshness;
- prior failures;
- policy-required full gates.

Outputs:
- focused test/eval set;
- mandatory full gates;
- omitted tests with reason;
- uncertainty/escalation state.

No probabilistic selector can suppress a deterministic mandatory gate.

## TI-04 — PVR: Proof Validity Reuse
Reuse prior proof only when compatibility remains valid.

Fingerprint inputs:
- exact relevant source/impact basis;
- test/tool version;
- dependency/config/policy;
- environment profile;
- proof artifact identity;
- feature contract version.

PVR starts SHADOW_ONLY against the non-reuse/full verification baseline.

## TI-05 — Shadow Full-Suite Verification
During calibration, AITS/PVR predictions run alongside the required broader/full suite.

Measure:
- critical missed tests;
- invalid reused proof;
- verification reduction;
- latency;
- resource/token savings;
- false confidence.

Promotion requires frozen thresholds and zero critical-invalid-reuse fixtures.

## TI-06 — Flake Intelligence
Distinguish:
- deterministic failure;
- environment failure;
- timeout/resource failure;
- suspected flake;
- unknown.

Retry policy is bounded. A passing retry does not erase the initial failure evidence.

## TI-07 — Scheduling Intelligence
Order verification to maximize early information:
- deterministic cheap checks;
- high-risk/likely-impact tests;
- parallel-safe groups;
- expensive suites later unless policy requires otherwise.

Scheduling optimizes time, not truth.

## TI-08 — Counterexample Generation
EXPERIMENTAL:
- property/fuzz/model-based candidate tests;
- boundary/negative cases;
- mutation-informed candidate cases.

Generated tests become evidence only after execution and validation.

## TI-09 — Semantic Regression
Compare verified behavioral/contract expectations across a change.

Deterministic sources first:
- API/schema;
- feature contracts;
- golden/fixture outputs;
- invariants;
- structured behavior.

LLM semantic comparison remains derived and cannot independently declare compatibility.

## TI-10 — Real-Use Verification
Representative workflows/resources/replay scenarios complement unit fixtures.

Do not substitute anecdotal production use for reproducible tests.

## TI-11 — Evidence Manifest
Machine-readable per verification run:
- feature/change basis;
- selected tests;
- omitted tests/reasons;
- proof reuse;
- failures/retries;
- result;
- tool/environment;
- evidence hashes;
- validity.

## TI-12 — Control Center
Expose:
- affected features;
- selected/full tests;
- verification contract status;
- PVR reuse/shadow;
- flakes/retries;
- time/resource reduction;
- critical coverage gaps;
- regression locks.

## HIVE-original extensions

### Verification Frontier
Find the smallest proof set currently justified by feature/risk/evidence contracts, then expand monotonically as release criticality increases.

### Negative Coverage Evidence
Record where impact/test mapping is incomplete. Lack of a selected test is never represented as proof that no test is needed.

### Proof Aging
Proof validity decays or invalidates when dependency/policy/tool/environment contracts drift, even if source files are unchanged.

### Test Value Ledger
Track verified information gained per test cost for scheduling research, without allowing historical ROI to override mandatory gates.

## Release-train disposition
This capability is too substantial to remain a footnote inside 1.5.

Provisional options:
- keep as a named 1.5 sub-release/vertical if implementation remains coherent with orchestration;
- renormalize into its own minor release before 2.0 if scope/evidence warrants.

Final numbering is deferred until legacy reconciliation closes.

## Stop condition
Test Intelligence is implementation-ready only after unresolved R21 names are recovered/dispositioned, benchmark corpus governance is frozen, and feature/risk/evidence shared contracts are canonical planning inputs.
