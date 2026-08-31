# 07 - HIVE CONTROL CENTER

The Control Center is a necessary V0.1 capability, an operational interface and
observability plane rather than a cosmetic dashboard.

## Home view

Near-real-time fleet state: total projects and READY, ACTIVE, INDEXING,
DEGRADED, BLOCKED, STALE, and OFFLINE counts. Active runs show project, task,
executor/model, stage, elapsed time, estimated tokens, cache hit rate, last
event, test state, and errors/warnings.

Global telemetry includes input/fresh/cached/output tokens, tokens per minute,
estimated savings, effective cost when available, savings estimate, and
historical charts. Context telemetry includes available, retrieved, reranked,
deduplicated, sent, reduction percentage, and signal ratio.

Cache telemetry includes process cache, Redis, retrieval cache, provider cache,
hit/miss, evictions, invalidations, and memory. Storage includes logical,
deduplicated, compressed physical, saved bytes, PostgreSQL, CAS, Redis,
artifacts, logs, and backups.

Platform health includes API, MCP, PostgreSQL, Redis, indexer, event system,
dashboard, optional local models, CPU, RAM, disk, I/O, and containers.

## Project and run detail

Project detail shows overview, version/phase, checkpoint, scope, DoD progress,
branch/HEAD, index health, commits, runs, decisions, canonical/staged memory,
modules/symbols, dependency graph, validation history, token/cost/cache/
storage/retrieval charts, and alerts.

Run detail is a live event timeline from prompt ingestion through context,
cache, retrieval, executor requests, tools, file changes, tests, validation,
staged memory, and final outcome. Use WebSocket or SSE, persist events for
replay, reconcile clients, and mark live token counts as estimated until
provider-final reconciliation.
