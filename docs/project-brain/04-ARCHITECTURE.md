# 04 - ARCHITECTURE

## High-level architecture

Executor/IDE/Agent -> MCP/REST -> HIVE Core -> PostgreSQL + pgvector and Redis
hot cache -> content-addressable storage on secondary disk, with the HIVE
Control Center as the operational interface.

HIVE Core contains the Project Registry, Prompt Intake, Context Manager, Memory
Manager, Retrieval Engine, ACCE Optimizer, Tool Gateway, Execution Orchestrator,
and Telemetry/Event Bus.

## Canonical data responsibilities

- Git repository: canonical source for code and code history.
- PostgreSQL: canonical structured state including projects, sessions, tasks,
  runs, checkpoint projections, memory records, decisions, documents, chunks,
  embeddings/references, tests/validation evidence, event metadata, and cache
  metadata where needed.
- Redis: non-canonical hot state such as sessions, short-lived capsules,
  retrieval cache, locks, queues, hot tool results, and TTL data. Redis loss
  must not destroy canonical truth.
- Content-addressable storage: durable prompt artifacts, parsed artifacts, large
  tool outputs, run artifacts, and snapshots that cannot be cheaply reconstructed.

## Core services

API/orchestrator, MCP server, repository indexer, retrieval/reranking service,
memory service, cache service, telemetry service, dashboard service, and an
optional local model service when promoted.

## Event model

Operations emit structured events such as project.discovered,
project.indexing, task.ingested, context.started, context.retrieved,
context.built, cache.hit, cache.miss, executor.started, tool.called,
file.changed, test.started, test.finished, validation.failed,
validation.passed, memory.staged, memory.promoted, run.completed, and
run.failed. The dashboard subscribes through WebSocket or SSE.

## Constraints

Core APIs cannot depend on one LLM provider; cache, embedding, and executor
providers are replaceable; repositories are not duplicated into proprietary
snapshots by default; and significant memory records include provenance.
