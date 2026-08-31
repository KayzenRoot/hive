# 02 - REQUIREMENTS

## Functional requirements

### Project registry

- Register multiple local projects.
- Track project name, repository path, branch, HEAD, language stack, and state.
- Detect offline, stale, indexing, ready, active, degraded, and blocked projects.

### Task/prompt intake

- Accept PDF, Markdown, TXT, and structured task text.
- Preserve the original prompt artifact.
- Extract usable task text and metadata.
- Resolve the target project with deterministic evidence where possible.
- Require explicit resolution when ambiguity risks modifying the wrong project.

### Context construction

- Read the current checkpoint first.
- Retrieve scope, DoD, architecture, and decisions relevant to the task.
- Index code by files and symbols with Git-aware/change-aware retrieval.
- Prefer symbols and relevant excerpts over entire files.
- Support hybrid semantic plus lexical retrieval and reranking.
- Build a bounded context capsule.

### Memory

Support working, session, project, semantic, episodic, decision, failure/error,
and procedural memory with provenance and canonical states.

### Cache

Support hot context, retrieval, tool-result, prompt/provider, and session caches
with TTL, invalidation, and reconstructibility.

### Storage optimization

Support content hashing, deduplication, incremental storage, Zstandard
compression, content-addressable blobs, hot/warm/cold policy, and Git-aware
avoidance of duplicate repository snapshots.

### Token optimization

Support progressive disclosure, adaptive budgets, context fingerprints, delta
context, stable prompt prefixes, tool gating, context signal ratio, deterministic
first execution, and saved-versus-fresh token telemetry where measurable.

### Autonomous execution

Support project identification, context preparation, tool selection, executor
dispatch, runtime telemetry, test/validation capture, staged memory writes, and
canonical promotion only after validation.

### Dashboard

Show projects, run status, token/cost telemetry, cache, context reduction,
retrieval, storage, memory, CPU/RAM/disk/service health, validation history,
timelines, events, alerts, and failures.

## Non-functional requirements

- Local-only operation is possible.
- No mandatory VPS or cloud database.
- Persistent data survives container recreation.
- Internal contracts are provider-independent.
- Services are restart-safe and provenance is auditable.
- V0.1 has low operational complexity.
- Projects have security boundaries.
- Unverified model output cannot silently mutate canonical memory.
- Dashboard remains useful during long-running execution.
