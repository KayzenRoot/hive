# 02 — REQUIREMENTS

## Functional requirements

### Project registry
- Register multiple local projects.
- Track project name, repository path, Git branch, HEAD, language stack and state.
- Detect offline, stale, indexing, ready, active, degraded and blocked projects.

### Task/prompt intake
- Accept PDF, Markdown, TXT and structured task text.
- Preserve the original prompt artifact.
- Extract usable task text and metadata.
- Resolve target project with deterministic evidence where possible.
- Require explicit resolution when ambiguity would risk modifying the wrong project.

### Context construction
- Read current checkpoint first.
- Retrieve scope, Definition of Done, architecture and decisions relevant to the task.
- Index code by files and symbols.
- Use Git-aware and change-aware retrieval.
- Prefer symbols and relevant excerpts over entire files.
- Support hybrid semantic + lexical retrieval.
- Support reranking.
- Build a bounded context capsule.

### Memory
- Working memory.
- Session memory.
- Project memory.
- Semantic memory.
- Episodic memory.
- Decision memory.
- Failure/error memory.
- Procedural memory.
- Canonical memory states with provenance.

### Cache
- Hot context cache.
- Retrieval cache.
- Tool-result cache.
- Prompt/provider cache metadata.
- Session cache.
- TTL and invalidation.
- Cache reconstructibility.

### Storage optimization
- Content hashing.
- Deduplication.
- Incremental storage.
- Zstandard compression.
- Content-addressable blob storage.
- Hot/warm/cold storage policy.
- Avoid duplicate repository snapshots when Git can reconstruct state.

### Token optimization
- Progressive disclosure.
- Adaptive token budgets.
- Context fingerprints.
- Delta context.
- Stable prompt prefixes.
- Tool gating.
- Context signal ratio.
- Do not call LLMs for deterministic tasks.
- Track saved versus fresh tokens when measurable.

### Autonomous execution
- Project identification.
- Context preparation.
- Tool selection.
- Executor dispatch.
- Runtime telemetry.
- Test and validation capture.
- Staged memory write.
- Canonical promotion only after validation.

### Dashboard
- All projects connected to HIVE.
- Live project and run status.
- Token telemetry.
- Cost telemetry where provider data allows it.
- Cache hit/miss.
- Context reduction.
- Retrieval metrics.
- Storage metrics.
- Memory metrics.
- CPU/RAM/disk/service health.
- Tests, builds, lint/typecheck.
- Run timeline and event stream.
- Alerts and failures.

## Non-functional requirements

- Local-only operation must be possible.
- No mandatory VPS or cloud database.
- Persistent data must survive container recreation.
- Provider-independent internal contracts.
- Restart-safe.
- Auditable provenance.
- Low operational complexity for V0.1.
- Security boundaries between projects.
- No silent canonical memory mutation from unverified model output.
- Dashboard should remain useful under long-running execution.
