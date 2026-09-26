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

## HIVE v1.0.3 context-first work and prompt contract

The current HIVE executor-context baseline is the published **v1.0.3** read-only MCP surface. This is a context and prompt-preparation baseline; it does **not** change this repository's product dependency, runtime, compatibility pin, or HIVE V1/V2 integration contract. Keep those project-specific pins unchanged unless their own authorized Work Order validates and admits an upgrade. This repository's Git state, approved checkpoint, source hierarchy, decisions, scope, and active Work Order remain authoritative over HIVE-derived memory/context.

### Preflight

1. Confirm the exact repository, branch, HEAD/base SHA, and active Work Order or issue before building context. Read this repository's checkpoint/source hierarchy and the Work Order's scope, allowed files, acceptance criteria, and stop condition.
2. When HIVE MCP is available in this execution surface, verify the handshake and the reported v1.0.3 context baseline. Resolve this repository by its actual registered identity; use only an existing, canonical task ID. Never guess a project or task ID.
3. Use only read-only tools actually exposed by the handshake. The v1.0.3 reference surface includes `project.list`, `project.status`, `context.build`, `context.search`, `memory.search`, `memory.get`, and `checkpoint.read`. Build task context only for a valid task ID. Retrieve the minimum context needed for this Work Order; do not load unrelated history or the whole corpus.
4. Record the exact Git basis and only HIVE version, project/task identity, source references, or context fingerprint actually returned. A HIVE summary is derived context, not canonical approval or evidence that an unobserved check passed.
5. If HIVE is absent, stale, mismatched, or not exposed here, label it accurately and continue from canonical repository sources whenever the Work Order permits. Finish independent authorized work and do not stop for routine confirmation. Mark BLOCKED only when an explicit gate requires unavailable HIVE evidence. Never claim local HIVE access from a hosted execution surface, or vice versa.
6. Do not synchronize/reindex a corpus, create tasks, write a database, call a provider, or mutate remote/runtime state unless the active Work Order explicitly authorizes that operation.

### Compact HIVE-grounded executor prompt

When preparing a Codex/Cursor or other executor prompt, include only the task-relevant context and these fields:

- **Identity:** repository/path, Work Order/issue, branch, exact base and current HEAD.
- **Authority:** canonical checkpoint and source paths; the active Work Order and Context Lock, if present.
- **HIVE context:** v1.0.3 handshake status, verified project/task IDs, and returned source references/fingerprint — or the truthful status `UNAVAILABLE`, `STALE`, or `NOT_REQUIRED`.
- **Work:** objective, exact allowed change surface, acceptance criteria, required focused checks, evidence to return, exclusions, and stop condition.
- **Execution direction:** complete every authorized step, fix review findings within scope, perform the required review, and report which checks actually ran. Do not ask for routine confirmation; do not widen scope or claim unperformed work.

Prefer canonical file paths and short HIVE context references over copying full documents or chat history. Keep stable policy, Work Order-specific requirements, and volatile runtime evidence in separate, compact sections.

HIVE repository self-hosting rule: HIVE MCP context may describe this repository, but only the exact Git checkout, approved Project Brain checkpoint, and active Work Order authorize repository changes.

### Prompt PDF delivery

For HIVE-related chats and executor handoffs, deliver every requested execution, correction, continuation, or audit prompt as a polished downloadable PDF. Do not place the complete prompt in a copyable chat code block. Keep the chat response to the review/verdict and a short summary with the PDF download link. The PDF is the complete execution artifact and must preserve the approved Work Order, Context Lock, HIVE preflight, canonical basis, scope, exclusions, acceptance criteria, tests, evidence, deliverables, review format, and stop condition. Render and visually inspect every page before delivery. A PDF must never conceal a missing authorization, failed gate, stale source, or unresolved stop condition. If PDF generation is unavailable, state that clearly rather than silently substituting a copyable prompt.
