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

## Engineering Delivery Protocol

For every approved increment, read and follow
`.engineering/ENGINEERING-DELIVERY-PROTOCOL.md` and its templates. The executor
must inspect the repository and canonical checkpoint first, freeze an exact
baseline, create a Context Lock, implement only the approved Work Order, run
the required validation, correct introduced issues, commit, push, open/update
a PR and produce an Evidence Bundle. Use a short branch and the Work Order ID
consistently across the Work Order, branch, PR, Context Lock, Evidence Bundle
and Checkpoint Delta.

Treat executor claims as staged until tests and evidence validate them. Stop on
scope expansion, stale context, unknown destructive effects, an indeterminate
baseline or unresolved HIGH/CRITICAL risk. Never promote canonical checkpoint
or other canonical truth, merge, release or begin cleanup alone. Do not remove
code, dependencies, migrations, endpoints, jobs, flags or contracts merely
because they appear unused; classify them in the cleanup inventory and wait
for a reviewed future Work Order. Return the final review in Brazilian
Portuguese.
