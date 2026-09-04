# Work Order — `<WORK-ORDER-ID>`

## Identity

- ID: `<WORK-ORDER-ID>`
- Title: `<title>`
- Status: `DRAFT | APPROVED | IN_PROGRESS | BLOCKED | READY_FOR_REVIEW | CLOSED`
- Branch: `<short-branch>`
- PR: `<number or pending>`
- Owner/authority: `<owner or NEEDS OWNER CONFIRMATION>`

## Source lock

- Repository: `<owner/name>`
- Base branch: `<branch>`
- Baseline Git SHA: `<40-char SHA>`
- Context Lock: `.engineering/context-locks/<WORK-ORDER-ID>.md`
- Latest approved checkpoint: `<path and status>`

## Objective and boundaries

### Objective

`<one concrete outcome>`

### In scope

- `<allowed path or behavior>`

### Out of scope

- product features;
- broad refactor or cleanup;
- migration, release or canonical promotion unless explicitly approved;
- `<other exclusions>`.

## Acceptance criteria

- [ ] `<objective criterion>`
- [ ] Baseline and AFTER evidence are recorded.
- [ ] No unexplained product behavior change.
- [ ] Required checks and review handoff are recorded.

## Risk and stop conditions

- Risk: `LOW | MEDIUM | HIGH | CRITICAL`
- Data/migration impact: `<NONE or explicit impact>`
- Stop if: stale context, scope expansion, destructive unknown, or unresolved
  HIGH/CRITICAL issue.

## Validation plan

| Area | Command/workflow | BEFORE | AFTER |
| --- | --- | --- | --- |
| Tests | `<command>` | `PENDING` | `PENDING` |
| Lint/typecheck | `<command>` | `PENDING` | `PENDING` |
| Build | `<command>` | `PENDING` | `PENDING` |
| Integration/E2E | `<command/workflow>` | `PENDING` | `PENDING` |

## Deliverables

- Work Order: this file;
- Context Lock: `.engineering/context-locks/<WORK-ORDER-ID>.md`;
- Evidence Bundle: `.engineering/reports/EVIDENCE-BUNDLE-<WORK-ORDER-ID>.md`;
- Cleanup/report artifacts as applicable;
- Checkpoint Delta: `.engineering/reports/CHECKPOINT-DELTA-<WORK-ORDER-ID>.md`.

## Handoff

- Commit: `<SHA or pending>`
- Head SHA audited: `<SHA or pending>`
- PR URL: `<URL or pending>`
- Auto-merge: `DISABLED | PENDING GOVERNANCE | AUTHORIZED`
- Sol/independent review: `AWAITING | APPROVED | REJECTED`
