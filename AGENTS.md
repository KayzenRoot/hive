# HIVE agent guidance

## Source of truth

Canonical project decisions and scope live in `docs/project-brain/`. Preserve their meaning. Read the latest approved checkpoint first, then decisions, scope, Definition of Done, architecture, security/policy, current Work Order/Context Lock, requirements and only then remaining supporting sources.

GEF is an execution/review/evidence overlay, not a second source of product truth. For substantial work also read:

- `.engineering/gef/GEF-POLICY.md`
- `.engineering/gef/GEF-EXECUTION-PROTOCOL.md`
- `.engineering/gef/GEF-PROMPT-REVIEW-STANDARD.md`
- `.engineering/gef/GEF-CURRENT.json`

## Execution rules

- Inspect repository state before changing files.
- Keep changes inside the current approved increment.
- Preserve active exact-base Work Orders; do not move/rewrite their authority silently.
- Substantial work requires a stable Work Order or equivalent HIVE execution contract.
- Use a Context Lock for project/base/HEAD/source/scope binding when useful.
- Prefer deterministic tools before model reasoning.
- Treat executor claims as staged until tests and evidence validate them.
- `UNKNOWN` is not `PASS`.
- Never commit secrets, `.env` files, or user-owned runtime data.
- Run relevant focused tests while implementing, then required candidate/full checks according to risk.
- Do not weaken tests, CI, branch protection, security or governance to obtain green status.
- Do not merge or publish releases unless current HIVE governance authorizes promotion.

## Review rules

Use exact-head delta review. Valid verdicts are `APPROVED`, `CORRECTION_REQUIRED`, and `BLOCKED`.

A fixable defect inside the approved increment is `CORRECTION_REQUIRED`, not `BLOCKED`. Approval requires exact candidate identity, required checks, CRITICAL=0, HIGH=0, no unresolved scope/preservation/evidence mismatch and no stale-head mismatch. If HEAD changes, audit again.

## Local conventions

- Backend code and tests live under `backend/`.
- Dashboard code lives under `dashboard/`.
- Operational scripts live under `scripts/`.
- Canonical product governance lives under `docs/project-brain/`.
- GEF engineering state lives under `.engineering/gef/`.
- Documentation should link to canonical sources instead of duplicating them.
