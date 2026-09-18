# HIVE V2 — Technology Maturity Registry

## Status
PLANNING CANDIDATE.

## Objective
Make innovation aggressive but governed. New technology can enter HIVE quickly as research without becoming a hidden production dependency.

## Maturity states
DISCOVERED → SCREENED → LAB_CANDIDATE → BENCHMARKED → SHADOW → LIMITED → PRODUCTION_ELIGIBLE.
Terminal states: REJECTED, SUPERSEDED, RETIRED.

Progression is evidence-based, not automatic.

## Registry record
Each technology/candidate stores:
- stable id/name;
- internal/external/original;
- problem/hypothesis;
- maturity;
- scope/classification NECESSARY/IMPORTANT/FUTURE;
- upstream identity/license if external;
- architecture seam;
- local-first/provider-independence impact;
- security/supply-chain review;
- benchmark protocol/baseline;
- quality/economy/resource results;
- failure/fallback/removal path;
- feature flag/shadow state;
- evidence refs;
- owner/governance decision;
- last validation/expiry.

## Promotion rules
DISCOVERED→SCREENED: problem and source identity known.
SCREENED→LAB: compatible architecture/license and bounded experiment.
LAB→BENCHMARKED: reproducible comparison completed.
BENCHMARKED→SHADOW: no unacceptable quality/security regression and integration is reversible.
SHADOW→LIMITED: real workload evidence supports benefit.
LIMITED→PRODUCTION_ELIGIBLE: release gates, migration/rollback, observability and support burden acceptable.

## HIVE-original technology
Original ideas follow the same gates. "Invented by HIVE" is not evidence of superiority.

## External technology
Supply-chain adoption gate from DevSecOps applies. Mandatory cloud dependency conflicts with local-first core unless explicitly classified as optional adapter.

## Retirement
A technology may be retired when benefit disappears, upstream risk rises, a shared primitive supersedes it or maintenance cost exceeds measured value. Canonical user state must survive retirement.

## Technology portfolio
Control Center/planning views should expose candidates by maturity, measured benefit, risk, maintenance burden and next evidence needed. Avoid a single opaque score.

## Initial registry candidates
- Jev-compatible DecisionProvider: DISCOVERED, exact upstream audit pending.
- Decision Delta: LAB_CANDIDATE.
- Confidence Debt: LAB_CANDIDATE.
- Predictive Context Prefetch: LAB_CANDIDATE.
- Cognitive Cache: LAB_CANDIDATE.
- Token ROI Scheduler: LAB_CANDIDATE.
- Counterexample Generator: LAB_CANDIDATE.
- PVR/Proof Validity Reuse: LAB_CANDIDATE.
- Patch Arena: LAB_CANDIDATE.
- Security Proof Delta: LAB_CANDIDATE.
- Architecture Antibodies: LAB_CANDIDATE.
- Experience Minimality Test: LAB_CANDIDATE.

These states are planning labels, not claims that benchmarks already exist.

## Stop condition
No experimental technology may become a mandatory release dependency without a registry record and evidence satisfying the applicable promotion gates.
