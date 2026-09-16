# GEF Bootstrap V1.0.0 Universal Adoption — HIVE

## Identity

- Repository: `KayzenRoot/hive`
- Project: `HIVE`
- Adoption work order: `GEF-UNIVERSAL-ADOPTION-002`
- Adoption mode: `BROWNFIELD`
- GEF baseline: `GEF Bootstrap V1.0.0 Universal Adoption`
- Discovery baseline: `main@4fb0aa111bd5b0f526df85b1897618d8eca1c0e0`
- Adoption branch: `governance/gef-v1-universal-adoption-002`
- Assurance: `MAX_ASSURANCE`
- Existing GEF historical adoption: PR `#81`, merged as `2ccbf09c193ba30e78d768bb32a4e78a4f209812`
- Current product increment at discovery: PR `#95`, `WO-024`, exact authorized base `4fb0aa111bd5b0f526df85b1897618d8eca1c0e0`

## Purpose

Reconcile HIVE's already-existing GEF layer with the Universal Adoption model without replacing HIVE's canonical Project Brain, product architecture, CI, branch rules, tests, or historical work. This is an additive governance upgrade, not a project rewrite.

## Canonical authority mapping

GEF does not create parallel HIVE product truth. The project-native authority remains:

1. `docs/project-brain/13-CHECKPOINT.md`
2. `docs/project-brain/16-DECISIONS-LEDGER.md`
3. `docs/project-brain/03-SCOPE.md`
4. `docs/project-brain/15-DEFINITION-OF-DONE.md`
5. `docs/project-brain/04-ARCHITECTURE.md`
6. `docs/project-brain/10-SECURITY-GOVERNANCE.md` and applicable policy constraints
7. current approved Work Order / Context Lock
8. `docs/project-brain/02-REQUIREMENTS.md` and remaining supporting sources
9. informal notes

Where HIVE's approved source hierarchy is more specific than generic GEF, HIVE remains authoritative. GEF is the execution, review, evidence, context-lock and adoption layer around those sources.

## Repository discovery receipt

HIVE is BROWNFIELD because it has substantial product code, migrations, tests, Docker Compose, dashboard, architecture, long Git history, protected-main governance, active Work Orders, accepted decisions and an existing GEF layer.

Observed at adoption discovery:

- default branch: `main`;
- protected main: ruleset `21934284` (`Protect main`), squash-only, review-thread resolution, zero bypass;
- required checks: `Validate`, `Integration health`, `Review Evidence`;
- backend: Python 3.12, FastAPI-oriented application modules, pytest, Ruff, strict mypy;
- dashboard: React/TypeScript/Vite/Vitest/ESLint;
- runtime: Docker Compose, PostgreSQL + pgvector, Redis-compatible HOT cache, local CAS;
- canonical validation entry point: `python scripts/validate.py`;
- hosted CI: `.github/workflows/ci.yml`;
- agent guidance: `AGENTS.md`;
- canonical governance: `docs/project-brain/**`;
- GEF artifacts already exist under `.engineering/gef/**`;
- active product closure PR: `#95`, which must be preserved exactly until its governed lifecycle ends.

Machine-readable detail lives in `GEF-DISCOVERY-RECEIPT.json` and `GEF-PRESERVATION-MAP.json`.

## Brownfield preservation plan

The following are project authority and are not replaced by GEF:

- `docs/project-brain/**`;
- `.github/workflows/ci.yml`;
- ruleset `21934284`;
- existing source, tests, migrations and deployment topology;
- current release/version semantics;
- historical commits, PRs, reviews and accepted evidence;
- active `WO-024` branch/PR and its exact-base contract.

The following are reconciled as GEF-derived engineering state:

- `.engineering/gef/GEF-ADOPTION.md`;
- `.engineering/gef/GEF-CURRENT.json`;
- `.engineering/gef/GEF-POLICY.md`;
- `.engineering/gef/GEF-EXECUTION-PROTOCOL.md`;
- `.engineering/gef/GEF-REVIEW-PROTOCOL.md`;
- new discovery, preservation, project-master, checkpoint, Work Order and Context Lock artifacts.

No historical module is retroactively labelled GEF-complete. Historical work remains historical evidence only where the repository proves it.

## Canonical GEF lifecycle for HIVE

`ANALYZE -> SOURCE CHECK -> NEXT NECESSARY INCREMENT -> WORK ORDER -> CONTEXT LOCK -> PREFLIGHT -> EXECUTOR -> TESTS/EVIDENCE -> PR -> EXACT-HEAD AUDIT -> CHECKPOINT DELTA -> MERGE -> NEXT`

Substantial mutation requires a stable Work Order or an existing HIVE Work Order that already satisfies the same contract. Routine deterministic inspection does not require a new Work Order.

## Active-work preservation rule

A governance/adoption increment MUST NOT be merged if doing so would silently invalidate an active exact-base Work Order. At discovery, `WO-024` PR #95 is authorized against the current main SHA `4fb0aa111bd5b0f526df85b1897618d8eca1c0e0`. Therefore this universal adoption may be prepared and audited on its own branch, but its canonical merge must wait until `WO-024` reaches its own governed terminal state or is explicitly superseded by a canonical decision.

This is preservation, not a convenience delay. The adoption must not force-rebase, retarget, rewrite, broaden or invalidate PR #95.

## Prompt standard

Every substantial executor prompt must, when applicable, contain:

- OBJECTIVE;
- CONTEXT and SOURCE CHECK;
- WORK ORDER identity;
- CONTEXT LOCK / exact base and expected head semantics;
- IN SCOPE / OUT OF SCOPE;
- FILES OR AREAS TO READ;
- ALLOWED/PRESERVED paths;
- REQUIREMENTS;
- ARCHITECTURE and SECURITY constraints;
- EXECUTION WAVES / critical path when useful;
- ACCEPTANCE CRITERIA;
- TESTS / VALIDATION REUSE PLAN;
- EVIDENCE requirements;
- REVIEW FORMAT;
- ROLLBACK/RECOVERY when mutation is material;
- STOP CONDITION.

Use `GEF-WORK-ORDER-TEMPLATE.md` and `GEF-CONTEXT-LOCK-TEMPLATE.json`. For large autonomous runs, compile a Marathon Execution Pack instead of repeatedly rediscovering the repository.

## Review standard

Reviews are delta-first and exact-head. An executor's statement of completion is not proof. Reviewers must inspect the candidate SHA, scope, changed paths, source authority, invalidated evidence, required test results, security findings, unresolved threads and exact-head CI.

Allowed verdicts:

- `APPROVED`
- `CORRECTION_REQUIRED`
- `BLOCKED`

`APPROVED` requires the reviewed candidate SHA to equal the candidate being promoted, all required checks complete, CRITICAL=0, HIGH=0, no unresolved scope/preservation/evidence mismatch and no stale-head mismatch. If HEAD moves, re-audit.

A fixable defect inside the approved increment is `CORRECTION_REQUIRED`, not `BLOCKED`. `BLOCKED` is reserved for a real external, canonical or capability blocker that prevents safe progress.

## Evidence and assurance

Evidence must bind to Work Order, exact candidate SHA, commands/workflows, results, failures/corrections, security findings and unresolved risks. `UNKNOWN` is never coerced to PASS. A digest proves integrity of the bytes it covers; it is not a cryptographic signature.

The HIVE required hosted gates remain authoritative. GEF optimizations, proof carry-forward and selective validation remain subordinate to measurable non-degradation and may never weaken those gates merely to obtain green CI.

## Security baseline

Preserve least privilege, project isolation, secret redaction, untrusted-input boundaries, path/symlink safety where filesystem mutation exists, bounded shell/process execution, dependency auditing, generated-artifact integrity and recovery from partial mutation. CRITICAL/HIGH unresolved release-blocking findings prohibit approval.

## Adoption acceptance status

At this branch baseline:

- repository discovery: COMPLETE;
- classification: BROWNFIELD;
- collision/preservation analysis: COMPLETE;
- canonical source mapping: COMPLETE;
- Work Order standard: INSTALLED ON ADOPTION BRANCH;
- Context Lock standard: INSTALLED ON ADOPTION BRANCH;
- review/prompt model: RECONCILED ON ADOPTION BRANCH;
- user work preservation: VERIFIED BY SCOPE;
- destructive normalization: NONE;
- canonical adoption merge: DEFERRED because active exact-base `WO-024` must not be invalidated;
- final post-adoption checkpoint: PENDING canonical adoption merge.

Current stop state: `GEF_ADOPTION_EXACT_HEAD_EVIDENCE_REQUIRED`.

## Next legal action

1. Continue and finish the already-authorized `WO-024` without changing its base contract.
2. After `WO-024` reaches its governed terminal state, refresh this adoption branch onto the new accepted main.
3. Re-run collision/preservation checks and repository-native validation.
4. Open/refresh the adoption PR with an adoption-compatible exact-head evidence path.
5. Perform exact-head technical audit and squash merge when all required gates are green.
6. Update `GEF-UNIVERSAL-CHECKPOINT.json` to `GEF_V1_ADOPTED_READY_FOR_GOVERNED_DEVELOPMENT` on the accepted post-merge state.

Until then, this branch is a complete staged installation, not canonical project truth.
