# 11 - TEST PLAN

HIVE is correct only through objective validation, not an LLM assertion.

## Required test layers

Unit coverage should include hashing/deduplication, compression, memory
lifecycle, token budgeting, context fingerprints, project resolution, cache
invalidation, parsing/chunking, and provenance.

Integration coverage should include PostgreSQL, pgvector, Redis, CAS, repository
indexer, MCP, API, event stream, dashboard, and executor adapter.

Retrieval benchmarks use known relevant files/symbols and measure recall@k,
precision, reranking quality, context size, and critical-context misses.
Token-efficiency benchmarks compare full context with HIVE context for input,
cache, output, success, tests, and retrieval evidence.

Storage measures logical, deduplicated, compressed, and reconstructed data;
canonical blobs remain lossless. Resilience tests restart containers, clear
Redis, verify canonical state, rebuild caches, reconnect the dashboard, and
replay event state.

Security tests project isolation, malicious prompt/document instructions, secret
redaction, and unauthorized canonical memory writes.

End-to-end flow: register project, index, upload prompt PDF, build context,
dispatch executor, stream telemetry, modify/test a sample project, capture
evidence, stage memory, complete review, verify dashboard, restart, and verify
persistence.

Any optimization that materially degrades benchmark correctness is rejected or
restricted to lower-risk task classes.
