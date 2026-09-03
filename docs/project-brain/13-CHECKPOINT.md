# 13 — CHECKPOINT

## STATUS
RERANKING FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE

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
- Durable project-scoped retrieval corpus implemented over repository file/symbol metadata and ingested derived task text.
- Deterministic chunk/reference provenance and bounded lexical candidate generation implemented.
- Retrieval remains isolated by project and exposes provenance/source-kind metadata.
- Corpus promotion revalidates exact Git HEAD, tracked inventory and source bytes fail-closed; stale/racing generations do not replace the prior valid corpus.
- Duplicate READY task content is collapsed at candidate selection without destroying distinct durable task provenance or cross-project isolation.
- Retrieval integration survives Redis restart and API restart without losing canonical corpus truth.
- Accepted lexical benchmark has 4 queries, recall@1 1.0, recall@5 1.0, MRR 1.0, zero critical misses and two-run reproducibility.
- Review evidence is consolidated and includes validation, integration, security and observed non-blocking warnings; bounded service-log capture is available for audit.
- Protected-main Ruleset requires Validate, Integration health and Review Evidence for PRs, requires thread resolution and allows squash-only with no bypass.
- PR #25 was approved at exact head `ee1b016b135d30d48d99d298788568e116396b23` and squash-merged as `e15690042041372febb565169e7bb80bef308337`.
- Post-merge CI run `33641440244` passed on `main` for exact SHA `e15690042041372febb565169e7bb80bef308337`.
- Provider-independent embedding adapter implemented.
- OpenAI-compatible embedding transport is replaceable and disabled/unconfigured by default for local-only operation.
- Durable semantic retrieval state uses PostgreSQL + pgvector.
- Embedding profile identity prevents incompatible model, revision and dimension mixing.
- Semantic sync reuses compatible chunk embeddings and does not make failed or incomplete runs current.
- Corpus and profile changes correctly make semantic state stale.
- Semantic query is bounded, project-scoped and provenance-preserving.
- Malformed provider ordering, dimension mismatch and invalid numeric vectors fail closed.
- Hybrid candidate fusion uses deterministic RRF over bounded lexical and semantic candidates.
- Lexical fallback works when semantic retrieval is disabled, unavailable, stale or provider-failing.
- Duplicate TASK content does not crowd semantic or hybrid candidate sets.
- Dashboard exposes real semantic state and hybrid retrieval results without secrets or fake cost metrics.
- Real integration proves pgvector, semantic sync/query, hybrid fusion, provider failure fallback, stale recovery, project isolation, Redis restart and API restart.
- Accepted lexical baseline remains green.
- Extended semantic/hybrid benchmark passes with hybrid recall@5 1.0, semantic recall@5 1.0, hybrid MRR 1.0 and zero critical misses in the deterministic fixture.
- Semantic challenge recovers relevant context that lexical-only misses or under-ranks in the extended challenge fixture.
- No production-quality claim is made for the deterministic test embedding fixture.
- PR #27 was independently approved at exact head `a74a2f27ea8771b06c6322fe2563968e37af7869` and squash-merged as `825134f1a4d4950ef95f8845941a86f2d65d1359`.
- Post-merge CI run `33664297759` passed on `main` for exact SHA `825134f1a4d4950ef95f8845941a86f2d65d1359`.
- Reviewer `kayzenweb3` is an eligible Write collaborator for the independent approval gate.
- GitHub native auto-merge is enabled for subsequent approval-gated PRs.
- Provider-independent `RerankerAdapter` is implemented over bounded, project-scoped hybrid candidates.
- Deterministic versioned candidate serialization and configurable HTTP rerank transport are implemented behind the adapter.
- Reranking is disabled by default; local-only operation remains valid and no mandatory local reranker was promoted.
- Reranker profile identity excludes secrets while capturing material model, revision and scoring identity.
- Reranked responses preserve lexical, semantic and hybrid provenance plus pre-rerank and post-rerank ranks.
- Deterministic score validation rejects duplicate, missing and out-of-range indexes, non-finite scores and provider model mismatches.
- Default rerank failures preserve the exact hybrid order with null rerank scores; strict failures are bounded and explicit.
- Rerank integration proves project isolation, duplicate TASK collapse, cross-project duplicate isolation and semantic `STALE` preservation.
- Rerank evidence proves no secret-sentinel credential leakage and reproducible two-run ordering identity.
- Accepted lexical, semantic and hybrid baselines remain green; the rerank challenge improves relevant rank without reducing recall@5.
- Rerank benchmark records recall@5 `1.0`, hybrid recall@5 `1.0`, reranked MRR `1.0`, hybrid challenge MRR `0.2`, strict rank improvement and zero critical misses.
- The deterministic rerank fixture proves contract mechanics, not production model quality.
- PR #29 was independently approved at exact head `80ad25dcaae51fbb6a6dad6e0a653eea51d5a3ee` and squash-merged as `fcbf0849a54e0283ed523e09ce18ea31a8bd7849`.
- WO-008-G1 moved auto-merge arming out of GitHub Actions; Review Evidence now verifies user-owned SQUASH auto-merge and rejects Bot/App ownership.
- PR #30 was independently approved at exact head `f8165e1ea9544841b7e67c26d4beecf0e986624f` and squash-merged as `57397ec8f4ffb94fb8e0647e17d648f432430258`.
- Post-merge CI run `33764713691` fired from `push` on exact main SHA `57397ec8f4ffb94fb8e0647e17d648f432430258`; Validate and Integration health passed and Review Evidence was skipped by design.
- Approval-gated user-owned auto-merge now preserves the required post-merge validation flow.

## IN PROGRESS
- Preparing the smallest necessary Context Manager foundation over the approved project registry, canonical governance sources and reranked retrieval pipeline.

## PENDING
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
- Context Manager.
- adaptive token budget.
- progressive disclosure.
- context fingerprints.
- delta context.
- provider/prompt cache adapter layer.
- checkpoint awareness orchestration.
- tool gating integration where not yet end-to-end.

## BLOCKERS
None known after Reranking Foundation approval and post-merge governance validation.

## DECISIONS
See `16-DECISIONS-LEDGER.md`.

## NEXT STEP
Implement the smallest necessary deterministic Context Manager foundation that, for an already-resolved project and task, reads the latest canonical checkpoint first, resolves the relevant scope/Definition of Done/architecture/decisions, invokes the approved bounded reranked retrieval pipeline, and builds a bounded provenance-bearing context capsule with explicit task, project state, constraints, acceptance criteria, relevant governance, relevant files/symbols/tests and retrieval provenance. Use fixed conservative bounds for this increment. Do not add memory lifecycle, adaptive token budgeting, full progressive-disclosure escalation, context fingerprints/delta context, prompt/provider cache, MCP product surface or autonomous executor dispatch in this increment.

## DEFINITION OF DONE
See `15-DEFINITION-OF-DONE.md`.

## BACKLOG
See `14-BACKLOG.md`.
