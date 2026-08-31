# 06 — ACCE: TOKEN & STORAGE OPTIMIZATION

## Purpose

ACCE = Adaptive Context Compression Engine.

Its objective is to reduce:
- LLM input tokens;
- repeated retrieval;
- repeated embeddings;
- repeated storage;
- disk usage;
- latency;

without measurable degradation in code quality or task correctness.

## Principle

Never confuse binary compression with token compression.

Binary compression saves disk.  
Context optimization saves tokens.

## Storage pipeline

```text
Raw artifact
 -> hash
 -> deduplicate
 -> chunk
 -> delta/change detection
 -> Zstd compression
 -> content-addressable storage
 -> derived representations
```

## Physical compression

Use Zstandard as the default lossless codec.

Suggested policy:
- HOT: low compression level / fastest.
- WARM: balanced.
- COLD: stronger compression where useful.

Exact levels must be benchmarked on real HIVE data instead of permanently hard-coded from assumptions.

## Deduplication

Use content hashes for:
- documents;
- chunks;
- prompt artifacts;
- tool outputs;
- context snapshots;
- derived representations.

Reference existing content instead of writing duplicates.

## Git-aware storage

Do not store repeated complete copies of source repositories.

Prefer:
- repository path;
- commit;
- branch;
- file;
- symbol;
- diff;
- immutable Git history.

## Incremental indexing

After changes:
- inspect Git diff;
- determine changed files/symbols;
- invalidate affected derived data;
- regenerate only affected chunks/embeddings/summaries.

## Context fingerprints

Stable representations receive fingerprints.

If source + relevant dependencies did not change:
- do not re-summarize;
- do not re-embed;
- do not rebuild equivalent context;
- reuse cached derived data.

## Delta context

For iterative runs, send what changed since prior context whenever safe.

A delta must not omit a dependency that became relevant due to the change.

## Prompt cache optimization

- Keep stable instructions at the beginning.
- Keep dynamic task/context after stable prefixes.
- Track provider cache capabilities behind adapters.
- Track cached versus fresh input tokens where the provider exposes them.

## Tool gating

Expose only the tool definitions needed for the task.

## Deterministic-first rule

Use deterministic algorithms before LLM calls for:
- file changes;
- symbol definitions;
- references;
- hashes;
- duplicate detection;
- Git state;
- syntax trees;
- dependency edges;
- test results;
- static metadata.

## Adaptive token budgets

Task budget considers:
- risk;
- change surface;
- affected dependencies;
- project phase;
- uncertainty;
- validation requirements.

Conceptual modes:
- ECO
- BALANCED
- SAFE

Mode selection should become automatic, not user-managed.

## Quality guardrail

Optimization objective:

Minimize:
`token_cost + latency + storage_cost`

Subject to:
- test pass rate not degraded;
- critical context loss = 0;
- retrieval recall above accepted threshold;
- code quality baseline preserved.

## Telemetry

Track per task/run:
- raw available context;
- retrieved context;
- reranked context;
- deduplicated context;
- final sent context;
- fresh input tokens;
- cached tokens;
- output tokens;
- estimated saved tokens;
- compression ratio;
- dedup ratio;
- embedding work avoided;
- cache hit rate.
