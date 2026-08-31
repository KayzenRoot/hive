# 04 — ARCHITECTURE

## High-level architecture

```text
Executor / IDE / Agent
        |
   MCP / REST
        |
+-------------------------+
| HIVE CORE               |
| Project Registry        |
| Prompt Intake           |
| Context Manager         |
| Memory Manager          |
| Retrieval Engine        |
| ACCE Optimizer          |
| Tool Gateway            |
| Execution Orchestrator  |
| Telemetry/Event Bus     |
+------------+------------+
             |
     +-------+-------+
     |               |
 PostgreSQL        Redis
 + pgvector       Hot Cache
     |
 Content-addressable
     storage
     |
 Secondary disk

             +
      HIVE Control Center
```

## Canonical data responsibilities

### Git repository
Canonical source for code and code history.

### PostgreSQL
Canonical structured state for:
- projects;
- sessions;
- tasks;
- runs;
- checkpoint projections;
- memory records;
- decisions;
- document metadata;
- chunks;
- embeddings/references;
- tests and validation evidence;
- event metadata;
- cache metadata where needed.

### Redis
Non-canonical hot layer:
- session state;
- short-lived context capsules;
- retrieval cache;
- locks;
- queues;
- hot tool results;
- TTL data.

Redis data loss must not destroy canonical project truth.

### Content-addressable storage
Durable blob storage for:
- ingested prompt artifacts;
- parsed source artifacts;
- large tool outputs;
- run artifacts;
- snapshots that cannot be reconstructed cheaply;
- compressed derived representations.

## Core services

- API / Orchestrator service.
- MCP server.
- Repository indexer.
- Retrieval/reranking service.
- Memory service.
- Cache service.
- Telemetry service.
- Dashboard web app.
- Optional local model service when promoted.

## Event model

Core operations emit structured events:
- project.discovered
- project.indexing
- task.ingested
- context.started
- context.retrieved
- context.built
- cache.hit
- cache.miss
- executor.started
- tool.called
- file.changed
- test.started
- test.finished
- validation.failed
- validation.passed
- memory.staged
- memory.promoted
- run.completed
- run.failed

Dashboard subscribes to these events through WebSocket or Server-Sent Events.

## Architectural constraints

- Core internal API cannot depend on one LLM provider.
- Cache adapters are replaceable.
- Embedding provider is replaceable.
- Executor provider is replaceable.
- Repository paths are not duplicated into proprietary snapshots by default.
- All significant memory records must include provenance.
