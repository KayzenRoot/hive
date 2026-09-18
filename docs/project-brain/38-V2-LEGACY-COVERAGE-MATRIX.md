# HIVE V2 — Legacy Coverage Matrix v0.1

## Status
PLANNING / COVERAGE ACCOUNTING. This matrix is deliberately conservative. It maps only capabilities whose semantics are recoverable from the frozen/living V2 sources or later planning evidence. Unresolved names remain unresolved. Nothing is silently dropped.

## Authority
- R20 frozen source controls the approved V2 target.
- R01–R19 research remains design provenance.
- Architecture Improvement Register is a gap/optimization source.
- Later R21/R22 planning is reconciled as additional capability planning and must not silently override R20.
- Post-freeze/new HIVE-original concepts require classification and evidence before promotion.

## Coverage states
MAPPED = explicit target exists.
PARTIAL = concept exists but needs a dedicated contract/spec.
PRESERVED_IMPORTANT = retained but not required for 2.0 unless promoted.
PRESERVED_FUTURE = intentionally deferred.
EXPERIMENT = benchmark/shadow required.
UNRESOLVED = source semantics must be recovered before implementation.
SUPERSEDED_BY_SHARED_PRIMITIVE = semantics retained through a more general approved primitive.

## A. Frozen R20 NECESSARY target

| Capability | State | Current destination |
|---|---|---|
| Local-first / single-operator foundation | MAPPED | 1.0 + regression |
| Docker Compose default | MAPPED | 1.0 + release regression |
| PostgreSQL + pgvector | MAPPED | 1.0 + migration gates |
| Redis HOT/noncanonical | MAPPED | 1.0 + cache taxonomy/recovery |
| Git canonical / CAS immutable artifacts | MAPPED | 1.0/1.2/1.8 |
| Governance / identity / provenance | MAPPED | 1.2 |
| Shared validity/freshness kernel | MAPPED | 1.2 |
| Shared event/evidence spine | MAPPED | 1.2/1.5 |
| Shared policy/capability kernel | MAPPED | 1.2/1.5 |
| HUE-IR/EET bounded graph | MAPPED | 1.3 |
| C³ context contract | MAPPED | 1.4 |
| Temporal governed memory | MAPPED | 1.6 |
| VEXL→Archetype→EEC→OCAR→XTV/HCELB learning kernel | PARTIAL | 1.6, exact legacy-object contract still required |
| Durable task-centric orchestration | MAPPED | 1.5 |
| UADS integration | MAPPED | 1.5 |
| Verification claim/evidence model | MAPPED | 1.5 + Test Intelligence |
| HAZF security boundary | MAPPED | 1.5 + DevSecOps profile |
| Local resource intelligence | MAPPED | 1.7 |
| Survivability/recovery | MAPPED | 1.8 |
| Observability/economics | MAPPED | 1.7 |
| Full Control Center | MAPPED | 1.7/1.9 |
| MCP primary IDE/agent integration | MAPPED | 1.5/1.9 |
| Release/provenance baseline | MAPPED | all releases |
| V0.1→V2 migration | MAPPED | 1.9 |
| Provider/GPU unavailable degraded mode | MAPPED | 1.5/1.9 |
| Cross-project EEC transfer + operator approval | PARTIAL | 1.6 governance |
| Backup-complete vs physical-independence claim discipline | MAPPED | 1.8 |
| End-to-end learning proof | PARTIAL | 1.6 + 1.9 |
| End-to-end failure/recovery proof | MAPPED | 1.8 + 1.9 |

## B. Architecture Improvement Register

| Register capability | State | Destination |
|---|---|---|
| Context Planner | MAPPED | 1.4 C³ |
| Context Compiler | MAPPED | 1.4 C³ |
| Context Economy Engine | MAPPED | 1.4/1.7 |
| Hybrid + Hierarchical Retrieval Contract | MAPPED | 1.3/1.4 |
| HCC — Hive Context Compiler | MAPPED | 1.4 |
| SID — Semantic Incremental Development | PARTIAL | 1.3/1.5 |
| PCC — Proof-Carrying Change | MAPPED | 1.5 |
| AIS — Architecture Immune System | MAPPED | dedicated spec 36 |
| Cognitive CI | MAPPED | spec 36 + Test Intelligence |
| EMN + Failure DNA | PARTIAL | 1.6 + Debug Intelligence |
| Adaptive Verification Budget | MAPPED | Test Intelligence |
| Capability Sandbox | MAPPED | 1.5 + DevSecOps |
| Predictive Context Prefetch | EXPERIMENT | 1.4 |
| Semantic Regression Engine | MAPPED | spec 36 |
| Living Specification Graph | MAPPED | 1.3 + spec 36 |
| Counterexample Generator | EXPERIMENT | Test Intelligence |
| Change Risk Predictor | EXPERIMENT | 1.1 + Test Intelligence |
| Cognitive Cache | EXPERIMENT | 1.4 |
| Token ROI Scheduler | EXPERIMENT | 1.4/1.7 |
| Adversarial Code Review | EXPERIMENT | 1.5/Test Intelligence |
| Self-Healing Development Loop | EXPERIMENT | Debug Intelligence |
| Benchmark Laboratory | MAPPED | shared benchmark conventions + per-release harnesses |
| Feature/Experiment Gates | MAPPED | 1.2/1.5 |
| Compatibility/Contract Layer | MAPPED | 1.2 |
| Technology Maturity Registry | PARTIAL | shared conventions / planning governance |

## C. Later Test Intelligence planning

| Capability | State | Destination |
|---|---|---|
| Feature Verification Contract Registry / FTI | MAPPED | spec 34 |
| FIM — Feature Impact Map | MAPPED | spec 34 |
| AITS — Adaptive Impact Test Selector | MAPPED | spec 34 |
| PVR — Proof Validity Reuse | EXPERIMENT | spec 34 shadow-first |
| Shadow full-suite verification | MAPPED | spec 34 |
| Flake intelligence | MAPPED | spec 34 |
| Scheduling intelligence | MAPPED | spec 34 |
| Real-use/resource/replay verification | MAPPED | spec 34 + 1.7 |
| SFC | UNRESOLVED | recover exact source |
| RUF | UNRESOLVED | recover exact source |
| RBG | UNRESOLVED | recover exact source |
| BCR | UNRESOLVED | recover exact source |
| DGS | UNRESOLVED | recover exact source |

## D. Later Debugging & Defect Intelligence planning

| Capability | State | Destination |
|---|---|---|
| DCF — Defect Causality Fabric | MAPPED | spec 35 |
| FDL — First Divergence Locator | MAPPED | spec 35 |
| IRC — Incident Replay Capsule | MAPPED | spec 35 |
| MRE — Minimal Reproducer Engine | MAPPED | spec 35 |
| GDC — Git-Defect Correlator | MAPPED | spec 35 |
| trajectory debugger | MAPPED | spec 35 |
| anomaly sentinel | MAPPED | spec 35 |
| patch arena | EXPERIMENT | spec 35 |
| counterfactual debugging | EXPERIMENT | spec 35 |
| repair verification | MAPPED | spec 35 |
| regression lock | MAPPED | spec 35 |
| defect genome / Failure DNA | PARTIAL | spec 35 + 1.6 |

## E. Frozen IMPORTANT items

| Capability | State | Disposition |
|---|---|---|
| Adaptive Golden Paths / Project DNA | PRESERVED_IMPORTANT | extension seams + backlog |
| full UGAS runtime integration | PRESERVED_IMPORTANT | contract now, runtime optional |
| A2A | PRESERVED_IMPORTANT | optional integration |
| local embedding/reranker | PRESERVED_IMPORTANT | optional/local capability |
| halfvec/binary vector optimization | PRESERVED_IMPORTANT | benchmark candidate |
| CAS pack optimization | PRESERVED_IMPORTANT | storage experiment |
| Zstd dictionaries | PRESERVED_IMPORTANT | storage experiment |
| advanced formal/mutation/provenance adapters | PRESERVED_IMPORTANT | high-assurance profiles |
| WASI microcomponents | PRESERVED_IMPORTANT | sandbox/plugin research |
| deep counterfactual economics | PRESERVED_IMPORTANT | economics research |
| expanded language parsers | PRESERVED_IMPORTANT | HUE adapters |

## F. Frozen FUTURE

| Capability | State |
|---|---|
| fine-tuning/model evolution | PRESERVED_FUTURE |
| Model Router as core | PRESERVED_FUTURE |
| multi-tenant SaaS/enterprise control plane | PRESERVED_FUTURE |
| BYOC/enterprise identity | PRESERVED_FUTURE |
| Kubernetes/distributed HIVE | PRESERVED_FUTURE |
| confidential/zkVM/PQC automation | PRESERVED_FUTURE |
| autonomous organizational evolution | PRESERVED_FUTURE |
| agent marketplace/society | PRESERVED_FUTURE |
| frontier EWM/causal engineering beyond bounded experiments | PRESERVED_FUTURE |

## G. Domain requirements

| Domain | Coverage disposition |
|---|---|
| Web2/SaaS/API | policy/context/test profile required |
| fintech/trading | elevated risk/verification profile required |
| Web3/DApps/smart contracts | elevated/critical security + invariant profile required |
| games/game systems | project/HUE/test/resource profile required |
| AI applications | provider/data/eval profile required |
| UADS | core integration NECESSARY |
| UGAS | contract IMPORTANT, runtime not generic-2.0 blocker |

## H. Cross-cutting missing specifications discovered

1. Exact legacy learning object model VEXL/Archetype/EEC/OCAR/XTV/HCELB needs a compact current spec.
2. Domain Profiles need an explicit contract rather than scattered requirements.
3. Technology Maturity Registry needs a compact shared schema.
4. Shared cache/risk/config/benchmark conventions from Gap Audit G-01..G-25 need a canonical planning document.
5. SFC/RUF/RBG/BCR/DGS remain unresolved and cannot be guessed.
6. Latest-plan acronyms SDIR/MCSO/PEGR/VCC/NKC/AIG/LVS/PCP/RPCache/FTI require source-by-source reconciliation; FTI is already mapped, the rest remain unresolved until exact semantics are recovered.
7. Jev-specific adapter remains blocked on exact upstream/license/API/benchmark audit.

## Coverage conclusion
No recovered frozen NECESSARY capability is currently marked DROPPED. Several are PARTIAL and therefore still block final planning freeze. IMPORTANT and FUTURE items are explicitly preserved rather than silently deleted.

## Next planning increments
1. compact spec for the frozen verified-learning object model;
2. Domain Profile contract;
3. shared contract/risk/cache/config/benchmark conventions;
4. Technology Maturity Registry;
5. continue exact acronym/source recovery;
6. external technology research, starting with Jev;
7. renormalize minor-release numbering after all NECESSARY/latest-target verticals are explicit.

## Stop condition
This matrix cannot become FINAL while any recoverable source item lacks a disposition or any frozen NECESSARY item remains PARTIAL without an implementation-grade specification.


## I. Recovered exact legacy names — reconciliation pass 2

This section resolves only names supported by prior planning records. It does not infer missing semantics.

| Legacy token | Exact recovered name | Coverage disposition |
|---|---|---|
| SDIR | Semantic Delta Intermediate Representation | PARTIAL → HUE/C3 seam; exact implementation contract still required |
| MCSO | Minimal Change Surface Optimizer | PARTIAL → HUE/Orchestration/Test Intelligence |
| PEGR | Pre-Execution Grounding Readiness Gate | PARTIAL → Orchestration/Verification |
| VCC | Verified Context Cache | PARTIAL → C3/cache validity; note: unrelated projects may reuse the acronym, HIVE meaning is this planning record |
| NKC | Negative Knowledge Cache | PARTIAL → C3/Verified Learning/negative evidence |
| AIG | Architecture Integrity Gate | MAPPED → Architecture Immune System / Cognitive CI |
| LVS | Live Verification Stream | PARTIAL → Verification/Telemetry/Control Center |
| PCP | Predictive Context Prefetch | EXPERIMENT → C3; already preserved in Architecture Improvement Register |
| RPCache | Retrieval Plan Cache | EXPERIMENT → HUE/C3 retrieval planning |
| FTI | Flaky Test Intelligence | PARTIAL → Test Intelligence. This corrects the earlier ambiguous expansion in this matrix; Feature Verification Contract Registry remains a capability but must not reuse FTI without a distinct stable id. |
| SFC | Shadow Full-Suite Calibration | MAPPED → Test Intelligence |
| RUF | Real-Use Fixture & Journey Layer | MAPPED → Test Intelligence / release validation |
| RBG | Resource Behavior Guard | MAPPED → Test Intelligence / Resource Intelligence |
| BCR | Behavioral Contract Replay | MAPPED → Test + Debug Intelligence |
| DGS | Defect Genome Store | MAPPED → Debug Intelligence / governed defect memory |

### Semantic notes recovered
- SFC periodically runs the full suite hidden in calibration/shadow mode.
- RUF verifies real installation/product journeys, not only isolated functions.
- RBG covers resource behavior including agents/conversations/retries/tokens/quota/CPU/RAM/fan-out.
- BCR turns a real user bug into a permanent reproducible behavioral scenario.
- DGS is structured defect/bug memory.

### Conflict resolution
An earlier planning pass expanded FTI as Feature Verification Contract Registry. A later exact legacy record identifies FTI as Flaky Test Intelligence. The registry capability itself remains valuable and preserved, but it must receive a non-conflicting stable identifier before freeze. No data/model/API contract may ship with the ambiguous acronym.

## J. Jev audit disposition
- Jev-compatible remote provider: SCREENED / OPTIONAL.
- local direct-logit scorer: LAB_CANDIDATE.
- prefix/shared-state scorer: LAB_CANDIDATE / SHADOW mandatory.
- no Jev implementation is a mandatory core dependency.
- HIVE owns deterministic policy, calibration, evidence, routing and fallback.

## K. Updated coverage blockers
The legacy-name blocker is materially reduced. Remaining work is no longer to guess acronyms; it is to write compact implementation contracts for PARTIAL capabilities that are required by the final release train, resolve the FTI identifier collision, and perform the canonical cross-audit before any 1.1 implementation prompt.
