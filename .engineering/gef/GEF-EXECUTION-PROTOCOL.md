# GEF V1 Execution Protocol — HIVE

## Pipeline

`REQUEST -> Source Drift Sentinel -> Task Class -> Context Radius -> UPIR/Task Manifest -> Decision Freeze Capsule -> Context Slice -> Patch Recipe -> Budgets -> SOURCE_MATCH -> bounded implementation -> A0/A1/A2 -> one final push -> A3 hosted gates + HEDS Delta -> exact-head verdict`

## Source Drift Sentinel

Before implementation, bind the pack to repository identity, authorized base/head, current checkpoint identity and material contracts. If any binding changed, stop `SOURCE_CONFLICT` or regenerate the pack.

## Execution Pack contract

Every implementation pack contains:

- project, work order, branch/PR, authorized base/head
- task class, context radius, assurance level
- Accepted/Frozen decisions/findings
- one Open Goal/Finding
- resolved Root Cause / Engineering Decision
- Patch Map with allowed files/symbols
- Prescribed Algorithm and postconditions
- Forbidden Shortcuts
- required positive/negative/regression/eval tests
- search, patch, retry and token/output budgets
- local assurance A0-A2
- one-shot publication target
- compact machine output
- exact STOP condition

## Correction Pack

```text
MODE: CORRECTION
TASK_CLASS: T1|T2
CONTEXT_RADIUS: C0|C1
ACCEPTED_AND_FROZEN: [...]
ONLY_OPEN_FINDING: CR-XX
ROOT_CAUSE: <resolved>
DECISION: <resolved>
TARGET_SYMBOLS: [...]
PRESCRIBED_TRANSFORM: [...]
FORBIDDEN: [...]
REQUIRED_TESTS: [...]
SEARCH_BUDGET: <count>
PATCH_BUDGET: <files/LOC>
RETRY_BUDGET: <count>
LOCAL_ASSURANCE: A0-A2
PUBLICATION: one final push
OUTPUT: compact JSON
STOP: COMPLETE_CANDIDATE | SOURCE_CONFLICT | SCOPE_EXPANSION_REQUIRED | BLOCKED_EVIDENCE | NEEDS_ARCHITECTURE
```

## SOURCE_MATCH

Implementation may start only when:

- authorized base/head still match,
- current canonical checkpoint/decisions are compatible,
- target paths/symbols exist or the pack explicitly authorizes creation,
- no newer accepted decision invalidates the recipe.

Failure is not permission to explore broadly. Escalate radius only with a concrete dependency or source conflict.

## Assurance

- `A0`: syntax/static/basic local checks.
- `A1`: focused local tests.
- `A2`: impacted tests/evals selected conservatively.
- `A3`: hosted full CI/security/platform/release gates required by HIVE.
- `A4`: HEDS independent semantic assurance.

HIVE starts GEF with shadow assurance ON. Existing full hosted checks remain authoritative until carry-forward/test-skipping is explicitly promoted after measured shadow cycles.

## Machine output

Executor output should prefer compact structured data: changed files, tests/evals, exit codes, evidence paths/digests, remaining blockers, requested/applied model where runtime exposes it, and STOP state. Long narrative is secondary and should be deterministically derivable when possible.
