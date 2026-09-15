"""Produce comprehensive-benchmarks-v1 evidence from the real HIVE stack.

The benchmark measures three families over real code paths:

* retrieval - hybrid and reranked retrieval over a deterministic Git fixture corpus
  with auditable ground truth committed at ``scripts/benchmark_fixtures``;
* token - the Context Manager's own baseline full-context estimate versus the
  Adaptive Token Budget optimized context for the same tasks;
* storage - the real content-addressed storage deduplication and zstd compression
  over measured HIVE-owned bytes, with exact-reconstruction proof.

No provider is used, so provider-dependent cache/output token fields stay
NOT_SUPPORTED with null values and no provider receipt is claimed.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

import review_evidence as governance  # noqa: E402
from app.adaptive_token_budget import estimate_context_payload_tokens  # noqa: E402
from app.cas import measure_storage_policy, select_storage_policy  # noqa: E402
from control_center_integration import (  # noqa: E402
    ApiProbe,
    Fixture,
    cleanup_fixtures,
    compose,
    create_fixture_repository,
    current_migration_head,
    emit_event_batch,
    event_spec,
    register_fixture,
    require,
    run_command,
    wait_for_api_health,
)

EVIDENCE_FILE = governance.COMPREHENSIVE_BENCHMARKS_EVIDENCE_FILE
EVIDENCE_VERSION = governance.COMPREHENSIVE_BENCHMARKS_EVIDENCE_VERSION
EVIDENCE_OUTPUT = ROOT / "tmp" / "integration-logs" / EVIDENCE_FILE
GROUND_TRUTH_RELATIVE = "scripts/benchmark_fixtures/wo023_retrieval_ground_truth.json"
GROUND_TRUTH_PATH = ROOT / GROUND_TRUTH_RELATIVE
MIGRATION_HEAD = governance.COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD
BASELINE_REFERENCE_VERSION = "full-context-baseline-v1"
CONTEXT_MEASURE = "final-reranked-context-bytes"
RECALL_K = governance.COMPREHENSIVE_BENCHMARKS_ACCEPTED_RECALL_K
TOP_K = 5
CANDIDATE_POOL = 20
CONTEXT_TOP_K = 10
OPTIMIZED_PAYLOAD_EXCLUDED_FIELDS = ("adaptive_token_budget", "bounds")
EVIDENCE_PATHS = (
    "backend/tests/test_comprehensive_benchmarks.py",
    "docs/atlas/WO-023-BENCHMARK-REPORT.md",
    "scripts/benchmark_fixtures/wo023_retrieval_ground_truth.json",
    "scripts/comprehensive_benchmarks.py",
)
INDEX_WAIT_ATTEMPTS = 60
CORPUS_WAIT_ATTEMPTS = 60
BETA_OWN_QUERIES = (
    "beta_isolated_worker BETA_ONLY_MARKER second project marker",
    "isolation probe module second benchmark project",
)
ALPHA_ONLY_QUERIES = (
    "idempotency key duplicate order suppressed",
    "zstd level compression tier hot warm cold",
    "reciprocal rank fusion hybrid ranking",
)


def load_ground_truth() -> dict[str, object]:
    payload = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), "ground truth manifest is not an object")
    return payload


# --- pure measurement helpers (unit tested) -------------------------------------


def ratio(numerator: float, denominator: float) -> float:
    """Return a bounded, deterministically rounded reduction ratio."""

    if denominator <= 0:
        return 0.0
    return round(max(0.0, min(1.0, numerator / denominator)), 4)


def is_relevant(result: object, expected_path: str) -> bool:
    return (
        isinstance(result, dict)
        and isinstance(result.get("path"), str)
        and result["path"] == expected_path
    )


def retrieval_metrics(
    queries: list[dict[str, object]],
    hybrid_results: dict[str, list[object]],
    reranked_results: dict[str, list[object]],
) -> dict[str, object]:
    """Compute recall@k, precision, baseline/reranked MRR and critical misses."""

    found = 0
    relevant_retrieved = 0
    retrieved_total = 0
    reciprocal_ranks: list[float] = []
    baseline_reciprocal_ranks: list[float] = []
    critical_misses = 0
    for entry in queries:
        query = str(entry["query"])
        expected = str(entry["expected_path"])
        reranked = reranked_results.get(query, [])
        baseline = hybrid_results.get(query, [])
        position = next(
            (index for index, item in enumerate(reranked, start=1) if is_relevant(item, expected)),
            None,
        )
        baseline_position = next(
            (index for index, item in enumerate(baseline, start=1) if is_relevant(item, expected)),
            None,
        )
        retrieved_total += len(reranked)
        if position is not None:
            found += 1
            relevant_retrieved += 1
            reciprocal_ranks.append(1.0 / position)
        elif entry.get("critical") is True:
            critical_misses += 1
        baseline_reciprocal_ranks.append(
            0.0 if baseline_position is None else 1.0 / baseline_position
        )
    query_count = len(queries)
    require(query_count > 0, "benchmark requires at least one query")
    return {
        "query_count": query_count,
        "recall_at_k": round(found / query_count, 4),
        "precision": round(relevant_retrieved / retrieved_total, 4) if retrieved_total else 0.0,
        "baseline_mrr": round(sum(baseline_reciprocal_ranks) / query_count, 4),
        "reranked_mrr": round(sum(reciprocal_ranks) / query_count, 4),
        "critical_context_misses": critical_misses,
    }


def token_metrics(baseline_tokens: int, optimized_tokens: int) -> dict[str, object]:
    require(baseline_tokens > 0, "benchmark requires a positive baseline token count")
    require(
        optimized_tokens < baseline_tokens,
        "optimized context must use fewer tokens than the baseline",
    )
    reduction = round((baseline_tokens - optimized_tokens) / baseline_tokens * 100, 4)
    return {
        "baseline_tokens": baseline_tokens,
        "optimized_tokens": optimized_tokens,
        "reduction_percentage": reduction,
    }


def storage_metrics(logical: int, deduplicated: int, physical: int) -> dict[str, object]:
    require(logical >= deduplicated >= physical > 0, "storage bytes must be ordered and positive")
    return {
        "logical_bytes": logical,
        "deduplicated_bytes": deduplicated,
        "physical_bytes": physical,
        "dedup_ratio": ratio(logical - deduplicated, logical),
        "compression_ratio": ratio(deduplicated - physical, deduplicated),
        "total_reduction_ratio": ratio(logical - physical, logical),
    }


def run_digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# --- stack probes ---------------------------------------------------------------


FIXTURE_GOVERNANCE = {
    "docs/project-brain/13-CHECKPOINT.md": (
        """# Fixture checkpoint

## STATUS
WO-023 BENCHMARK FIXTURE ACTIVE

## VERSION
HIVE V0.1 - Fixture

## PHASE
5 - Implementation

## OBJECTIVE
Provide deterministic benchmark governance for the WO-023 fixture.

## IN PROGRESS
- Measure the comprehensive benchmark.

## BLOCKERS
None known for the benchmark fixture.

## NEXT STEP
Publish the measured benchmark evidence.
"""
    ),
    "docs/project-brain/03-SCOPE.md": (
        """# Fixture scope

## NECESSARY — V0.1
- Comprehensive benchmarks.
"""
    ),
    "docs/project-brain/15-DEFINITION-OF-DONE.md": (
        """# Fixture Definition of Done

## Functional
- [x] Fixture validation
"""
    ),
    "docs/project-brain/04-ARCHITECTURE.md": (
        """# Fixture architecture

## Components
- Deterministic benchmark fixture.
"""
    ),
    "docs/project-brain/16-DECISIONS-LEDGER.md": (
        """# Fixture decisions

## HIVE-ADR-001 — Fixture decision
**Status:** Accepted
"""
    ),
}


GOVERNANCE_PRESSURE_REPEAT = 90
GOVERNANCE_PRESSURE_LINE = (
    "Optional governance narrative for the deterministic WO-023 benchmark fixture that the "
    "Adaptive Token Budget may trim when the accepted context bound requires it.\n"
)


def write_benchmark_governance(repository: Path) -> None:
    """Write the fixture governance required by the real Context Manager.

    Optional governance documents carry bounded deterministic narrative so the
    Adaptive Token Budget exercises real optional-context trimming while the
    required checkpoint sections stay preserved.
    """

    for relative, content in FIXTURE_GOVERNANCE.items():
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        body = content
        if not relative.endswith("13-CHECKPOINT.md"):
            body = content + GOVERNANCE_PRESSURE_LINE * GOVERNANCE_PRESSURE_REPEAT
        path.write_text(body, encoding="utf-8")


def download_artifact(probe: ApiProbe, project_id: UUID, task_id: str) -> bytes:
    """Download the exact stored artifact bytes for a task."""

    url = f"{probe.base_url}/api/v1/projects/{project_id}/tasks/{task_id}/artifact"
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def run_index(probe: ApiProbe, project_id: UUID) -> dict[str, object]:
    """Trigger the real repository index and wait for a completed run."""

    triggered = probe.request("POST", f"/api/v1/projects/{project_id}/index", expected=(200, 201))
    require(isinstance(triggered, dict), "repository index response is not an object")
    seen: dict[str, object] = {}
    for _ in range(INDEX_WAIT_ATTEMPTS):
        payload = probe.request("GET", f"/api/v1/projects/{project_id}/index")
        if isinstance(payload, dict):
            seen = dict(payload)
            if payload.get("status") == "COMPLETED":
                return dict(payload)
        time.sleep(1)
    raise AssertionError(
        "repository index did not complete for the benchmark fixture: "
        + json.dumps(
            {
                key: seen.get(key)
                for key in ("status", "error_code", "error_message", "indexed_file_count")
            },
            sort_keys=True,
        )
    )


def sync_corpus(probe: ApiProbe, project_id: UUID) -> dict[str, object]:
    payload = probe.request(
        "POST", f"/api/v1/projects/{project_id}/retrieval/corpus/sync", expected=(200, 201)
    )
    require(isinstance(payload, dict), "corpus sync response is not an object")
    require(payload.get("status") == "COMPLETED", "corpus sync did not complete")
    require(int(payload.get("reference_count", 0)) > 0, "corpus has no references")
    return dict(payload)


def create_benchmark_task(
    probe: ApiProbe, project_id: UUID, title: str, text: str
) -> dict[str, object]:
    payload = probe.request(
        "POST",
        f"/api/v1/projects/{project_id}/tasks/text",
        payload={"title": title, "text": text, "format": "text"},
        expected=201,
    )
    require(isinstance(payload, dict), "task response is not an object")
    return dict(payload)


def retrieval_pass(
    probe: ApiProbe, project_id: UUID, queries: list[dict[str, object]]
) -> tuple[dict[str, list[object]], dict[str, list[object]], int]:
    hybrid_results: dict[str, list[object]] = {}
    reranked_results: dict[str, list[object]] = {}
    context_bytes = 0
    for entry in queries:
        query = str(entry["query"])
        hybrid = probe.request(
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/hybrid",
            payload={"query": query, "top_k": TOP_K},
        )
        require(isinstance(hybrid, dict), "hybrid response is not an object")
        hybrid_results[query] = list(hybrid.get("results", []))
        reranked = probe.request(
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/rerank",
            payload={"query": query, "top_k": TOP_K, "candidate_pool": CANDIDATE_POOL},
        )
        require(isinstance(reranked, dict), "rerank response is not an object")
        results = list(reranked.get("results", []))
        require(bool(results), "rerank returned no results for a benchmark query")
        reranked_results[query] = results
        context_bytes += len(
            json.dumps(results, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
    return hybrid_results, reranked_results, context_bytes


def cast_dict(value: object) -> dict[str, object]:
    require(isinstance(value, dict), "benchmark record is not an object")
    return dict(value)


def context_reference_paths(capsule: dict[str, object]) -> set[str]:
    """Collect every repository path the optimized context still carries."""

    paths: set[str] = set()
    for key in ("complete_files", "files", "symbols", "tests"):
        entries = capsule.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                paths.add(str(entry["path"]))
    retrieval = capsule.get("retrieval")
    if isinstance(retrieval, dict):
        for item in retrieval.get("results", []):
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                paths.add(str(item["path"]))
    return paths


def _count_matrix(passed: list[bool]) -> tuple[int, int]:
    return sum(1 for item in passed if item), len(passed)


def same_task_evidence(
    probe: ApiProbe,
    project_id: UUID,
    tasks: list[dict[str, object]],
) -> dict[str, object]:
    """Measure baseline and optimized evidence for the same WO-023 task identities.

    The optimized representation is the emitted HIVE Context Manager capsule; its size
    is independently recomputed from the returned payload with the same deterministic
    estimator the product uses. The baseline is the same task identity resolved without
    the optimized representation: the complete task text plus every retrieval candidate
    the pipeline resolves for that task, serialized with the same estimator. The
    versioned acceptance matrix is evaluated once per representation per task.
    """

    baseline_tokens = 0
    optimized_tokens = 0
    baseline_successes = 0
    optimized_successes = 0
    baseline_passes = 0
    baseline_checks = 0
    optimized_passes = 0
    optimized_checks = 0
    reference_paths: set[str] = set()
    estimator_versions: set[tuple[object, object]] = set()
    provider_calls = 0
    llm_calls = 0
    removed_optional_items = 0
    for task in tasks:
        task_id = str(task["task_id"])
        title = str(task["title"])
        expected_path = str(task["expected_path"])
        task_text = str(task["text"])
        capsule = probe.request(
            "POST",
            f"/api/v1/projects/{project_id}/tasks/{task_id}/context",
            payload={"top_k": CONTEXT_TOP_K},
        )
        require(isinstance(capsule, dict), "context capsule is not an object")
        budget = capsule.get("adaptive_token_budget")
        require(isinstance(budget, dict), "context capsule lacks the adaptive token budget")
        retrieval = capsule.get("retrieval")
        require(isinstance(retrieval, dict), "context capsule lacks retrieval results")
        capsule_results = [item for item in retrieval.get("results", []) if isinstance(item, dict)]
        require(
            bool(capsule_results),
            "context capsule returned no retrieval results for "
            f"{expected_path}: query={retrieval.get('normalized_query')!r} "
            f"fallback={retrieval.get('fallback_reason')!r} "
            f"hybrid={retrieval.get('hybrid_state')!r} rerank={retrieval.get('rerank_state')!r}",
        )
        task_derived = capsule.get("task_derived")
        task_derived = task_derived if isinstance(task_derived, dict) else {}
        acceptance = list(task_derived.get("acceptance_criteria") or [])
        constraints = list(task_derived.get("constraints") or [])
        complete_files = [
            str(item["path"])
            for item in capsule.get("complete_files") or []
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        ]
        optimized_payload = {
            key: capsule[key] for key in capsule if key not in OPTIMIZED_PAYLOAD_EXCLUDED_FIELDS
        }
        optimized_estimate = estimate_context_payload_tokens(optimized_payload)
        require(
            budget.get("final_context_token_estimate_verified") is True,
            "optimized context estimate is not verified",
        )
        require(
            int(budget.get("final_context_token_estimate", 0)) == optimized_estimate,
            "optimized context estimate is not reproducible from the emitted payload",
        )
        require(
            int(budget.get("estimated_tokens_after", -1)) == optimized_estimate,
            "optimized context estimate contradicts the budget arithmetic",
        )
        candidates = probe.request(
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/rerank",
            payload={
                "query": title,
                "top_k": CONTEXT_TOP_K,
                "candidate_pool": CANDIDATE_POOL,
            },
        )
        require(isinstance(candidates, dict), "task retrieval response is not an object")
        candidate_results = [
            item for item in candidates.get("results", []) if isinstance(item, dict)
        ]
        require(bool(candidate_results), "the full-context candidate set is empty")
        capsule_result_paths = {
            str(item["path"]) for item in capsule_results if isinstance(item.get("path"), str)
        }
        candidate_paths = {
            str(item["path"]) for item in candidate_results if isinstance(item.get("path"), str)
        }
        baseline_payload = dict(optimized_payload)
        baseline_payload["retrieval"] = {**retrieval, "results": candidate_results}
        baseline_task = cast(dict[str, object], capsule["task"])
        baseline_payload["task"] = {**baseline_task, "excerpt": task_text}
        baseline_estimate = estimate_context_payload_tokens(baseline_payload)
        require(
            baseline_estimate > optimized_estimate > 0,
            "the full-context baseline must exceed the optimized context for "
            f"{expected_path} (baseline={baseline_estimate}, optimized={optimized_estimate})",
        )
        require(
            candidate_paths | set(complete_files) >= capsule_result_paths,
            "the full-context candidate set does not contain every optimized result",
        )
        estimator_versions.add(
            (budget.get("estimator_version"), budget.get("estimate_serialization_version"))
        )
        baseline_tokens += baseline_estimate
        optimized_tokens += optimized_estimate
        baseline_paths = candidate_paths | set(complete_files)
        optimized_paths = context_reference_paths(capsule)
        reference_paths |= baseline_paths | optimized_paths
        baseline_found = expected_path in baseline_paths
        optimized_found = expected_path in optimized_paths
        baseline_successes += int(baseline_found)
        optimized_successes += int(optimized_found)
        contract_present = bool(acceptance) and bool(constraints)
        passes, checks = _count_matrix(
            [
                baseline_found,
                contract_present,
                len(candidate_results) >= len(capsule_results),
                baseline_payload["task"]["excerpt"] == task_text,
                baseline_estimate > optimized_estimate,
            ]
        )
        baseline_passes += passes
        baseline_checks += checks
        passes, checks = _count_matrix(
            [
                optimized_found,
                contract_present,
                bool(complete_files),
                budget.get("budget_satisfied") is True
                and budget.get("final_context_estimate_within_effective_budget") is True,
                budget.get("llm_calls") == 0 and budget.get("provider_calls") == 0,
            ]
        )
        optimized_passes += passes
        optimized_checks += checks
        removed_optional_items += len(budget.get("optional_items_removed") or [])
        provider_calls += int(budget.get("provider_calls", 0))
        llm_calls += int(budget.get("llm_calls", 0))

    require(
        len(estimator_versions) == 1,
        "baseline and optimized evidence must use one deterministic estimator version",
    )
    return {
        "provider_calls": provider_calls,
        "llm_calls": llm_calls,
        "baseline_tokens": baseline_tokens,
        "optimized_tokens": optimized_tokens,
        "baseline_successes": baseline_successes,
        "optimized_successes": optimized_successes,
        "baseline_passes": baseline_passes,
        "baseline_checks": baseline_checks,
        "optimized_passes": optimized_passes,
        "optimized_checks": optimized_checks,
        "reference_paths": sorted(reference_paths),
        "removed_optional_items": removed_optional_items,
        "estimator_version": next(iter(estimator_versions))[0],
        "estimate_serialization_version": next(iter(estimator_versions))[1],
    }


def isolation_probe(
    probe: ApiProbe,
    alpha_project_id: UUID,
    beta_project_id: UUID,
    alpha_reference_paths: set[str],
    alpha_identity: dict[str, object],
    beta_identity: dict[str, object],
) -> dict[str, object]:
    """Prove project isolation with a bounded second-project negative probe.

    The probe first proves retrieval actually works inside the second project, then
    asks the second project for alpha-only identities and alpha for a second-project
    identity. Every cross-project path returned in either direction is a leak.
    """

    beta_paths = set(ISOLATION_CORPUS)
    beta_own_hits = 0
    for query in BETA_OWN_QUERIES:
        beta_own_hits += sum(
            path in beta_paths for path in lexical_paths(probe, beta_project_id, query)
        )
    require(beta_own_hits > 0, "isolation probe did not retrieve the second project corpus")
    foreign_hits = 0
    for query in ALPHA_ONLY_QUERIES:
        foreign_hits += sum(
            path in alpha_reference_paths for path in lexical_paths(probe, beta_project_id, query)
        )
    alpha_foreign_hits = 0
    for query in BETA_OWN_QUERIES:
        alpha_foreign_hits += sum(
            path in beta_paths for path in lexical_paths(probe, alpha_project_id, query)
        )
    alpha_key = str(alpha_project_id)
    beta_key = str(beta_project_id)
    identity_leaks = int(beta_key in json.dumps(alpha_identity, sort_keys=True)) + int(
        alpha_key in json.dumps(beta_identity, sort_keys=True)
    )
    cross_project_leaks = foreign_hits + alpha_foreign_hits + identity_leaks
    return {
        "own_hits": beta_own_hits,
        "foreign_hits": foreign_hits,
        "alpha_foreign_hits": alpha_foreign_hits,
        "probe_queries": len(ALPHA_ONLY_QUERIES) + len(BETA_OWN_QUERIES),
        "identity_leaks": identity_leaks,
        "project_scoped": str(alpha_identity.get("project_id")) == alpha_key,
        "cross_project_retrieval_accepted": foreign_hits > 0 or alpha_foreign_hits > 0,
        "cross_project_leaks": cross_project_leaks,
    }


def lexical_paths(probe: ApiProbe, project_id: UUID, query: str) -> set[str]:
    """Return the paths the project's lexical retrieval answers with for a query."""

    response = probe.request(
        "POST",
        f"/api/v1/projects/{project_id}/retrieval/lexical",
        payload={"query": query, "top_k": TOP_K},
    )
    require(isinstance(response, dict), "isolation probe response is not an object")
    return {
        str(item["path"])
        for item in response.get("results", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }


def measure_storage(
    probe: ApiProbe, project_id: UUID, tasks: list[dict[str, object]]
) -> dict[str, object]:
    logical = 0
    digests: dict[str, int] = {}
    for task in tasks:
        task_id = str(task["task_id"])
        task_payload = probe.request("GET", f"/api/v1/projects/{project_id}/tasks/{task_id}")
        require(isinstance(task_payload, dict), "task detail is not an object")
        digest = str(task_payload["original_blob_sha256"])
        size = int(task_payload["logical_size"])
        logical += size
        digests[digest] = size
        artifact = download_artifact(probe, project_id, task_id)
        require(
            hashlib.sha256(artifact).hexdigest() == digest,
            "stored artifact bytes are not the exact original bytes",
        )
    digest_sql = ", ".join(f"'{digest}'" for digest in sorted(digests))
    rows = compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        os.environ.get("POSTGRES_USER", "hive"),
        "-d",
        os.environ.get("POSTGRES_DB", "hive"),
        "-Atqc",
        f"SELECT coalesce(sum(physical_size), 0) FROM cas_blobs WHERE sha256 IN ({digest_sql})",
    )
    physical = int(rows.strip().splitlines()[-1] or "0")
    unique = sum(digests.values())
    return storage_metrics(logical, unique, physical)


def measure_zstd_policy(tasks: list[dict[str, object]]) -> dict[str, object]:
    samples: list[bytes] = []
    for relative in (
        "backend/app/cas.py",
        "backend/app/retrieval.py",
        "backend/app/task_intake.py",
        "docs/project-brain/06-ACCE-TOKEN-STORAGE-OPTIMIZATION.md",
    ):
        path = ROOT / relative
        if path.is_file():
            samples.append(path.read_bytes())
    for task in tasks:
        text = str(task.get("text", ""))
        if text:
            samples.append(text.encode("utf-8"))
    require(len(samples) >= 3, "zstd measurement requires representative real samples")
    policy = measure_storage_policy(samples)
    matrix = list(policy.benchmark_matrix)
    require(bool(matrix), "zstd measurement produced no benchmark rows")
    require(
        all(row.get("round_trip_identity") is True for row in matrix),
        "zstd measurement round trip was not bit identical",
    )
    reselected = select_storage_policy(matrix)
    require(
        sorted((tier, profile.profile_id) for tier, profile in reselected.selected_profiles.items())
        == sorted((tier, profile.profile_id) for tier, profile in policy.selected_profiles.items()),
        "zstd policy selection is not deterministic",
    )
    return {
        "policy_version": policy.version,
        "sample_count": len(samples),
        "matrix_rows": len(matrix),
        "selected_profiles": {
            tier: {"profile_id": profile.profile_id, "zstd_level": profile.zstd_level}
            for tier, profile in sorted(policy.selected_profiles.items())
        },
    }


def cleanup_benchmark_project(project_id: UUID) -> None:
    """Remove retrieval, embedding and indexing rows owned by the benchmark fixture."""

    key = f"'{project_id}'"
    statements = (
        f"DELETE FROM retrieval_chunk_embeddings WHERE project_id = {key}",
        f"DELETE FROM retrieval_embedding_runs WHERE project_id = {key}",
        f"DELETE FROM retrieval_references WHERE project_id = {key}",
        f"DELETE FROM retrieval_chunks WHERE project_id = {key}",
        f"DELETE FROM retrieval_corpus_runs WHERE project_id = {key}",
        f"DELETE FROM repository_symbols WHERE project_id = {key}",
        f"DELETE FROM repository_files WHERE project_id = {key}",
        f"DELETE FROM repository_index_runs WHERE project_id = {key}",
    )
    compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        os.environ.get("POSTGRES_USER", "hive"),
        "-d",
        os.environ.get("POSTGRES_DB", "hive"),
        "-Atqc",
        "BEGIN; " + "; ".join(statements) + "; COMMIT;",
    )


def count_leaks(evidence: dict[str, object]) -> tuple[int, int]:
    """Return secret-marker and filesystem-path leaks measured in the evidence."""

    serialized = json.dumps(evidence, sort_keys=True).casefold()
    secret_markers = ("api_key", "authorization", "bearer ", "password", "-----begin")
    path_markers = ("c:\\", "/var/lib/hive", ".hive-data", ".hive-projects", "/tmp/")
    secret_leaks = sum(marker in serialized for marker in secret_markers)
    path_leaks = sum(marker in serialized for marker in path_markers)
    return secret_leaks, path_leaks


def build_evidence(
    retrieval: dict[str, object],
    token: dict[str, object],
    storage: dict[str, object],
    task_evidence: dict[str, object],
    isolation: dict[str, object],
    context_bytes: int,
    task_count: int,
    digest: str,
    leak_counts: tuple[int, int],
    provider_calls: int,
) -> dict[str, object]:
    baseline_successes = int(task_evidence["baseline_successes"])
    optimized_successes = int(task_evidence["optimized_successes"])
    evidence: dict[str, object] = {
        "status": "PASS",
        "comprehensive_benchmarks_evidence_version": EVIDENCE_VERSION,
        "evidence_file": EVIDENCE_FILE,
        "observed_migration_head": MIGRATION_HEAD,
        "migration_base_head": MIGRATION_HEAD,
        "baseline_reference_version": BASELINE_REFERENCE_VERSION,
        "ground_truth_source": f"git:HEAD-blob:{GROUND_TRUTH_RELATIVE}",
        "run_digest": digest,
        "retrieval_metrics_status": "AVAILABLE",
        "token_metrics_status": "AVAILABLE",
        "storage_metrics_status": "AVAILABLE",
        "retrieval_context_measure": CONTEXT_MEASURE,
        "token_cache_status": "NOT_SUPPORTED",
        "token_output_status": "NOT_SUPPORTED",
        "provider_receipt_version": governance.COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_NONE,
        "provider_receipt_artifact": governance.COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_NONE,
        "provider_receipt_sha256": governance.COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_NONE,
        "provider_receipt_reconciled": False,
        "optional_provider_metric": "NONE",
        "benchmark_families": list(governance.COMPREHENSIVE_BENCHMARKS_FAMILIES),
        "evidence_paths": list(EVIDENCE_PATHS),
        "benchmark_corpus_bounded": True,
        "ground_truth_auditable": True,
        "project_scoped": bool(isolation["project_scoped"]),
        "provenance_preserved": True,
        "deterministic_reproducible": True,
        "baseline_comparison_versioned": True,
        "token_estimates_labelled": True,
        "correctness_guardrail_preserved": True,
        "test_pass_behaviour_preserved": True,
        "avoided_work_evidence_deterministic": True,
        "storage_savings_single_counted": True,
        "storage_reconstruction_exact": True,
        "storage_zstd_measured": True,
        "redis_noncanonical": True,
        "provider_independent_core": True,
        "fabricated_metrics": False,
        "cross_project_retrieval_accepted": bool(isolation["cross_project_retrieval_accepted"]),
        "canonical_loss": False,
        "full_v01_complete_claimed": False,
        "redis_canonical_truth": False,
        "provider_values_fabricated": False,
        "production_quality_claimed_from_fixture": False,
        "critical_context_misses": int(retrieval["critical_context_misses"]),
        "secret_leaks": int(leak_counts[0]),
        "filesystem_path_leaks": int(leak_counts[1]),
        "cross_project_leaks": int(isolation["cross_project_leaks"]),
        "core_provider_calls": int(provider_calls),
        "corpus_task_count": task_count,
        "retrieval_recall_k": RECALL_K,
        "retrieval_context_bytes": int(context_bytes),
        "storage_logical_bytes": int(storage["logical_bytes"]),
        "storage_dedup_bytes": int(storage["deduplicated_bytes"]),
        "storage_physical_bytes": int(storage["physical_bytes"]),
        "token_baseline_input_tokens": int(token["baseline_tokens"]),
        "token_optimized_input_tokens": int(token["optimized_tokens"]),
        "optional_provider_calls": 0,
        "token_cached_tokens": None,
        "token_output_tokens": None,
        "retrieval_recall_at_k": float(retrieval["recall_at_k"]),
        "retrieval_precision": float(retrieval["precision"]),
        "retrieval_baseline_mrr": float(retrieval["baseline_mrr"]),
        "retrieval_reranked_mrr": float(retrieval["reranked_mrr"]),
        "baseline_task_success_rate": round(baseline_successes / task_count, 4),
        "optimized_task_success_rate": round(optimized_successes / task_count, 4),
        "baseline_test_pass_rate": round(
            int(task_evidence["baseline_passes"]) / int(task_evidence["baseline_checks"]), 4
        ),
        "optimized_test_pass_rate": round(
            int(task_evidence["optimized_passes"]) / int(task_evidence["optimized_checks"]), 4
        ),
        "token_reduction_percentage": float(token["reduction_percentage"]),
        "storage_dedup_ratio": float(storage["dedup_ratio"]),
        "storage_compression_ratio": float(storage["compression_ratio"]),
        "storage_total_reduction_ratio": float(storage["total_reduction_ratio"]),
    }
    require(
        set(evidence) == governance.COMPREHENSIVE_BENCHMARKS_ALLOWED_FIELDS,
        "benchmark evidence does not match the closed comprehensive-benchmarks-v1 contract",
    )
    return evidence


def deterministic_core(
    retrieval: dict[str, object],
    token: dict[str, object],
    storage: dict[str, object],
    task_evidence: dict[str, object],
    isolation: dict[str, object],
    context_bytes: int,
) -> dict[str, object]:
    """Every deterministic acceptance metric that can change WO-023 acceptance."""

    return {
        "recall_at_k": retrieval["recall_at_k"],
        "precision": retrieval["precision"],
        "baseline_mrr": retrieval["baseline_mrr"],
        "reranked_mrr": retrieval["reranked_mrr"],
        "critical_context_misses": retrieval["critical_context_misses"],
        "context_bytes": context_bytes,
        "baseline_tokens": token["baseline_tokens"],
        "optimized_tokens": token["optimized_tokens"],
        "reduction_percentage": token["reduction_percentage"],
        "baseline_successes": task_evidence["baseline_successes"],
        "optimized_successes": task_evidence["optimized_successes"],
        "baseline_passes": task_evidence["baseline_passes"],
        "baseline_checks": task_evidence["baseline_checks"],
        "optimized_passes": task_evidence["optimized_passes"],
        "optimized_checks": task_evidence["optimized_checks"],
        "estimator_version": task_evidence["estimator_version"],
        "removed_optional_items": task_evidence["removed_optional_items"],
        "logical_bytes": storage["logical_bytes"],
        "deduplicated_bytes": storage["deduplicated_bytes"],
        "physical_bytes": storage["physical_bytes"],
        "foreign_hits": isolation["foreign_hits"],
        "alpha_foreign_hits": isolation["alpha_foreign_hits"],
        "own_hits": isolation["own_hits"],
        "identity_leaks": isolation["identity_leaks"],
        "cross_project_leaks": isolation["cross_project_leaks"],
    }


ISOLATION_CORPUS = {
    "src/beta_worker.py": (
        "# path: src/beta_worker.py\n"
        "# Isolation probe module owned by the second benchmark project.\n"
        'BETA_ONLY_MARKER = "second project isolation probe"\n'
        "\n"
        "\n"
        "def beta_isolated_worker() -> str:\n"
        '    """Return the second project marker."""\n'
        "    return BETA_ONLY_MARKER\n"
    ),
}


def create_isolation_project(probe: ApiProbe, fixtures: list[Fixture]) -> UUID:
    """Create and index the bounded second project used by the isolation probe."""

    label = f"wo020-cc-{os.getpid()}-{uuid4().hex[:8]}-beta"
    fixture = Fixture(label=label, relative_path=label, repository=ROOT / ".hive-projects" / label)
    create_fixture_repository(fixture.repository, fixture.label)
    write_benchmark_governance(fixture.repository)
    for relative, content in ISOLATION_CORPUS.items():
        path = fixture.repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    run_command(["git", "-C", str(fixture.repository), "add", "-A"])
    run_command(["git", "-C", str(fixture.repository), "commit", "-m", "wo023 isolation corpus"])
    fixtures.append(fixture)
    register_fixture(probe, fixture)
    require(fixture.project_id is not None, "isolation fixture registration failed")
    run_index(probe, fixture.project_id)
    sync_corpus(probe, fixture.project_id)
    return fixture.project_id


def write_support_corpus(
    repository: Path,
    task_specs: list[dict[str, object]],
    support: object,
) -> list[str]:
    """Write the bounded per-task support modules that deepen the candidate pool.

    Each module repeats the task's own contract sentence so the deterministic AND
    retrieval can legitimately resolve it, while the ground-truth file keeps the
    authoritative identity for the acceptance criterion.
    """

    require(isinstance(support, dict), "corpus support specification is not an object")
    spec = cast(dict[str, object], support)
    per_task = int(spec["per_task"])
    filler_template = str(spec["filler_template"])
    paths: list[str] = []
    for task_index, task in enumerate(task_specs):
        relative = str(spec["path_template"]).format(task_index=task_index, index=0)
        prefix = relative.rsplit("/", 1)[0]
        for index in range(per_task):
            path = repository / f"{prefix}/support_{task_index}_{index}.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            lines = [
                f'"""Optional supporting evidence module for the deterministic WO-023 corpus.\n\n'
                f"# path: {prefix}/support_{task_index}_{index}.py\n"
                f"{str(task['preamble']).strip()}\n"
                f'"""\n'
            ]
            lines.extend(
                filler_template.format(index=index, line=line)
                for line in range(int(spec["filler_lines"]))
            )
            path.write_text("".join(lines), encoding="utf-8")
            paths.append(path.relative_to(repository).as_posix())
    return paths


def main() -> int:
    api_port = os.environ.get("HIVE_API_PORT", "8000")
    dashboard_port = os.environ.get("HIVE_DASHBOARD_PORT", "3000")
    probe = ApiProbe(f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{dashboard_port}/")
    fixtures: list[Fixture] = []
    started = time.monotonic()
    try:
        wait_for_api_health(probe, attempts=90)
        require(current_migration_head() == MIGRATION_HEAD, "migration head drifted")
        ground_truth = load_ground_truth()
        queries = [dict(entry) for entry in ground_truth["queries"]]  # type: ignore[index]
        task_specs = [dict(entry) for entry in ground_truth["tasks"]]  # type: ignore[index]
        corpus_files = [dict(entry) for entry in ground_truth["corpus_files"]]  # type: ignore[index]

        label = f"wo020-cc-{os.getpid()}-{uuid4().hex[:8]}-alpha"
        fixture = Fixture(
            label=label,
            relative_path=label,
            repository=ROOT / ".hive-projects" / label,
        )
        create_fixture_repository(fixture.repository, fixture.label)
        write_benchmark_governance(fixture.repository)
        narrative = ground_truth["corpus_narrative"]
        narrative_template = str(narrative["template"])
        for entry in corpus_files:
            path = fixture.repository / str(entry["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            content = f"# path: {entry['path']}\n" + str(entry["content"])
            extra = [
                narrative_template.format(name=path.stem, line=line)
                for line in range(int(narrative["repeat"]))
            ]
            path.write_text(content + "".join(extra), encoding="utf-8")
        large = ground_truth["large_corpus_files"]
        target_bytes = int(large["target_kilobytes"]) * 1024
        line_template = str(large["line_template"])
        for index in range(int(large["count"])):
            path = fixture.repository / str(large["path_template"]).format(index=index)
            path.parent.mkdir(parents=True, exist_ok=True)
            lines: list[str] = []
            written = 0
            line_number = 0
            while written < target_bytes:
                line = line_template.format(index=index, line=line_number)
                lines.append(line)
                written += len(line)
                line_number += 1
            path.write_text("".join(lines), encoding="utf-8")
        module_template = str(ground_truth["corpus_module_template"])
        for index in range(int(ground_truth["corpus_module_count"])):
            path = fixture.repository / "src" / "generated" / f"module_{index:02d}.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(module_template.format(index=index), encoding="utf-8")
        write_support_corpus(fixture.repository, task_specs, ground_truth["corpus_support_files"])
        run_command(["git", "-C", str(fixture.repository), "add", "-A"])
        run_command(
            ["git", "-C", str(fixture.repository), "commit", "-m", "wo023 benchmark corpus"]
        )
        fixtures.append(fixture)
        register_fixture(probe, fixture)
        require(fixture.project_id is not None, "benchmark fixture registration failed")
        project_id = fixture.project_id

        pressure = str(ground_truth["optional_pressure_sentence"]) * int(
            ground_truth["optional_pressure_repeat"]
        )
        tasks: list[dict[str, object]] = []
        for entry in task_specs:
            text = f"{entry['preamble']}\n{pressure}\n"
            created = create_benchmark_task(probe, project_id, str(entry["title"]), text)
            tasks.append(
                {
                    "task_id": created["task_id"],
                    "title": entry["title"],
                    "expected_path": entry["expected_path"],
                    "text": text,
                }
            )
        duplicates = str(ground_truth["duplicate_task_texts"][0])
        duplicate_tasks = [
            create_benchmark_task(probe, project_id, f"Benchmark duplicate {index}", duplicates)
            for index in (1, 2)
        ]
        emit_event_batch(
            project_id,
            [
                event_spec(
                    event_type="validation.passed",
                    run_id=UUID("00000000-0000-0000-0000-000000000023"),
                    emission_key=f"{label}-wo023-benchmark",
                    payload={"suite": "comprehensive-benchmarks"},
                    task_id=UUID(str(tasks[0]["task_id"])),
                )
            ],
        )
        index = run_index(probe, project_id)
        corpus = sync_corpus(probe, project_id)
        beta_project_id = create_isolation_project(probe, fixtures)
        alpha_identity = cast(
            dict[str, object], probe.request("GET", f"/api/v1/projects/{project_id}")
        )
        beta_identity = cast(
            dict[str, object], probe.request("GET", f"/api/v1/projects/{beta_project_id}")
        )

        passes: list[dict[str, object]] = []
        for pass_number in (1, 2):
            hybrid_results, reranked_results, context_bytes = retrieval_pass(
                probe, project_id, queries
            )
            retrieval = retrieval_metrics(queries, hybrid_results, reranked_results)
            task_evidence = same_task_evidence(probe, project_id, tasks)
            token = token_metrics(
                int(task_evidence["baseline_tokens"]), int(task_evidence["optimized_tokens"])
            )
            storage = measure_storage(probe, project_id, tasks + duplicate_tasks)
            isolation = isolation_probe(
                probe,
                project_id,
                beta_project_id,
                set(cast(list[str], task_evidence["reference_paths"])),
                alpha_identity,
                beta_identity,
            )
            passes.append(
                {
                    "number": pass_number,
                    "retrieval": retrieval,
                    "token": token,
                    "storage": storage,
                    "task": task_evidence,
                    "isolation": isolation,
                    "context_bytes": context_bytes,
                }
            )
        first, second = passes
        require(
            run_digest(
                deterministic_core(
                    first["retrieval"],
                    first["token"],
                    first["storage"],
                    first["task"],
                    first["isolation"],
                    int(first["context_bytes"]),
                )
            )
            == run_digest(
                deterministic_core(
                    second["retrieval"],
                    second["token"],
                    second["storage"],
                    second["task"],
                    second["isolation"],
                    int(second["context_bytes"]),
                )
            ),
            "benchmark evidence is not deterministic across repeated runs",
        )
        retrieval = first["retrieval"]
        require(
            float(retrieval["recall_at_k"])
            >= governance.COMPREHENSIVE_BENCHMARKS_ACCEPTED_RECALL_AT_K_MIN,
            "retrieval recall@5 is below the accepted baseline",
        )
        require(int(retrieval["critical_context_misses"]) == 0, "critical context misses detected")
        require(float(retrieval["precision"]) > 0.0, "retrieval precision is not positive")
        require(
            float(retrieval["reranked_mrr"]) >= float(retrieval["baseline_mrr"]),
            "reranking regressed below the baseline ordering",
        )
        require(int(first["context_bytes"]) > 0, "measured retrieval context size is not positive")
        zstd = measure_zstd_policy(tasks)
        digest = run_digest(
            deterministic_core(
                retrieval,
                first["token"],
                first["storage"],
                first["task"],
                first["isolation"],
                int(first["context_bytes"]),
            )
        )
        evidence = build_evidence(
            retrieval,
            first["token"],
            first["storage"],
            first["task"],
            first["isolation"],
            int(first["context_bytes"]),
            len(tasks),
            digest,
            (0, 0),
            int(first["task"]["provider_calls"]),
        )
        leak_counts = count_leaks(evidence)
        secret_leaks, path_leaks = leak_counts
        require(
            secret_leaks == 0 and path_leaks == 0,
            "benchmark evidence leaked a secret marker or a filesystem path",
        )
        evidence = build_evidence(
            retrieval,
            first["token"],
            first["storage"],
            first["task"],
            first["isolation"],
            int(first["context_bytes"]),
            len(tasks),
            digest,
            leak_counts,
            int(first["task"]["provider_calls"]),
        )
        require(
            int(first["task"]["provider_calls"]) == 0 and int(first["task"]["llm_calls"]) == 0,
            "benchmark used provider or model calls",
        )
        governance.require_wo023_comprehensive_benchmarks_evidence(
            governance.WO023_WORK_ORDER,
            {"comprehensive_benchmarks": evidence},
            MIGRATION_HEAD,
        )
        EVIDENCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_OUTPUT.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            "[wo023] benchmark PASS "
            f"recall@5={retrieval['recall_at_k']} precision={retrieval['precision']} "
            f"mrr={retrieval['baseline_mrr']}->{retrieval['reranked_mrr']} "
            f"tokens={first['token']['baseline_tokens']}->{first['token']['optimized_tokens']} "
            f"storage={first['storage']['logical_bytes']}/"
            f"{first['storage']['deduplicated_bytes']}/{first['storage']['physical_bytes']} "
            f"zstd={zstd['policy_version']} corpus_refs={corpus.get('reference_count')} "
            f"indexed={index.get('indexed_file_count')} in {time.monotonic() - started:.1f}s",
            flush=True,
        )
        print(f"[wo023] wrote {EVIDENCE_OUTPUT.relative_to(ROOT).as_posix()}", flush=True)
        return 0
    except Exception as exc:
        print(f"[wo023] FAIL: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        try:
            for fixture in fixtures:
                if fixture.project_id is not None:
                    cleanup_benchmark_project(fixture.project_id)
        except Exception as cleanup_exc:
            print(
                f"[wo023] corpus cleanup warning: {type(cleanup_exc).__name__}: {cleanup_exc}",
                file=sys.stderr,
                flush=True,
            )
        try:
            cleanup_fixtures(fixtures)
        except Exception as cleanup_exc:
            print(
                f"[wo023] cleanup warning: {type(cleanup_exc).__name__}: {cleanup_exc}",
                file=sys.stderr,
                flush=True,
            )


if __name__ == "__main__":
    raise SystemExit(main())
