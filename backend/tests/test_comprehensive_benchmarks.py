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

DETERMINISTIC_CORE_FIELDS = {
    "recall_at_k",
    "precision",
    "baseline_mrr",
    "reranked_mrr",
    "critical_context_misses",
    "context_bytes",
    "baseline_tokens",
    "optimized_tokens",
    "reduction_percentage",
    "baseline_successes",
    "optimized_successes",
    "baseline_passes",
    "baseline_checks",
    "optimized_passes",
    "optimized_checks",
    "estimator_version",
    "removed_optional_items",
    "logical_bytes",
    "deduplicated_bytes",
    "physical_bytes",
    "foreign_hits",
    "alpha_foreign_hits",
    "own_hits",
    "identity_leaks",
    "cross_project_leaks",
}


def sample_retrieval() -> dict[str, object]:
    return {
        "query_count": 5,
        "recall_at_k": 1.0,
        "precision": 0.5,
        "baseline_mrr": 1.0,
        "reranked_mrr": 1.0,
        "critical_context_misses": 0,
    }


def sample_task_evidence(**overrides: object) -> dict[str, object]:
    """Same-task baseline/optimized evidence for three benchmark task identities."""

    measured: dict[str, object] = {
        "baseline_tokens": 28_729,
        "optimized_tokens": 5_952,
        "baseline_successes": 3,
        "optimized_successes": 3,
        "baseline_passes": 15,
        "baseline_checks": 15,
        "optimized_passes": 15,
        "optimized_checks": 15,
        "reference_paths": ["src/order_service.py"],
        "removed_optional_items": 0,
        "estimator_version": "utf8-byte-ratio-approx-v1",
        "estimate_serialization_version": "context-payload-v1",
        "provider_calls": 0,
        "llm_calls": 0,
    }
    return {**measured, **overrides}


def sample_isolation(**overrides: object) -> dict[str, object]:
    """Measured two-project isolation probe outcome."""

    measured: dict[str, object] = {
        "own_hits": 2,
        "foreign_hits": 0,
        "alpha_foreign_hits": 0,
        "probe_queries": 5,
        "identity_leaks": 0,
        "project_scoped": True,
        "cross_project_retrieval_accepted": False,
        "cross_project_leaks": 0,
    }
    return {**measured, **overrides}


def build_sample_evidence(**overrides: object) -> dict[str, object]:
    task = cast(dict[str, object], overrides.pop("task", sample_task_evidence()))
    isolation = cast(dict[str, object], overrides.pop("isolation", sample_isolation()))
    retrieval = cast(dict[str, object], overrides.pop("retrieval", sample_retrieval()))
    token = cast(
        dict[str, object],
        overrides.pop("token", benchmarks.token_metrics(28_729, 5_952)),
    )
    storage = cast(
        dict[str, object],
        overrides.pop("storage", benchmarks.storage_metrics(931, 718, 527)),
    )
    assert not overrides, f"unexpected evidence overrides: {sorted(overrides)}"
    evidence = benchmarks.build_evidence(
        retrieval,
        token,
        storage,
        task,
        isolation,
        15_505,
        3,
        benchmarks.run_digest({"fixture": True}),
        (0, 0),
        int(cast(int, task["provider_calls"])),
    )
    return cast(dict[str, object], evidence)


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
        assert "## Acceptance Criteria" in task["preamble"]
        assert "## Constraints" in task["preamble"]
    support = ground_truth["corpus_support_files"]
    assert int(support["per_task"]) >= 1
    assert "{task_index}" in support["path_template"]
    assert "{index}" in support["filler_template"]
    assert benchmarks.GROUND_TRUTH_RELATIVE in benchmarks.EVIDENCE_PATHS
    assert benchmarks.GROUND_TRUTH_PATH.is_file()


def test_support_corpus_modules_are_valid_python(tmp_path: Path) -> None:
    ground_truth = benchmarks.load_ground_truth()
    written = benchmarks.write_support_corpus(
        tmp_path,
        [dict(entry) for entry in ground_truth["tasks"]],
        ground_truth["corpus_support_files"],
    )

    assert len(written) == len(ground_truth["tasks"]) * int(
        ground_truth["corpus_support_files"]["per_task"]
    )
    for relative in written:
        path = tmp_path / relative
        assert path.is_file()
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
        assert path.parent.name == "support"
    with pytest.raises(AssertionError, match="not an object"):
        benchmarks.write_support_corpus(tmp_path, [], "unsupported")


def test_evidence_matches_the_closed_governance_contract() -> None:
    evidence = build_sample_evidence()

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


def test_task_success_and_test_pass_rates_use_the_same_task_denominator() -> None:
    task = sample_task_evidence(
        baseline_successes=2,
        optimized_successes=2,
        baseline_passes=13,
        baseline_checks=15,
        optimized_passes=14,
        optimized_checks=15,
    )
    evidence = build_sample_evidence(task=task)

    assert evidence["corpus_task_count"] == 3
    assert evidence["baseline_task_success_rate"] == round(2 / 3, 4)
    assert evidence["optimized_task_success_rate"] == round(2 / 3, 4)
    assert evidence["baseline_test_pass_rate"] == round(13 / 15, 4)
    assert evidence["optimized_test_pass_rate"] == round(14 / 15, 4)
    benchmarks.governance.require_wo023_comprehensive_benchmarks_evidence(
        benchmarks.governance.WO023_WORK_ORDER,
        {"comprehensive_benchmarks": evidence},
        benchmarks.MIGRATION_HEAD,
    )


def require_benchmark_gate(evidence: dict[str, object]) -> None:
    benchmarks.governance.require_wo023_comprehensive_benchmarks_evidence(
        benchmarks.governance.WO023_WORK_ORDER,
        {"comprehensive_benchmarks": evidence},
        benchmarks.MIGRATION_HEAD,
    )


def test_evidence_isolation_follows_the_measured_probe() -> None:
    foreign = build_sample_evidence(
        isolation=sample_isolation(
            foreign_hits=1,
            cross_project_retrieval_accepted=True,
            cross_project_leaks=1,
        )
    )
    assert foreign["cross_project_leaks"] == 1
    assert foreign["cross_project_retrieval_accepted"] is True
    with pytest.raises(ValueError, match="cross_project_retrieval_accepted"):
        require_benchmark_gate(foreign)

    identity = build_sample_evidence(
        isolation=sample_isolation(identity_leaks=1, cross_project_leaks=1)
    )
    assert identity["cross_project_leaks"] == 1
    with pytest.raises(ValueError, match="cross_project_leaks=0"):
        require_benchmark_gate(identity)

    unscoped = build_sample_evidence(isolation=sample_isolation(project_scoped=False))
    assert unscoped["project_scoped"] is False
    with pytest.raises(ValueError, match="project_scoped"):
        require_benchmark_gate(unscoped)


def test_deterministic_core_covers_every_load_bearing_metric() -> None:
    token = benchmarks.token_metrics(28_729, 5_952)
    storage = benchmarks.storage_metrics(931, 718, 527)
    task = sample_task_evidence()
    isolation = sample_isolation()
    core = benchmarks.deterministic_core(
        sample_retrieval(), token, storage, task, isolation, 15_505
    )

    assert set(core) == DETERMINISTIC_CORE_FIELDS
    digest = benchmarks.run_digest(core)
    mutations: tuple[
        tuple[str, dict[str, object], dict[str, object], dict[str, object], dict[str, object]],
        ...,
    ] = (
        ("recall", {"recall_at_k": 0.8}, {}, {}, {}),
        ("precision", {"precision": 0.4}, {}, {}, {}),
        ("baseline_mrr", {"baseline_mrr": 0.9}, {}, {}, {}),
        ("reranked_mrr", {"reranked_mrr": 0.9}, {}, {}, {}),
        ("critical misses", {"critical_context_misses": 1}, {}, {}, {}),
        ("baseline tokens", {}, {"baseline_tokens": 28_730}, {}, {}),
        ("optimized tokens", {}, {"optimized_tokens": 5_951}, {}, {}),
        ("baseline successes", {}, {}, {"baseline_successes": 2}, {}),
        ("optimized successes", {}, {}, {"optimized_successes": 2}, {}),
        ("baseline passes", {}, {}, {"baseline_passes": 14}, {}),
        ("optimized passes", {}, {}, {"optimized_passes": 14}, {}),
        ("estimator version", {}, {}, {"estimator_version": "utf8-byte-ratio-approx-v2"}, {}),
        ("trimmed optional items", {}, {}, {"removed_optional_items": 2}, {}),
        ("identity leaks", {}, {}, {}, {"identity_leaks": 1}),
        ("own hits", {}, {}, {}, {"own_hits": 3}),
        ("foreign hits", {}, {}, {}, {"foreign_hits": 1}),
        ("alpha foreign hits", {}, {}, {}, {"alpha_foreign_hits": 1}),
        ("cross-project leaks", {}, {}, {}, {"cross_project_leaks": 1}),
    )
    for label, retrieval_override, token_override, task_override, isolation_override in mutations:
        mutated = benchmarks.deterministic_core(
            {**sample_retrieval(), **retrieval_override},
            {**token, **token_override},
            storage,
            {**task, **task_override},
            {**isolation, **isolation_override},
            15_505,
        )
        assert benchmarks.run_digest(mutated) != digest, f"{label} does not affect the digest"
    assert (
        benchmarks.run_digest(
            benchmarks.deterministic_core(
                sample_retrieval(), token, storage, task, isolation, 99_999
            )
        )
        != digest
    )
    assert (
        benchmarks.run_digest(
            benchmarks.deterministic_core(
                sample_retrieval(),
                token,
                benchmarks.storage_metrics(932, 718, 527),
                task,
                isolation,
                15_505,
            )
        )
        != digest
    )


def test_count_matrix_counts_passes_and_checks() -> None:
    assert benchmarks._count_matrix([True, True, False]) == (2, 3)
    assert benchmarks._count_matrix([]) == (0, 0)
    assert benchmarks._count_matrix([True]) == (1, 1)


def test_evidence_builder_rejects_fabricated_outcomes() -> None:
    evidence = build_sample_evidence()

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
        (
            "degraded optimized task success",
            {"optimized_task_success_rate": 0.5},
            "must not degrade benchmark task success",
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
        build_sample_evidence(storage=benchmarks.storage_metrics(1, 1, 0))


def test_migration_head_and_evidence_paths_are_repository_relative() -> None:
    assert benchmarks.MIGRATION_HEAD == "0007_telemetry_events"
    for path in benchmarks.EVIDENCE_PATHS:
        assert not path.startswith("/")
        assert ".." not in path
        assert (benchmarks.ROOT / path).is_file()
    payload = json.loads((benchmarks.ROOT / benchmarks.GROUND_TRUTH_RELATIVE).read_text("utf-8"))
    assert payload["work_order"] == "WO-023"


def test_host_projects_root_honors_configured_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configured = tmp_path / "custom-projects"
    monkeypatch.setenv("HIVE_PROJECTS_ROOT", str(configured))
    assert benchmarks.host_projects_root() == configured.resolve()


def test_host_projects_root_defaults_to_repository_fixture_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HIVE_PROJECTS_ROOT", raising=False)
    assert benchmarks.host_projects_root() == (benchmarks.ROOT / ".hive-projects").resolve()
