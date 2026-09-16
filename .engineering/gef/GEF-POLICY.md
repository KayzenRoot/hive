# GEF V1 Universal Local Policy — HIVE

## Purpose

This policy adapts GEF Bootstrap V1.0.0 Universal Adoption to HIVE without replacing HIVE's canonical governance.

## Authority

When sources conflict, resolve HIVE work in this order unless a newer accepted canonical decision explicitly changes it:

1. latest accepted `docs/project-brain/13-CHECKPOINT.md`;
2. accepted `docs/project-brain/16-DECISIONS-LEDGER.md`;
3. approved `docs/project-brain/03-SCOPE.md`;
4. `docs/project-brain/15-DEFINITION-OF-DONE.md` and accepted criteria;
5. `docs/project-brain/04-ARCHITECTURE.md`;
6. `docs/project-brain/10-SECURITY-GOVERNANCE.md` and applicable policy constraints;
7. current approved Work Order / Context Lock;
8. `docs/project-brain/02-REQUIREMENTS.md` and remaining supporting sources;
9. informal notes.

Do not silently resolve material contradictions. Record them and fail closed when they affect safe execution or approval.

## Canonical execution loop

`ANALYZE -> SOURCE CHECK -> NEXT NECESSARY INCREMENT -> WORK ORDER -> CONTEXT LOCK -> PREFLIGHT -> EXECUTOR -> TESTS/EVIDENCE -> PR -> EXACT-HEAD AUDIT -> CHECKPOINT DELTA -> MERGE -> NEXT`

Substantial work requires a stable Work Order or an existing HIVE execution contract that is equivalent or stronger.

## Brownfield preservation

HIVE is BROWNFIELD. Therefore:

- inspect before mutation;
- preserve Git history and project-native architecture;
- prefer additive reconciliation and mappings;
- do not replace README, CI, architecture, tests, release semantics or naming simply to resemble a GEF template;
- do not convert historical work into fake GEF Work Orders;
- keep technical debt separate from adoption defects;
- preserve active exact-base work;
- do not mass-format unrelated files;
- never weaken tests, security, branch rules or Review Evidence to obtain green checks.

## Exact-head and active-work rule

The candidate SHA that is reviewed and tested must be the SHA approved. If HEAD changes, review again.

A new governance/adoption merge must not move `main` in a way that silently invalidates an active exact-base Work Order. Finish or canonically supersede the active Work Order first.

## Prompt rule

Use `.engineering/gef/GEF-PROMPT-REVIEW-STANDARD.md`, `GEF-WORK-ORDER-TEMPLATE.md` and `GEF-CONTEXT-LOCK-TEMPLATE.json` for substantial future work. Compile the smallest high-signal context that preserves correctness.

## Review rule

Allowed verdicts only:

- `APPROVED`
- `CORRECTION_REQUIRED`
- `BLOCKED`

A fixable defect inside the authorized increment is `CORRECTION_REQUIRED`. `BLOCKED` requires a concrete external, canonical or capability constraint that prevents safe progress.

`APPROVED` requires exact candidate identity, all required checks complete, CRITICAL=0, HIGH=0, no unresolved scope/preservation/evidence mismatch and no stale-head mismatch.

## Evidence rule

Evidence is load-bearing only when it binds to the Work Order, exact candidate HEAD, actual commands/workflows/results, corrections, security findings and unresolved risks.

- `UNKNOWN` is not `PASS`.
- Missing evidence is not completion.
- A hash demonstrates integrity of covered bytes; it is not signing.
- Executor claims are staged until independently validated.
- Optional adapters are not release blockers unless the target actually requires them.

## HIVE validation

Discover real commands from the repository. Current baseline includes:

- `python scripts/validate.py`;
- hosted `Validate`;
- hosted `Integration health`;
- hosted `Review Evidence`.

Use focused checks during implementation and a full candidate assurance sweep when release-critical. GEF proof-reuse optimizations remain subordinate to HIVE required gates until objective evidence authorizes otherwise.

## Git/GitHub

- protected `main` remains authoritative;
- substantial work uses branches/PRs;
- merge policy follows current ruleset, presently squash-only;
- no force-push to protected history;
- no direct canonical mutation that violates repository policy;
- single-owner operation does not require artificial human approval, but exact-head technical audit remains mandatory;
- auto-merge must not bypass Sol/HIVE gates.

## Security

Tailor controls to HIVE's actual threat surface: secrets/redaction, project isolation, untrusted prompt/document boundaries, path and symlink safety where filesystem operations exist, bounded process execution, dependency risk, generated artifact integrity, recovery from partial mutation and GitHub permission boundaries.

CRITICAL or HIGH unresolved release blockers prohibit approval.

## Completion claims

GEF adoption progress and HIVE product progress are separate. Completing GEF adoption does not increase HIVE product completion by itself. HIVE V0.1 may only be declared complete when canonical DoD and final-review requirements are objectively satisfied.
