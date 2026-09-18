# HIVE 2.0 — Completion Gate and Evidence Matrix

## Status
PLANNING CANDIDATE. This is a completion contract, not authorization to release.

## Principle
HIVE 2.0 is declared only when the frozen V2 NECESSARY target is objectively satisfied by the accumulated stable release train. No feature is considered complete because it was planned, coded or demonstrated once.

## Frozen target mapping

| Frozen capability group | Planned delivery | 2.0 proof family |
|---|---|---|
| inherited V0.1 local foundation | 1.0 | existing closure + regression |
| canonical governance/identity/provenance | 1.2 | authority/validity/reconciliation |
| HUE-IR/EET repository intelligence | 1.3 | graph/impact/rebuild |
| C³ context/progressive disclosure | 1.4 | context quality/economy |
| temporal governed memory | 1.6 | temporal/contradiction/provenance |
| Verified Engineering Learning + HCELB | 1.6 | HCELB + learning safety |
| task-centric durable orchestration | 1.5 | recovery/proof-carrying runs |
| UADS quality integration | 1.5 | UADS evidence lineage |
| verification claim/evidence model | 1.5 | proof obligations/claims |
| shared validity/event/policy infrastructure | 1.2 + 1.5 | policy/event coherence |
| HAZF security boundary | 1.5 | security/capability matrix |
| local resource intelligence | 1.7 | calibration/pressure |
| survivability/recovery | 1.8 | clean restore/fault injection |
| observability/engineering economics | 1.7 | truthful economics/trace |
| full Control Center views | 1.7 + 1.9 | integrated UI truthfulness |
| MCP/IDE-native integration | 1.5 + 1.9 | bounded integration |
| release/provenance baseline | 1.0 + all releases | release manifests |
| V0.1→V2 migration | 1.9 | upgrade chain/migration |
| provider-unavailable degraded mode | 1.5 + 1.9 | degraded capability proof |

Decision Fabric 1.1 is an additive post-freeze capability that strengthens policy/economy but is not used to hide a missing frozen capability.

## Evidence states
Every DoD item is exactly one of:
- PROVEN;
- NOT_APPLICABLE with justification;
- MISSING;
- STALE;
- BLOCKED.

Only PROVEN or valid NOT_APPLICABLE may close a required item.

## Global functional gate
Prove representative end-to-end engineering workflows across multiple project fixtures, restart boundaries and exact Git/checkpoint bases.

## Global test gate
Required:
- unit;
- integration;
- deterministic generated maps/registries;
- E2E;
- migration/upgrade;
- fault injection/recovery;
- security/isolation;
- benchmark;
- dashboard truthfulness;
- provider degraded mode.

## Global documentation gate
Current:
- source of truth;
- requirements/scope/architecture;
- decisions;
- operations;
- installation/upgrade/rollback;
- backup/recovery;
- MCP/integration;
- security;
- Control Center;
- benchmark methodology;
- release evidence;
- known limitations.

## Local deployment gate
A clean supported workstation must be able to:
- install;
- initialize persistent roots;
- start Compose;
- pass migrations/health;
- register/use projects;
- survive restart;
- perform backup/restore;
- upgrade through supported path.

## Data integrity gate
- PostgreSQL canonical structured truth preserved;
- CAS hash/integrity preserved;
- Redis disposable;
- derived state rebuildable;
- project isolation;
- provenance/validity explicit;
- no silent canonical promotion.

## Economy gate
Report quality together with:
- fresh/cached/output tokens;
- retrieved/sent context;
- context reduction;
- provider/tool calls;
- cache hit;
- storage logical/physical;
- latency;
- resource pressure;
- cost where pricing provenance exists.

No minimum marketing percentage is invented. Claims require reproducible benchmark evidence.

## Learning gate
HCELB must show the enabled Verified Learning path is either:
- measurably beneficial within approved quality/safety bounds, or
- kept disabled/shadow-only.

A harmful or unproven learning control path cannot be required for 2.0 correctness.

## Recovery gate
Prove:
- verified backup;
- clean-target restore;
- Redis loss;
- CAS corruption handling;
- disk pressure;
- interrupted operation;
- interrupted/failed migration;
- Known-Good State visibility;
- read-only survival where applicable.

## Security gate
HIGH/CRITICAL unresolved release defects = 0.

Re-run isolation, tool/capability, filesystem, network, secrets, staged/canonical, provider, MCP and recovery/migration boundaries.

## Performance gate
No material unexplained regression against frozen representative baselines. Accepted tradeoffs must be explicit and tied to required correctness/security capability.

## Release provenance gate
Bind final 2.0:
- exact source commit;
- tag;
- migration head;
- artifact hashes;
- test/evidence index;
- release authorization;
- upgrade/rollback;
- known limitations;
- post-release install smoke.

## Final audit procedure
1. generate Evidence Closure report;
2. reject any MISSING/STALE/BLOCKED required item;
3. inspect NOT_APPLICABLE justifications;
4. verify exact-head evidence;
5. run final integration/security/recovery/migration gates;
6. verify release provenance;
7. update canonical checkpoint/decision/release docs;
8. only then authorize tag/release.

## Final declaration
Only after all gates pass:

`HIVE V2.0 — VERSION COMPLETE`

## Stop condition
If any required evidence is MISSING, STALE or BLOCKED, the only next work is the smallest corrective/closure increment. No declaration, tag or roadmap advancement substitutes for proof.
