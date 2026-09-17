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
