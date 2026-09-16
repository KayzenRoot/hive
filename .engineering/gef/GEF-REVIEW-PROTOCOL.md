# GEF V1 Universal Exact-Head Review Protocol — HIVE

## Principle

Review is evidence-bound, delta-first and exact-head. Executor narrative is useful context, never proof by itself.

## Review entry requirements

Before issuing a final verdict, resolve when applicable:

- repository/PR identity;
- base branch and authorized base SHA;
- exact candidate HEAD;
- Work Order / Context Lock;
- changed-file inventory and diff;
- current canonical checkpoint and applicable source hierarchy;
- required CI/test/evidence state;
- ruleset/merge policy;
- unresolved review threads;
- auto-merge state;
- CRITICAL/HIGH findings.

If exact candidate identity cannot be established, do not approve.

## Delta-first pipeline

1. Read current accepted checkpoint and source authority.
2. Confirm candidate base/head/branch/PR and stale-head status.
3. Check Work Order scope and preservation boundaries.
4. Inspect changed files, contracts, data flows and architecture seams.
5. Identify accepted evidence invalidated by the diff.
6. Audit security, canonical data, project isolation, error handling and rollback implications proportionate to risk.
7. Inspect relevant focused checks and full candidate evidence.
8. Inspect hosted exact-head checks.
9. Verify review threads, ruleset and merge/auto-merge state.
10. Issue a verdict anchored to the exact candidate SHA.

If HEAD changes, repeat the exact-head audit for the new candidate.

## Verdicts

### APPROVED

Use only when all applicable facts are true:

- candidate SHA is known and current;
- required checks are complete and green;
- CRITICAL=0;
- HIGH=0;
- scope is satisfied without unauthorized expansion;
- no preservation violation exists;
- no architecture/security/data-integrity defect remains;
- evidence matches the claims it is used to prove;
- no unresolved stale-head mismatch exists;
- required review threads are resolved;
- merge state complies with repository policy.

### CORRECTION_REQUIRED

Use when one or more defects are fixable inside the authorized increment.

The correction should:

- remain on the same Work Order/PR when safe;
- address only audited findings and directly related regressions;
- preserve accepted evidence that remains valid;
- use focused tests during correction;
- finish with required full/exact-head evidence;
- not advance the next product increment until re-audited.

### BLOCKED

Use only when a concrete external, canonical or capability constraint prevents safe continuation, such as unavailable required permissions, irreconcilable canonical contradiction, unavailable required external service with no valid substitute, or an active governance dependency that cannot be safely bypassed.

Do not classify ordinary test failures, CI failures, assertion errors, implementation defects or run duration as BLOCKED when they are fixable inside scope.

## Severity handling

- CRITICAL unresolved: approval forbidden.
- HIGH unresolved: approval forbidden.
- MEDIUM: must be resolved or explicitly accepted by applicable project governance before release-critical approval.
- LOW: may be accepted when non-blocking and recorded.

Do not down-rank findings merely to progress faster.

## Evidence validity

A prior proof may be carried forward only when the current diff does not invalidate the behavior, contract, fixture, dependency, environment assumption or evidence lineage it proved.

When uncertain, rerun the smallest relevant check. Release-critical closure may require the full candidate sweep.

`UNKNOWN` is not PASS. A hash alone proves only byte integrity, not correctness or signing.

## Review response

A concise Sol review should report:

- `VERDICT`;
- exact PR/base/head;
- blocking findings ordered by severity;
- material positive evidence retained;
- CI/tests/evidence/ruleset/thread state;
- next legal action;
- product progress separately from GEF/adoption progress when estimates are requested.

If a correction prompt is required, generate one bounded executor prompt that closes all known in-scope findings in as few dependency-safe gates as practical.

## Merge and post-merge

When HIVE governance authorizes Sol direct promotion and all exact-head preconditions are green, merge using the repository's current allowed method. Immediately verify the new default-branch SHA, expected lineage and mandatory post-merge CI/evidence.

Do not advance after a failed post-merge gate until the failure is understood and resolved.

## Final project completion

GEF cannot declare HIVE complete. HIVE V0.1 completion is governed by the canonical Definition of Done and final canonical checkpoint/review process.
