# 13 — CHECKPOINT

## STATUS
REPOSITORY INDEXING APPROVED / V0.1 IMPLEMENTATION ACTIVE

## VERSION
HIVE V0.1 — Foundation

## PHASE
5 — Implementation

## OBJECTIVE
Create a local-first autonomous context, memory, retrieval, token optimization and control platform for large LLM-assisted software projects.

## SCOPE
See `03-SCOPE.md`.

## COMPLETED
- Product objective defined.
- V0.1 scope frozen at architecture/source level.
- Core architecture defined.
- ACCE optimization strategy defined.
- Control Center promoted to V0.1 required capability.
- Redis-compatible hot cache promoted to V0.1.
- Autonomous prompt intake/execution flow defined.
- MCP/skills separation defined.
- Governance and validation principles defined.
- Local Docker persistence strategy defined.
- Canonical Project Brain installed in Git and protected by deterministic SHA256 verification.
- Professional GitHub repository foundation configured.
- Bootstrap PR #1 approved and merged through protected `main`.
- Docker Compose foundation validated with PostgreSQL + pgvector, Redis hot cache, API health and Control Center health shell.
- Secondary-disk persistence configuration documented for Windows and Linux.
- Deterministic CI and Docker integration health are required checks for `main`.
- Release workflow validates tag/version coherence, matching notes, tests, integration smoke and versioned ZIP + SHA256 packaging.
- `v0.0.1-bootstrap` published as a GitHub pre-release with validated downloadable assets.
- Versioned PostgreSQL business-schema migration foundation implemented with startup schema gating.
- Durable Project Registry implemented in PostgreSQL.
- Multiple local projects can be registered, listed, inspected and re-inspected through `/api/v1/projects`.
- Project source access is constrained to an explicit read-only `HIVE_PROJECTS_ROOT`.
- Project path traversal, symlink escape and duplicate physical identity are deterministically blocked.
- Git branch, HEAD, detached state, working-tree status and language stack are inspected without an LLM.
- Project states READY, OFFLINE, DEGRADED and BLOCKED have tested deterministic semantics.
- Project Registry remains durable across Redis loss/restart and API/container recreation.
- HIVE Control Center exposes a functional real-data Project Fleet with registration and re-inspection.
- Real-Git Linux integration coverage validates canonical identity, security-boundary transitions and recovery.
- Durable Task/Prompt Intake is implemented and bound to `project_id`.
- PDF, TXT, Markdown and structured text intake is implemented with bounded validation.
- Original task artifacts are preserved by SHA-256 content address with lossless Zstandard storage.
- CAS deduplication, exact-byte recovery, corruption fail-closed behavior and project-scoped access are tested.
- Deterministic derived-text extraction and explicit extraction status are implemented.
- HIVE Control Center exposes real intake status, original download, derived-text preview and CAS metrics.
- PR #17 was approved at exact head `3fea9f68aa4a09b106ed4cde0f5f2d1d084dc2a7` and merged as `152edf2423a257cb27e8ae070551c574c4ede6bc`.
- Post-merge CI run #47 passed on `main` for `152edf2423a257cb27e8ae070551c574c4ede6bc`.
- Local Verified Runner foundation implemented with schema-constrained staged change sets, deterministic path/admission/application/changed-file verification, per-mutation SHA-256 revalidation and non-canonical staged results.
- ToolPolicy enforces executable allowlists, normalized shell blocking, explicit subprocess environment allowlisting, bounded stdout/stderr capture, timeouts and model/effort evidence.
- Windows path security covers traversal, symlink escape, reserved device names, ADS, trailing dot/space and case aliases with regression tests.
- Deterministic Module Registry/Test Map include the Local Verified Runner, and the Windows validation harness is UTF-8/console-safe.
- PR #21 was approved at exact head `22f6996fd7f5b3e2537d1009c91929bde96c4c13` and merged as `80aa34a1c5d9a4060fbdf07bc23f93340a54d76b`.
- Post-merge CI run `33508738134` passed on `main` for `80aa34a1c5d9a4060fbdf07bc23f93340a54d76b`.
- Deterministic repository indexing foundation implemented with Git-aware tracked-file inventory, stable SHA-256 content identity, incremental add/change/remove/reuse semantics and Python AST symbol metadata.
- Repository indexing metadata and provenance are durable in PostgreSQL and remain project-scoped through composite same-project constraints.
- Repository indexing fails closed on unsafe tracked paths, source/Git inventory mutation and Python syntax failure without corrupting the prior valid index.
- Real Git/PostgreSQL integration proves incremental reuse, add/change/remove, qualified Python symbols, project isolation, cross-project FK rejection, transactional rollback and restart persistence.
- PR #23 was approved at exact head `be71bc99d715d623b895bf4e1e7c95d3586ad053` and squash-merged as `ee2580473a0226ad38a40695366129f5473fa974`.
- Post-merge CI run `33565088918` passed on `main` for `ee2580473a0226ad38a40695366129f5473fa974`.

## IN PROGRESS
- Preparing the smallest necessary project-scoped retrieval corpus and lexical candidate-generation foundation for hybrid retrieval.

## PENDING
- retrieval.
- memory.
- ACCE beyond the intake/storage foundation.
- MCP server product surface.
- autonomous execution beyond the Local Verified Runner foundation.
- telemetry.
- full Control Center.
- comprehensive retrieval/token/storage benchmarks.
- stabilization.
- full local deployment validation.
- backup/recovery validation.
- final documentation.
- final V0.1 review.

## BLOCKERS
None known after Repository Indexing approval.

## DECISIONS
See `16-DECISIONS-LEDGER.md`.

## NEXT STEP
Implement the smallest necessary retrieval foundation for V0.1: build a project-scoped retrieval corpus over repository file/symbol metadata and ingested derived text, add deterministic chunk/reference provenance and lexical candidate generation, and establish the benchmark/evidence surface needed for later pgvector semantic retrieval and reranking. Do not add memory, Context Manager orchestration, MCP product surface or autonomous retrieval execution in this increment.

## DEFINITION OF DONE
See `15-DEFINITION-OF-DONE.md`.

## BACKLOG
See `14-BACKLOG.md`.
