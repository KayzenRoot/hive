# 16 - DECISIONS LEDGER

- HIVE-ADR-001 Local-first - HIVE V0.1 runs locally and does not require a VPS.
- HIVE-ADR-002 Docker-first - primary packaging/deployment uses Docker Compose.
- HIVE-ADR-003 PostgreSQL durable state - PostgreSQL is the durable structured
  store.
- HIVE-ADR-004 pgvector initially - use pgvector for V0.1 vector retrieval
  before introducing another vector database.
- HIVE-ADR-005 Redis is hot cache - required in V0.1 but not canonical truth.
- HIVE-ADR-006 Content-addressable storage - large/artifact data uses content
  hashing and deduplication where practical.
- HIVE-ADR-007 Zstd - default lossless compression for eligible stored blobs.
- HIVE-ADR-008 Deterministic first - do not spend LLM tokens on deterministic
  tasks.
- HIVE-ADR-009 Progressive disclosure - context begins small and expands only
  when necessary.
- HIVE-ADR-010 Canonical source protection - summaries/embeddings are derived;
  canonical source remains reconstructible and protected.
- HIVE-ADR-011 Executor claims are staged - assertions do not become canonical
  without validation/provenance.
- HIVE-ADR-012 MCP as primary universal agent interface - HIVE Core remains
  independent internally.
- HIVE-ADR-013 Skills are behavioral adapters - they do not contain the main
  persistence/intelligence engine.
- HIVE-ADR-014 Full Control Center is V0.1 - real-time/near-real-time operation
  is required.
- HIVE-ADR-015 Autonomous context use - users should not manually request
  memory/RAG/cache/context optimization for each task.
- HIVE-ADR-016 Optimize subject to quality - optimization is subordinate to
  correctness and validated quality.
- HIVE-ADR-017 Provider independence - LLM, embedding, reranking, and cache
  behavior sits behind replaceable adapters.
- HIVE-ADR-018 Git remains source-code history - HIVE does not replace Git or
  store redundant full repository snapshots by default.
