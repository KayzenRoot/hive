# HIVE V2 — Legacy Planning Reconciliation Register

## Status
PLANNING RECONCILIATION. This register exists because HIVE V2 had multiple planning generations. The current incremental 1.x→2.0 train MUST preserve the approved/frozen V2 target and must not accidentally discard useful capabilities from earlier or later V2 research.

## Governing rule
1. Frozen R20 architecture remains the authority for the already-approved V2 target.
2. Earlier V2 drafts/registers are preserved as design provenance and gap sources.
3. Later post-freeze planning/research is not silently promoted. It is inventoried, classified, mapped and either:
   - integrated into a 1.x release when NECESSARY for correctness/DoD;
   - retained as IMPORTANT candidate;
   - kept EXPERIMENTAL/shadow until benchmark;
   - placed in FUTURE when it would make 2.0 unfinishable or contradict frozen architecture.
4. No previously planned item is silently deleted. Exclusion/deferment requires an explicit disposition.
5. New HIVE-original technology remains a research candidate until specification, benchmark and compatibility/security review.

## Source generations being reconciled

### Generation A — early V2 living architecture
Key themes:
- Context Planner / Context Compiler / Context Economy;
- hybrid + hierarchical retrieval;
- repository/code intelligence;
- ACCE-Hybrid;
- memory tiers/consolidation;
- Development Harness;
- stable prompt prefix/provider cache;
- token budgets/progressive disclosure;
- bounded agent orchestration;
- executor adapters;
- MCP/Skills registry;
- eval/retrieval harnesses;
- end-to-end observability;
- dashboard;
- security/project isolation;
- provenance;
- retry/idempotency;
- checkpoint control plane.

### Generation B — proprietary engineering fabric / improvement register
Explicit portfolio to preserve:
- HCC — Hive Context Compiler;
- SID — Semantic Incremental Development;
- PCC — Proof-Carrying Change;
- AIS — Architecture Immune System;
- Cognitive CI;
- EMN + Failure DNA;
- Adaptive Verification Budget;
- Capability Sandbox;
- Predictive Context Prefetch;
- Semantic Regression Engine;
- Living Specification Graph;
- Counterexample Generator;
- Change Risk Predictor;
- Cognitive Cache;
- Token ROI Scheduler;
- Adversarial Code Review orchestration;
- Self-Healing Development Loop.

Structural additions:
- Benchmark Laboratory;
- Feature/Experiment Gates;
- Compatibility/Contract Layer;
- Technology Maturity Registry.

### Generation C — frozen R20 V2
The 19 NECESSARY frozen groups remain the completion target:
1. inherited V0.1 local foundation;
2. governance/identity/provenance;
3. HUE-IR/EET;
4. C³;
5. temporal governed memory;
6. Verified Engineering Learning + HCELB;
7. durable task-centric orchestration;
8. UADS;
9. verification claim/evidence;
10. shared validity/event/policy;
11. HAZF;
12. local resource intelligence;
13. survivability/recovery;
14. observability/economics;
15. Control Center;
16. MCP/IDE integration;
17. release/provenance;
18. migration;
19. provider-unavailable degraded mode.

### Generation D — post-freeze/latest research extensions
Preserve and formally reconcile these named capability families from the later V2 planning:
- SDIR;
- MCSO;
- PEGR;
- VCC;
- NKC;
- AIG;
- Failure DNA;
- LVS;
- PCP;
- RPCache;
- FTI;
- Test Intelligence / Feature Verification Contract Registry;
- FIM;
- AITS;
- confidence budgets;
- PVR;
- shadow full-suite verification;
- real-use/resource/replay verification;
- defect genome;
- adversarial/flake/scheduling intelligence;
- Debugging & Defect Intelligence;
- DCF;
- FDL;
- IRC;
- MRE;
- GDC;
- trajectory debugger;
- anomaly sentinel;
- patch arena;
- counterfactual debugging;
- repair verification;
- regression lock.

Exact semantics for acronyms that are not present in current canonical sources MUST be recovered from their source before implementation. Their names alone are not sufficient specification.

## Current release mapping

### 1.1 Decision Fabric
Already absorbs:
- bounded decision/scoring;
- confidence/escalation;
- deterministic prefilter;
- cache/delta/shadow;
- risk-aware decision control.

Potential legacy mappings:
- Change Risk Predictor;
- confidence budgets;
- parts of AIG/decision gating where exact source confirms.

### 1.2 Governance & Canonical Contracts
Absorbs:
- Compatibility/Contract Layer;
- Technology Maturity Registry foundations;
- provenance/validity/promotion;
- feature/experiment lifecycle contracts;
- architecture decision authority.

### 1.3 HUE Repository Intelligence
Absorbs:
- repository intelligence;
- Code Intelligence Graph;
- Change Impact;
- EET;
- source→tests/evals;
- Living Specification Graph foundations;
- Semantic Regression structural evidence;
- SID structural/incremental component.

### 1.4 C³ Context Intelligence
Absorbs:
- HCC;
- Context Planner/Compiler/Economy;
- ACCE-Hybrid context side;
- Predictive Context Prefetch candidate;
- Cognitive Cache candidate;
- Token ROI Scheduler candidate;
- PCP/RPCache candidates only after exact source reconciliation.

### 1.5 Orchestration/UADS/Verification
Absorbs:
- PCC;
- Cognitive CI;
- Adaptive Verification Budget;
- Capability Sandbox;
- Feature/Experiment Gates;
- Test Intelligence;
- Feature Verification Contract Registry;
- FIM/AITS/PVR after semantic recovery;
- shadow full-suite;
- adversarial/flake/scheduling verification;
- bounded Self-Healing Development Loop;
- adversarial review.

### 1.6 Temporal Memory & Verified Learning
Absorbs:
- EMN + Failure DNA;
- validated failure/fix learning;
- defect genome candidates;
- replay/counterfactual learning;
- NKC/FTI where recovered semantics prove memory/learning fit.

### 1.7 Resources/Observability/Control Center
Absorbs:
- Token ROI/resource behavior;
- real-use resource verification;
- economic telemetry;
- dashboard visibility for all promoted capabilities.

### 1.8 Survivability/Recovery
Absorbs:
- repair/recovery evidence;
- anomaly/recovery state where not debugging-specific.

### 1.9 Integration/2.0 Readiness
Absorbs:
- Compatibility proof;
- full-suite integrated shadow;
- cross-capability regression;
- final feature/contract/evidence closure.

## Identified missing capability cluster: 1.x Debug/Test Intelligence expansion
The first-pass 1.1–1.9 map does not yet give the later R21/R22 Test Intelligence and Debugging/Defect Intelligence enough first-class detail.

Decision:
DO NOT hide this inside generic 1.5 verification.

Create explicit specifications before the release train is frozen:
- Test Intelligence expansion under 1.5, or a separate minor release if its coherent vertical slice is too large;
- Debugging & Defect Intelligence as its own coherent minor release candidate before 2.0 if source reconciliation proves it is part of the intended latest V2 target.

Release numbering may be renormalized. Semantic completeness has priority over preserving the provisional 1.1–1.9 numbering.

## Additional capability cluster requiring explicit planning

### Architecture Immune System
Needs a first-class spec for:
- architecture fitness functions;
- forbidden dependencies/imports;
- contract drift;
- database ownership;
- API/schema compatibility;
- module boundary violations;
- generated deterministic architecture evidence.

Likely delivery: 1.3 + 1.5, but must receive an explicit contract.

### Semantic Regression Engine
Needs explicit spec and benchmark:
- semantic/behavioral contract changes;
- changed intent/architecture;
- retrieval of prior verified behavior;
- false-positive control;
- deterministic evidence before LLM inference.

### Counterexample Generator
Experiment under verification:
- property/fuzz/model-based test candidate generation;
- bounded by risk/cost;
- generated tests are evidence candidates until executed.

### Self-Healing Development Loop
Must remain bounded:
execute → verify → diagnose → repair → reverify, with attempt/token/time/scope caps and escalation.

### Supply-chain / DevSecOps
Frozen research explicitly includes SAST/SCA/DAST where appropriate, SBOM, provenance/signing/SLSA-aligned controls, threat modeling, dependency risk and auditable agent actions. Current first-pass release map under-specifies this. Add an explicit security/supply-chain section before freeze.

### High-assurance verification profiles
Selective formal/model-checking/SMT/symbolic verification remains risk-adaptive, not universal. Add profile hooks without making formal methods mandatory for ordinary work.

### Project DNA / Adaptive Golden Paths
Frozen IMPORTANT. Preserve in backlog and design extension seams now; do not make 2.0 completion depend on advanced implementation unless later DoD evidence requires it.

### Domain profiles
Preserve research requirements for:
- Web2/SaaS;
- fintech/trading;
- Web3/DApps;
- games;
- UADS;
- UGAS.
Domain profiles strengthen risk/tool/verification/context policy without forking HIVE into separate products.

## Explicitly preserved IMPORTANT items
- Adaptive Golden Paths / Project DNA;
- full UGAS runtime integration;
- A2A;
- local embedding/reranker;
- halfvec/binary vector optimization;
- CAS pack optimization;
- Zstd dictionaries;
- advanced formal/mutation/provenance adapters;
- WASI microcomponents;
- deep counterfactual economics;
- expanded language parsers.

## Explicitly preserved FUTURE
- EWM/causal engineering beyond bounded experiments;
- fine-tuning/model evolution;
- Model Router as core;
- multi-tenant SaaS/enterprise control plane;
- BYOC/enterprise identity;
- Kubernetes/distributed HIVE;
- confidential/zkVM/PQC automation;
- autonomous organizational evolution;
- agent marketplace/society.

These remain preserved, not deleted. They do not block 2.0 unless separately promoted through governance.

## New completeness rule
Before 2.0 roadmap freeze, generate a Legacy Coverage Matrix with one row for every recoverable V2 capability from every source generation and columns:
- source generation/document/round;
- original classification;
- exact description;
- current classification;
- target release/module;
- acceptance evidence;
- disposition;
- reason for any deferment.

Coverage requirement: every source item has a disposition. UNKNOWN is permitted temporarily; SILENTLY DROPPED is not.

## Immediate next increments
1. recover exact semantics of all latest-plan acronyms/capabilities;
2. create Test Intelligence specification;
3. create Debugging & Defect Intelligence specification;
4. create Architecture Immune System / semantic-regression specification;
5. create DevSecOps/supply-chain/high-assurance profile specification;
6. generate full Legacy Coverage Matrix;
7. then renormalize the release train if necessary;
8. only after that freeze 1.1 and authorize executor work.

## Stop condition
No 1.x→2.0 roadmap may be called complete until every recoverable capability from the older frozen plan and the newer V2 planning has an explicit mapped disposition and all NECESSARY/latest-target gaps have specifications and objective proof requirements.
