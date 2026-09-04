# 16 — DECISIONS LEDGER

## HIVE-ADR-001 — Local-first
**Status:** Accepted  
HIVE V0.1 runs locally and does not require a VPS.

## HIVE-ADR-002 — Docker-first
**Status:** Accepted  
Primary packaging/deployment uses Docker Compose.

## HIVE-ADR-003 — PostgreSQL durable state
**Status:** Accepted  
PostgreSQL is the durable structured store.

## HIVE-ADR-004 — pgvector initially
**Status:** Accepted  
Use pgvector for V0.1 vector retrieval before introducing an additional vector database.

## HIVE-ADR-005 — Redis is hot cache
**Status:** Accepted  
Redis-compatible cache is required in V0.1 but is not canonical truth.

## HIVE-ADR-006 — Content-addressable storage
**Status:** Accepted  
Large/artifact data uses content hashing and deduplication where practical.

## HIVE-ADR-007 — Zstd
**Status:** Accepted  
Zstandard is the default lossless compression strategy for eligible stored blobs.

## HIVE-ADR-008 — Deterministic first
**Status:** Accepted  
Do not spend LLM tokens on tasks reliably solved by deterministic code/tools.

## HIVE-ADR-009 — Progressive disclosure
**Status:** Accepted  
Context begins small and expands only when necessary.

## HIVE-ADR-010 — Canonical source protection
**Status:** Accepted  
Summaries/embeddings are derived representations; canonical source remains reconstructible and protected.

## HIVE-ADR-011 — Executor claims are staged
**Status:** Accepted  
Executor assertions do not become canonical without validation/provenance.

## HIVE-ADR-012 — MCP as primary universal agent interface
**Status:** Accepted  
HIVE Core remains independent of MCP internally, but MCP is a primary integration surface.

## HIVE-ADR-013 — Skills are behavioral adapters
**Status:** Accepted  
Skills instruct agents how to consume HIVE; skills do not contain the main persistence/intelligence engine.

## HIVE-ADR-014 — Full Control Center is V0.1
**Status:** Accepted  
Real-time/near-real-time operational dashboard is a required core capability.

## HIVE-ADR-015 — Autonomous context use
**Status:** Accepted  
Users should not need to manually request memory/RAG/cache/context optimization for each task.

## HIVE-ADR-016 — Optimize subject to quality
**Status:** Accepted  
Token/storage optimization is subordinate to correctness and validated quality.

## HIVE-ADR-017 — Provider independence
**Status:** Accepted  
LLM, embedding, reranking and cache-provider-specific behavior is behind replaceable adapters.

## HIVE-ADR-018 — Git remains source-code history
**Status:** Accepted  
HIVE does not replace Git or store redundant full repository snapshots by default.

## HIVE-ADR-019 — Single-account GitHub stage-gated governance
**Status:** Accepted  
The sole operational GitHub identity is `KayzenRoot`. The prior requirement that Sol review from a second independent GitHub account (`kayzenweb3`) is superseded. Executor and Sol remain distinct logical roles: the executor stops with required checks green and native auto-merge disabled; Sol audits the exact HEAD; only Sol approval may arm user-owned SQUASH auto-merge. Required checks Validate, Integration health and Review Evidence, plus post-merge CI on `main`, remain mandatory. Protect main keeps deletion protection, non-fast-forward, pull-request requirement, thread resolution, squash-only merge and zero bypass. Native required approving review count is 0; last-push approval and extra unattributed-change approval are disabled because they cannot be satisfied by a second independent GitHub identity. Native GitHub Approve is not the quality gate. This is an explicit usability tradeoff accepted by the user.
