# 11 — TEST PLAN

## Test objective

HIVE is not correct because an LLM says it works.

V0.1 requires objective validation.

## Required test layers

### Unit
- hashing/dedup;
- compression/decompression;
- memory lifecycle;
- token budgeting;
- context fingerprinting;
- project resolution;
- cache invalidation;
- parser/chunker;
- provenance.

### Integration
- PostgreSQL;
- pgvector;
- Redis;
- CAS;
- repository indexer;
- MCP;
- API;
- event stream;
- dashboard;
- executor adapter.

### Retrieval
Create benchmark tasks with known relevant files/symbols.

Measure:
- recall@k;
- precision;
- reranking quality;
- context size;
- critical-context misses.

### Token efficiency
For benchmark tasks compare:
- baseline/full-context approach;
- HIVE optimized context.

Measure:
- input tokens;
- cache;
- outputs;
- task success;
- test pass rate;
- retrieval evidence.

### Storage
Measure:
- raw logical data;
- deduplicated data;
- compressed data;
- reconstruction integrity.

Compression is lossless for canonical blobs.

### Resilience
- restart containers;
- clear Redis;
- verify canonical state survives;
- rebuild derived caches;
- reconnect dashboard;
- replay event state.

### Security
- cross-project retrieval isolation;
- malicious prompt/document instructions;
- secret redaction;
- unauthorized canonical memory writes.

### End-to-end
1. register project;
2. index project;
3. upload prompt PDF;
4. build context;
5. dispatch executor;
6. stream telemetry;
7. modify/test sample project;
8. capture evidence;
9. stage memory;
10. complete review;
11. verify dashboard state;
12. restart and verify persistence.

## Quality rule

Any optimization that materially degrades benchmark task correctness must be rejected or restricted to lower-risk task classes.
