# 06 - ACCE: TOKEN & STORAGE OPTIMIZATION

ACCE (Adaptive Context Compression Engine) reduces input tokens, repeated
retrieval/embeddings/storage, disk usage, and latency without measurable
degradation in code quality or task correctness. Binary compression saves disk;
context optimization saves tokens.

## Storage pipeline

Raw artifact -> hash -> deduplicate -> chunk -> delta/change detection ->
Zstandard compression -> content-addressable storage -> derived
representations.

Use Zstandard as the default lossless codec. HOT favors speed, WARM balances
speed and size, and COLD may use stronger compression; levels must be benchmarked
on real HIVE data.

Use content hashes for documents, chunks, prompt artifacts, tool outputs,
context snapshots, and derived representations. Do not store repeated complete
source repositories; prefer repository path, commit, branch, file, symbol,
diff, and immutable Git history.

## Incremental and context optimization

Inspect Git diffs, invalidate affected derived data, and regenerate only
affected chunks/embeddings/summaries. Stable representations get fingerprints;
unchanged source and dependencies reuse derived data. Iterative runs may send
safe deltas but must not omit newly relevant dependencies.

Keep stable prompt instructions first and dynamic task/context after them.
Expose only tools needed for the task. Use deterministic algorithms before LLMs
for changes, symbols, references, hashes, duplicates, Git state, syntax trees,
dependency edges, tests, and static metadata.

Adaptive budgets consider risk, change surface, dependencies, project phase,
uncertainty, and validation requirements. Conceptual modes are ECO, BALANCED,
and SAFE; selection should become automatic.

## Quality guardrail and telemetry

Minimize token cost, latency, and storage cost subject to no test-pass
degradation, zero critical-context loss, accepted retrieval recall, and
preserved code-quality baseline. Track raw/retrieved/reranked/deduplicated/sent
context, fresh/cached/output tokens, saved tokens, compression/dedup ratios,
avoided embedding work, and cache hit rate per task/run.
