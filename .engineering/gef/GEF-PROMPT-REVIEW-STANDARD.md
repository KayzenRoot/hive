# GEF Universal Prompt & Review Standard — HIVE

## Purpose

This is the operational standard for future HIVE prompts and reviews after Universal GEF reconciliation. It is an engineering workflow adapter around HIVE canonical governance. It never overrides Project Brain or an approved Work Order.

## Prompt compilation rule

Do not send an executor a repository biography. Compile the smallest self-contained execution packet that preserves correctness.

For substantial work, prompts should use this order when applicable:

1. `OBJECTIVE`
2. `CONTEXT`
3. `SOURCE CHECK`
4. `WORK ORDER`
5. `CONTEXT LOCK`
6. `SCOPE`
7. `OUT OF SCOPE`
8. `FILES/AREAS TO READ`
9. `ALLOWED/PRESERVED PATHS`
10. `REQUIREMENTS`
11. `ARCHITECTURE RULES`
12. `SECURITY CONSTRAINTS`
13. `EXECUTION WAVES / CRITICAL PATH`
14. `ACCEPTANCE CRITERIA`
15. `TESTS`
16. `EVIDENCE`
17. `ROLLBACK/RECOVERY`
18. `DELIVERABLES`
19. `REVIEW FORMAT`
20. `STOP CONDITION`

For very large but bounded work, include a Marathon Execution Pack and prefer 2-3 large dependency-safe gates over many tiny handoffs.

## Context economy

Each prompt should compile, when useful:

- Implementation Seed Tree;
- File Intent Capsule;
- Brownfield Patch Intent Capsule;
- Executor Navigation Map;
- Decision Closure Capsule;
- Execution Waves;
- Validation Reuse Plan;
- Critical Path.

Do not repeatedly require rereading the whole repository when a smaller exact source set is enough. Never omit a canonical source whose meaning is load-bearing to the increment.

## Brownfield rule

Before changing existing code or governance:

- inspect current behavior and history;
- map collisions;
- preserve user work and project-native conventions;
- prefer additive reconciliation;
- do not mass-format or rename for GEF aesthetics;
- do not fabricate historical GEF execution;
- separate adoption defects from product technical debt.

## Testing rule

Use real project commands. Scale assurance to change risk:

`STRUCTURAL -> FOCUSED -> IMPACTED -> BOUNDARY/INTEGRATION -> RISK EXPANSION -> FULL CANDIDATE`

During implementation, prefer focused checks. Run the release-critical/full candidate sweep once after the implementation stabilizes. If that sweep finds an in-scope defect, fix it, rerun the affected focused check, then rerun the final sweep.

A failed test is a defect/evidence fact, not a documentation problem.

## Evidence rule

Every approval-relevant claim must have load-bearing evidence. Evidence records should bind:

- Work Order;
- exact base;
- exact candidate HEAD;
- commands/workflow run IDs;
- test/build/lint/typecheck results;
- security scan/results;
- changed-file inventory;
- failures/corrections;
- unresolved risks.

Never coerce missing data to zero or PASS. `UNKNOWN != PASS`.

## Review pipeline

Use a delta-first exact-head review:

1. Resolve canonical source and current checkpoint.
2. Resolve PR/candidate identity and exact HEAD.
3. Verify base/branch/Work Order/Context Lock.
4. Inspect changed files and scope.
5. Determine which accepted evidence was invalidated by the diff.
6. Inspect architecture, security, data integrity and contract changes.
7. Verify focused and required full tests/evidence.
8. Verify hosted exact-head required checks.
9. Check review threads, auto-merge and ruleset state.
10. Issue one verdict anchored to the exact candidate SHA.

If the candidate HEAD moves, the verdict is stale and must be re-audited.

## Review verdicts

Only these verdicts are valid:

### APPROVED

Use only when:

- candidate SHA is identified and unchanged;
- required checks are complete and green;
- CRITICAL=0;
- HIGH=0;
- no unresolved scope violation;
- no unresolved architecture/security/data-integrity defect;
- no evidence mismatch;
- no preservation violation;
- no stale-head mismatch.

### CORRECTION_REQUIRED

Use when the candidate has a fixable defect inside the authorized increment. The corrective increment must address only the audited findings and must reuse the same Work Order/PR when safe. Do not advance to the next implementation increment until correction is validated.

### BLOCKED

Use only when a concrete external, canonical or capability constraint prevents safe continuation. Ordinary test failures, CI failures, assertion mismatches, lint errors and time already spent are not blockers when they can be fixed inside scope.

## Review response format

A normal Sol review should state, compactly:

- verdict;
- exact candidate/base/PR identity;
- findings ordered by severity;
- positive evidence that remains valid;
- tests/CI/ruleset/threads state;
- what must happen next;
- project progress estimate only when it can be defended separately from GEF adoption progress.

If correction is required and an executor prompt is the next legal action, generate one bounded corrective prompt, not a chain of speculative prompts.

## Merge rule

Follow repository policy. HIVE currently uses protected main and squash-only promotion. Sol may perform an exact-head squash merge only when current project governance authorizes it and all required preconditions are green. After merge, verify the new default-branch SHA and mandatory post-merge evidence before advancing.

## Checkpoint delta

After accepted work, update canonical checkpoint only when the Work Order authorizes that mutation. Otherwise produce a proposed delta/evidence reference and leave canonical truth unchanged.

## STOP CONDITIONS

Every substantial prompt must define a concrete stop. Examples:

- candidate ready for exact-head Sol audit;
- correction proven and same PR green;
- external capability gap precisely documented;
- merge/post-merge verified;
- final version completion when canonical DoD permits it.

No executor should stop merely because the run is long if the remaining work is ordinary in-scope correction.
