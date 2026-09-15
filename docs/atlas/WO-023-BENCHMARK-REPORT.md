# WO-023 Comprehensive Benchmarks

Deterministic, provider-independent benchmark evidence for the V0.1 retrieval,
token-efficiency and storage-efficiency requirements. The harness lives in
`scripts/comprehensive_benchmarks.py`, runs inside the Integration health job
(through `scripts/integration_health.py`) and publishes the closed
`comprehensive-benchmarks-v1` payload to
`tmp/integration-logs/comprehensive-benchmarks.json`.

## Benchmark design

Every family is measured by driving real HIVE code paths over an isolated Git
fixture project; nothing in the evidence is hand-authored.

| Family | Real code path | Measured evidence |
| --- | --- | --- |
| Retrieval | corpus sync, `/retrieval/hybrid`, `/retrieval/rerank` | recall@5, precision@5, baseline MRR (hybrid), reranked MRR, final reranked context bytes, critical-context misses |
| Token | Context Manager capsule plus the accepted Adaptive Token Budget benchmark (`app.adaptive_token_budget`) | baseline full-context tokens, optimized tokens, reduction percentage, required-context and governance preservation, budget compliance |
| Storage | content-addressed storage (`cas_blobs`), real CAS/zstd policy measurement (`app.cas.measure_storage_policy`) | referenced (logical) bytes, deduplicated bytes, physical bytes, dedup/compression/total-reduction ratios, exact-byte reconstruction, measured zstd tier selection |

The benchmark runs the retrieval and token families twice per invocation and
requires an identical digest of the deterministic metrics, so
`deterministic_reproducible` is proven rather than assumed.

## Dataset identity

`scripts/benchmark_fixtures/wo023_retrieval_ground_truth.json`
(`wo023-benchmark-corpus-v1`) is the auditable ground truth and the dataset
generator:

- five hand-written module files (`order_service`, `rate_limiter`,
  `cache_policy`, `storage_policy`, `retrieval_ranker`) plus fixture notes;
- 36 generated modules that provide representative optional retrieval breadth;
- three generated large padding blocks retained as optional candidates;
- fixture governance documents required by the real Context Manager;
- five retrieval queries and three benchmark tasks, each declaring its
  expected repository-relative path.

Ground truth is bound to canonical bytes through
`ground_truth_source = git:HEAD-blob:scripts/benchmark_fixtures/wo023_retrieval_ground_truth.json`,
which the Review Evidence contract re-verifies at the reviewed HEAD.

## Measured result on protected main

| Metric | Observed |
| --- | --- |
| recall@5 (accepted gate: k=5, >= 0.90) | 1.0 |
| precision@5 | 0.5 |
| baseline MRR -> reranked MRR | 1.0 -> 1.0 |
| critical-context misses | 0 |
| baseline tokens -> optimized tokens | 28,729 -> 5,952 (79.28% reduction) |
| storage logical / deduplicated / physical bytes | 931 / 718 / 527 |
| zstd policy | `acce-policy-v1`, measured, deterministic re-selection |
| task success and guardrail rates | 1.0 / 1.0 |
| corpus references | 196 across 53 indexed files |

## Interpretation

- Retrieval: the accepted recall gate is met with zero critical misses, and
  reranking never scores below the baseline ordering. Precision@5 is bounded by
  single-file ground truth (one relevant file per query), so the accepted
  measure is recall@5 with strictly positive precision.
- Token: the reduction comes from the Adaptive Token Budget planner on the same
  fixtures, with required context, mandatory governance coverage, acceptance
  criteria and task constraints all preserved, and the optimized estimate
  verified inside the effective budget.
- Storage: ordering (`logical >= deduplicated >= physical`) and the three
  reduction ratios are computed from measured byte counts only and never
  double-counted; every stored artifact was re-downloaded and hashed to prove
  exact reconstruction with zero canonical loss.
- Provider independence: the benchmark makes no provider or model call, so
  `token_cache_status` and `token_output_status` stay `NOT_SUPPORTED` with null
  values and no provider receipt is claimed.

## Known limitations

- The corpus is a bounded fixture, so the numbers demonstrate contract
  mechanics and deterministic behaviour, not production-scale quality; the
  evidence records `production_quality_claimed_from_fixture = false`.
- Semantic retrieval and the reranker are unconfigured in the shared stack, so
  hybrid and rerank report their deterministic lexical fallbacks; the harness
  measures whatever the configured stack truthfully produces.
- Precision@5 cannot exceed 0.2-0.5 with single-file ground truth by
  construction.

## Stabilization performed while building the benchmark

- The harness deletes its own retrieval corpus, embedding and indexing rows
  before the shared fixture cleanup, because retrieval references block the
  generic task cleanup (missing foreign-key ordering).
- Task texts were reduced below the Context Manager query window and the
  corpus files now carry their own path and acceptance-criteria tokens, because
  the real AND-semantics lexical query otherwise produces zero candidates.
- The zstd sample set was widened to representative HIVE-owned sources to clear
  the accepted minimum measurement input.
