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
| Token | Context Manager capsule for the same benchmark task identities, measured with the shared estimator `app.adaptive_token_budget.estimate_context_payload_tokens` (`utf8-byte-ratio-approx-v1` / `context-payload-v1`) | baseline full-context tokens, optimized capsule tokens, reduction percentage, per-representation acceptance matrix |
| Storage | content-addressed storage (`cas_blobs`), real CAS/zstd policy measurement (`app.cas.measure_storage_policy`) | referenced (logical) bytes, deduplicated bytes, physical bytes, dedup/compression/total-reduction ratios, exact-byte reconstruction, measured zstd tier selection |

The benchmark runs retrieval, token, storage, task-outcome and isolation
measurements twice per invocation and requires an identical digest of every
deterministic acceptance metric, so `deterministic_reproducible` is proven
rather than assumed.

## Same-task baseline and optimized representations

The token and correctness families deliberately derive both representations from
the *same* WO-023 task identities (no Adaptive Token Budget unit fixture and no
unrelated dataset):

- **Baseline (full context).** For each benchmark task, the harness resolves the
  complete task text and the entire bounded candidate pool
  (`/retrieval/rerank`, `top_k=10`, `candidate_pool=20`) and serializes that
  payload with the same deterministic estimator the product uses. The candidate
  superset is enforced: every result the optimized capsule still carries must
  exist in the baseline candidate set.
- **Optimized (HIVE representation).** The emitted Context Manager capsule for
  that same task, with its size independently recomputed client-side from the
  returned payload (budget and bounds metadata excluded) and required to equal
  the product's verified `final_context_token_estimate`.

Because both numbers come from the same tasks and the same estimator, the
reduction percentage is a like-for-like comparison instead of a cross-dataset
comparison.

**Task success** uses one objective criterion per representation: does the
representation still expose the task's expected repository-relative ground-truth
identity (baseline: candidate set plus required complete files; optimized:
retrieval results, projections and required complete files). No separate lexical
query is substituted for context success.

**Test pass rate** comes from a small versioned acceptance matrix
(`wo023-task-acceptance-matrix-v1`, five checks per representation per task:
ground-truth identity, complete task contract, representation depth, budget or
full-context integrity, and provider-free execution). The same checks are
evaluated against both representations, so neither rate is a hard-coded
constant; guardrail booleans remain separate supporting evidence.

## Project isolation

Isolation is measured, not asserted. The harness registers and indexes a second,
bounded fixture project with its own corpus and then runs a two-way negative
probe: the second project must answer its own identity queries (proving
retrieval is live), the alpha-only queries must not return any alpha path from
the second project, and a second-project identity query must not return any
second-project path from alpha. `project_scoped`,
`cross_project_retrieval_accepted` and `cross_project_leaks` are derived from
those measurements plus a project-identity cross-check.


## Dataset identity

`scripts/benchmark_fixtures/wo023_retrieval_ground_truth.json`
(`wo023-benchmark-corpus-v1`) is the auditable ground truth and the dataset
generator:

- five hand-written module files (`order_service`, `rate_limiter`,
  `cache_policy`, `storage_policy`, `retrieval_ranker`) plus fixture notes; the
  three benchmark-task files carry their own contract, acceptance-criteria and
  constraint vocabulary so the real AND-semantics lexical query can resolve them;
- 36 generated modules that provide representative optional retrieval breadth;
- three generated large padding blocks retained as optional candidates;
- six bounded per-task support modules per benchmark task, which deepen the
  candidate pool so the optimized capsule provably retains a strict subset of
  the full-context candidate set;
- fixture governance documents required by the real Context Manager;
- five retrieval queries and three benchmark tasks, each declaring its
  expected repository-relative path and staying inside the bounded query window.

Ground truth is bound to canonical bytes through
`ground_truth_source = git:HEAD-blob:scripts/benchmark_fixtures/wo023_retrieval_ground_truth.json`,
which the Review Evidence contract re-verifies at the reviewed HEAD.

## Measured result (corrected same-task methodology)

These are the values the harness produced on the exact corrected HEAD of PR #90
during the truth correction; the machine-readable source of truth is the
`comprehensive-benchmarks-v1` payload the Integration health job publishes.

| Metric | Observed |
| --- | --- |
| recall@5 (accepted gate: k=5, >= 0.90) | 1.0 |
| precision@5 | 0.4167 |
| baseline MRR -> reranked MRR | 1.0 -> 1.0 |
| critical-context misses | 0 |
| final reranked retrieval context bytes | 18,977 |
| baseline full-context tokens -> optimized capsule tokens | 21,347 -> 14,650 (31.37% reduction) |
| baseline -> optimized task success rate | 1.0 -> 1.0 |
| baseline -> optimized test pass rate | 1.0 -> 1.0 |
| storage logical / deduplicated / physical bytes | 990 / 777 / 559 |
| zstd policy | `acce-policy-v1`, measured, deterministic re-selection |
| project isolation | `project_scoped = true`, `cross_project_retrieval_accepted = false`, `cross_project_leaks = 0` |
| corpus references | 214 across 71 indexed files |

Token counts vary by a few tokens between invocations because the fixture
project identity (PID and generated UUID) appears inside the measured payload.
Within one invocation both passes measure the identical fixture and must produce
the identical digest, which is the reproducibility claim the evidence carries.

## Interpretation

- Retrieval: the accepted recall gate is met with zero critical misses, and
  reranking never scores below the baseline ordering. Precision@5 is bounded by
  single-file ground truth (one relevant file per query), so the accepted
  measure is recall@5 with strictly positive precision.
- Token: the baseline and the optimized representation are the same task, so the
  31.37% saving is a like-for-like result of the Context Manager plus Adaptive
  Token Budget trimming, not a comparison across datasets. The client-side
  recomputation of the emitted payload must equal the product's verified
  estimate, and the total is verified inside the effective budget.
- Correctness: task success is 1.0 in both representations under one objective
  ground-truth-identity criterion, and the versioned acceptance matrix passes
  every check in both representations. The candidate-superset requirement makes
  the baseline structurally complete rather than assumed complete.
- Isolation: the two-way negative probe measured no cross-project retrieval and
  no identity leak between the benchmark project and the bounded second project.
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
- The baseline representation is the complete task text plus the entire bounded
  candidate pool, so its token count is a full-context measure of the same task
  and not an unbounded "every file in the repository" measure.
- Precision@5 cannot exceed 0.2-0.5 with single-file ground truth by
  construction.
- WO-023 is not canonically approved until the hosted Review Evidence gate
  passes on the corrected HEAD; this report does not promote checkpoint truth.

## Stabilization performed while building the benchmark

- The harness deletes its own retrieval corpus, embedding and indexing rows
  before the shared fixture cleanup, because retrieval references block the
  generic task cleanup (missing foreign-key ordering).
- Task texts stay inside the Context Manager query window, the corpus files
  carry their own path, contract and acceptance-criteria tokens, and per-task
  support modules repeat the same contract vocabulary, because the real
  AND-semantics lexical query otherwise produces zero candidates.
- The zstd sample set was widened to representative HIVE-owned sources to clear
  the accepted minimum measurement input.

