# GEF V1 Universal Execution Protocol — HIVE

## Pipeline

All substantial governed work follows:

`ANALYZE -> SOURCE CHECK -> NEXT NECESSARY INCREMENT -> WORK ORDER -> CONTEXT LOCK -> PREFLIGHT -> EXECUTOR -> TESTS/EVIDENCE -> PR -> EXACT-HEAD AUDIT -> CHECKPOINT DELTA -> MERGE -> NEXT`

Do not jump from an idea directly to mutation when a stable execution contract is needed.

## 1. ANALYZE

Inspect current repository state, active branches/PRs, canonical checkpoint, applicable decisions, scope, DoD and architecture. Determine whether the requested change is NECESSARY, IMPORTANT, FUTURE or OUT OF SCOPE under HIVE governance.

Do not start a next implementation increment while the current one is still awaiting correction or validation.

## 2. SOURCE CHECK

Resolve project authority before implementation. Use the HIVE authority order from `GEF-POLICY.md`. Record material contradictions. Do not silently choose the most convenient source.

## 3. NEXT NECESSARY INCREMENT

Define the smallest coherent increment that materially advances the accepted checkpoint/DoD. Prefer a larger safe increment over many tiny handoffs when dependencies allow it, but do not combine unrelated scope.

## 4. WORK ORDER

Use a stable Work Order. Existing HIVE Work Orders remain valid when they already specify objective, scope, allowed paths, constraints, acceptance, tests/evidence, review and stop condition.

New substantial work should use `GEF-WORK-ORDER-TEMPLATE.md`.

## 5. CONTEXT LOCK

Bind the execution to project identity, authorized base SHA, expected branch/HEAD semantics, source authority, allowed/preserved paths and stale-head policy. Use `GEF-CONTEXT-LOCK-TEMPLATE.json` when a machine-readable lock is useful.

Fail closed when identity, HEAD, project/task binding or authority becomes stale or ambiguous.

## 6. PREFLIGHT

Before mutation:

- confirm branch/base/current HEAD;
- inspect changed/untracked state where applicable;
- detect active exact-base work that must be preserved;
- resolve collision/preservation constraints;
- identify real validation commands;
- confirm required tools/permissions;
- check that the increment can be rolled back safely.

## 7. EXECUTOR

The executor must inspect existing implementation before changes and implement only the approved increment. Local implementation choices are allowed when compatible with architecture and constraints.

For large work, compile executor acceleration context:

- Implementation Seed Tree;
- File Intent Capsule;
- Brownfield Patch Intent Capsule;
- Executor Navigation Map;
- Decision Closure Capsule;
- Execution Waves;
- Validation Reuse Plan;
- Critical Path;
- Marathon Execution Pack when useful.

Prefer deterministic code/tools before LLM/provider calls. Do not repeatedly reread the whole repository when a smaller high-signal context is sufficient.

## 8. TESTS / EVIDENCE

Use real repository commands, never invented commands. Apply proportionate assurance:

1. structural/static;
2. focused/direct;
3. impacted dependency;
4. boundary/integration;
5. risk expansion;
6. full candidate assurance for release-critical work.

During coding, run focused checks. After the candidate stabilizes, run the required full sweep once. If it reveals an in-scope defect, fix it, rerun affected focused checks, then run the final sweep again.

Evidence must bind to Work Order, exact base/candidate SHA, commands/workflows, results, failures/corrections, security findings, changed paths and unresolved risks.

## 9. PR

Substantial work integrates through a PR unless repository policy explicitly permits another governed path. The PR must identify the Work Order, authorized base when required, exact current head/evidence and preservation-sensitive facts.

Do not arm auto-merge when Sol/HIVE exact-head audit is still required.

## 10. EXACT-HEAD AUDIT

Review the exact candidate SHA. Use delta-first analysis against canonical sources and the Work Order. Inspect invalidated evidence, tests/CI, security, data integrity, architectural contracts, scope, review threads and ruleset state.

Allowed verdicts: `APPROVED`, `CORRECTION_REQUIRED`, `BLOCKED`.

If HEAD moves after review, audit again.

## 11. CHECKPOINT DELTA

After acceptance, determine whether the Work Order authorizes canonical checkpoint mutation. If not, record only a proposed delta/evidence reference. Never mutate canonical truth merely because implementation succeeded.

## 12. MERGE

Follow repository policy. HIVE currently uses protected main and squash-only integration. Sol may perform exact-head squash merge when canonical governance allows and all required preconditions are green.

After merge, verify:

- resulting default-branch SHA;
- expected parent/lineage;
- required post-merge CI/evidence;
- no unintended scope drift.

## 13. NEXT

Only after the current increment is accepted and canonical truth is reconciled may the next necessary increment be defined.

## Routine failures vs blockers

Routine in-scope failures such as red tests, CI failure, assertion mismatch, lint/typecheck errors or elapsed execution time are corrections, not blockers.

`BLOCKED` is reserved for a concrete external/canonical/capability condition that prevents safe continuation.

## Stop conditions

Every substantial prompt must contain a concrete STOP CONDITION. For Universal GEF adoption use the canonical states:

- `GEF_ADOPTION_IN_PROGRESS`
- `GEF_ADOPTION_EXACT_HEAD_EVIDENCE_REQUIRED`
- `GEF_ADOPTION_BLOCKED_BY_CAPABILITY_GAP`
- `GEF_V1_ADOPTED_READY_FOR_GOVERNED_DEVELOPMENT`
