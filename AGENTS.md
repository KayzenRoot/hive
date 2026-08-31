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

## Local conventions

- Backend code and tests live under backend/.
- Dashboard code lives under dashboard/.
- Operational scripts live under scripts/.
- Documentation is concise and should link to canonical sources instead of
  duplicating them.
