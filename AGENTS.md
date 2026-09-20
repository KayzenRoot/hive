# HIVE agent guidance

## Source of truth

Canonical project decisions and scope live in docs/project-brain/. Preserve
their meaning. The latest approved checkpoint has precedence over the decisions
ledger, scope, Definition of Done, architecture, requirements, and remaining
sources.

## Execution rules

- Inspect repository state before changing files.
- Keep changes inside the current approved increment.
- Prefer deterministic tools before model reasoning.
- Treat executor claims as staged until tests and evidence validate them.
- Never commit secrets, .env files, or user-owned runtime data.
- Run the relevant tests, lint, typecheck, build, and configuration checks.
- Do not merge or publish releases without explicit approval.

## Review self-healing rule

- During Sol review, classify each defect as `SELF_HEALABLE` or `EXECUTOR_REQUIRED`.
- `SELF_HEALABLE` means a small, localized, low-risk defect that can be corrected directly with
  the currently available repository tools and validated objectively without secrets, local-only
  state, destructive actions, migrations, scope expansion, architecture changes, approved-decision
  changes, or evidence unavailable to the reviewer.
- For a `SELF_HEALABLE` defect, Sol applies the smallest correction, runs or obtains the relevant
  validation/evidence, keeps the correction inside the same logical increment/PR when safe, and
  continues the review. Once clean, the same review should provide the next authorized executor
  prompt instead of spending a Codex round on the trivial correction.
- `EXECUTOR_REQUIRED` covers defects that require local execution, heavy implementation, secrets,
  migrations, destructive or irreversible actions, broader architectural/scope decisions, or
  evidence Sol cannot produce from the available tools. In that case the verdict is
  `CORRECTION REQUIRED` and only the corrective delta is issued; no later implementation increment
  advances until the correction is validated.
- Self-healing never bypasses protected `main`, required tests/checks, Review Evidence, canonical
  promotion rules, STOP CONDITIONs, or HIGH/CRITICAL defect gates, and must not include unrelated
  cleanup.

## Maintenance and release rules

- Release-affecting changes must keep version and release metadata coherent.
  Run `python scripts/verify_release_metadata.py` and
  `python scripts/validate.py` before handing off.
- The supported stable line is 1.0.x; release numbering follows
  docs/VERSIONING.md and maintenance follows docs/MAINTENANCE.md.
- Never rewrite historical release notes, historical CHANGELOG entries, or
  accepted Project Brain history to match a newer version.
- Release tags are immutable by policy and must target the exact accepted
  release commit; never move or recreate a published tag.
- Release metadata, CHANGELOG headings, and `docs/releases/vX.Y.Z.md` status
  lines are validated deterministically; never hand-edit around the verifier.

## Local conventions

- Backend code and tests live under backend/.
- Dashboard code lives under dashboard/.
- Operational scripts live under scripts/.
- Documentation is concise and should link to canonical sources instead of
  duplicating them.
