from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, cast

import pytest

SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "comprehensive_benchmarks.py"


def load_benchmark_module() -> Any:
    """Load the stand-alone benchmark harness without pulling it into mypy's import graph."""

    spec = importlib.util.spec_from_file_location("wo023_comprehensive_benchmarks", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Any, module)


benchmarks = load_benchmark_module()


def test_ratio_is_bounded_and_deterministic() -> None:
    assert benchmarks.ratio(50, 100) == 0.5
    assert benchmarks.ratio(0, 100) == 0.0
    assert benchmarks.ratio(5, 0) == 0.0
    assert benchmarks.ratio(150, 100) == 1.0
    assert benchmarks.ratio(1, 3) == benchmarks.ratio(1, 3)


def test_retrieval_metrics_detect_ground_truth_and_critical_misses() -> None:
    queries = [
        {"query": "alpha", "expected_path": "src/a.py", "critical": True},
        {"query": "beta", "expected_path": "src/b.py", "critical": True},
        {"query": "gamma", "expected_path": "src/c.py", "critical": False},
    ]
    hybrid = {
        "alpha": [{"path": "src/a.py"}, {"path": "src/x.py"}],
        "beta": [{"path": "src/b.py"}],
        "gamma": [{"path": "src/y.py"}],
    }
    reranked = {
        "alpha": [{"path": "src/x.py"}, {"path": "src/a.py"}],
        "beta": [{"path": "src/b.py"}],
        "gamma": [{"path": "src/y.py"}],
    }
    metrics = benchmarks.retrieval_metrics(queries, hybrid, reranked)

    assert metrics["query_count"] == 3
    assert metrics["recall_at_k"] == round(2 / 3, 4)
    assert metrics["critical_context_misses"] == 0
    assert metrics["baseline_mrr"] == round((1 + 1 + 0) / 3, 4)
    assert metrics["reranked_mrr"] == round((1 / 2 + 1) / 3, 4)
    assert metrics["precision"] == round(2 / 4, 4)


def test_retrieval_metrics_count_critical_misses() -> None:
    queries = [{"query": "alpha", "expected_path": "src/a.py", "critical": True}]
    metrics = benchmarks.retrieval_metrics(
        queries, {"alpha": [{"path": "src/z.py"}]}, {"alpha": [{"path": "src/z.py"}]}
    )

    assert metrics["recall_at_k"] == 0.0
    assert metrics["critical_context_misses"] == 1
    assert metrics["reranked_mrr"] == 0.0


def test_token_metrics_require_a_strict_reduction() -> None:
    metrics = benchmarks.token_metrics(1000, 400)

    assert metrics["baseline_tokens"] == 1000
    assert metrics["optimized_tokens"] == 400
    assert metrics["reduction_percentage"] == 60.0
    with pytest.raises(AssertionError, match="positive baseline"):
        benchmarks.token_metrics(0, 0)
    with pytest.raises(AssertionError, match="fewer tokens"):
        benchmarks.token_metrics(1000, 1000)


def test_storage_metrics_are_ordered_and_arithmetically_consistent() -> None:
    metrics = benchmarks.storage_metrics(1000, 600, 300)

    assert metrics["dedup_ratio"] == 0.4
    assert metrics["compression_ratio"] == 0.5
    assert metrics["total_reduction_ratio"] == 0.7
    with pytest.raises(AssertionError, match="ordered and positive"):
        benchmarks.storage_metrics(1000, 600, 0)
    with pytest.raises(AssertionError, match="ordered and positive"):
        benchmarks.storage_metrics(500, 600, 300)


def test_run_digest_is_stable_and_key_order_independent() -> None:
    left = {"a": 1, "b": [1, 2, 3]}
    right = {"b": [1, 2, 3], "a": 1}

    assert benchmarks.run_digest(left) == benchmarks.run_digest(right)
    assert len(benchmarks.run_digest(left)) == 64
    assert benchmarks.run_digest({"a": 2, "b": [1, 2, 3]}) != benchmarks.run_digest(left)


def test_ground_truth_manifest_matches_the_committed_corpus() -> None:
    ground_truth = benchmarks.load_ground_truth()

    corpus_paths = {entry["path"] for entry in ground_truth["corpus_files"]}
    for query in ground_truth["queries"]:
        assert query["expected_path"] in corpus_paths
        assert query["critical"] is True
    for task in ground_truth["tasks"]:
        assert task["expected_path"] in corpus_paths
        assert len(task["preamble"]) < 192
        assert task["expected_path"] in task["preamble"]
    assert benchmarks.GROUND_TRUTH_RELATIVE in benchmarks.EVIDENCE_PATHS
    assert benchmarks.GROUND_TRUTH_PATH.is_file()


def test_evidence_matches_the_closed_governance_contract() -> None:
    retrieval = {
        "query_count": 5,
        "recall_at_k": 1.0,
        "precision": 0.5,
        "baseline_mrr": 1.0,
        "reranked_mrr": 1.0,
        "critical_context_misses": 0,
    }
    token = benchmarks.token_metrics(28_729, 5_952)
    storage = benchmarks.storage_metrics(931, 718, 527)
    evidence = benchmarks.build_evidence(
        retrieval,
        token,
        storage,
        12_345,
        3,
        3,
        15,
        15,
        benchmarks.run_digest({"fixture": True}),
    )

    assert set(evidence) == benchmarks.governance.COMPREHENSIVE_BENCHMARKS_ALLOWED_FIELDS
    assert evidence["status"] == "PASS"
    assert evidence["benchmark_families"] == ["retrieval", "token", "storage"]
    assert evidence["retrieval_recall_k"] == 5
    assert evidence["token_cache_status"] == "NOT_SUPPORTED"
    assert evidence["token_cached_tokens"] is None
    assert evidence["token_output_tokens"] is None
    assert evidence["provider_receipt_version"] == "NONE"
    assert evidence["provider_receipt_reconciled"] is False
    assert evidence["full_v01_complete_claimed"] is False
    assert evidence["production_quality_claimed_from_fixture"] is False
    assert evidence["optimized_task_success_rate"] == 1.0
    assert evidence["optimized_test_pass_rate"] == 1.0
    benchmarks.governance.require_wo023_comprehensive_benchmarks_evidence(
        benchmarks.governance.WO023_WORK_ORDER,
        {"comprehensive_benchmarks": evidence},
        benchmarks.MIGRATION_HEAD,
    )


def test_evidence_builder_rejects_fabricated_outcomes() -> None:
    retrieval = {
        "query_count": 5,
        "recall_at_k": 1.0,
        "precision": 0.5,
        "baseline_mrr": 1.0,
        "reranked_mrr": 1.0,
        "critical_context_misses": 0,
    }
    token = benchmarks.token_metrics(1_000, 400)
    storage = benchmarks.storage_metrics(1_000, 600, 300)
    digest = benchmarks.run_digest({"fixture": True})
    evidence = benchmarks.build_evidence(retrieval, token, storage, 1_000, 3, 3, 15, 15, digest)

    fabricated: tuple[tuple[str, dict[str, object], str], ...] = (
        (
            "fabricated critical miss",
            {"critical_context_misses": 1},
            "critical_context_misses=0",
        ),
        (
            "impossible storage bytes",
            {"storage_physical_bytes": 2_000},
            "logical >= deduplicated",
        ),
        (
            "zero recall",
            {"retrieval_recall_at_k": 0.0},
            "accepted baseline",
        ),
        (
            "v0.1 completion claim",
            {"full_v01_complete_claimed": True},
            "negative claims",
        ),
    )
    for _label, override, expected in fabricated:
        with pytest.raises(ValueError, match=expected):
            benchmarks.governance.require_wo023_comprehensive_benchmarks_evidence(
                benchmarks.governance.WO023_WORK_ORDER,
                {"comprehensive_benchmarks": {**evidence, **override}},
                benchmarks.MIGRATION_HEAD,
            )
    with pytest.raises(AssertionError, match="ordered and positive"):
        benchmarks.build_evidence(
            retrieval, token, benchmarks.storage_metrics(1, 1, 0), 1, 3, 3, 15, 15, digest
        )


def test_migration_head_and_evidence_paths_are_repository_relative() -> None:
    assert benchmarks.MIGRATION_HEAD == "0007_telemetry_events"
    for path in benchmarks.EVIDENCE_PATHS:
        assert not path.startswith("/")
        assert ".." not in path
        assert (benchmarks.ROOT / path).is_file()
    payload = json.loads((benchmarks.ROOT / benchmarks.GROUND_TRUTH_RELATIVE).read_text("utf-8"))
    assert payload["work_order"] == "WO-023"
