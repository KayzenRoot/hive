from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from project_registry_integration import (
    ROOT,
    assert_equal,
    cleanup_temporary_root,
    compose,
    request,
    run,
    wait_for_health,
)

SCHEMA_REVISION = "0005_semantic_retrieval"
MANIFEST = ROOT / "benchmarks" / "retrieval_lexical_manifest.json"
BENCHMARK_OUTPUT = ROOT / "tmp" / "validation" / "retrieval-benchmark.json"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def scalar(project_name: str, environment: dict[str, str], query: str) -> str:
    result = compose(
        project_name,
        [
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "hive",
            "-d",
            "hive",
            "-Atqc",
            query,
        ],
        env=environment,
    )
    return result.stdout.strip()


def commit(repository: Path, message: str, environment: dict[str, str]) -> str:
    run(["git", "-C", str(repository), "add", "-A"], env=environment)
    run(["git", "-C", str(repository), "commit", "-m", message], env=environment)
    return run(["git", "-C", str(repository), "rev-parse", "HEAD"], env=environment).stdout.strip()


def is_relevant(result: Any, expected: dict[str, Any]) -> bool:
    if not isinstance(result, dict):
        return False
    expected_kind = expected.get("expected_source_kind")
    expected_path = expected.get("expected_path")
    expected_symbol = expected.get("expected_qualified_symbol")
    return not (
        (expected_kind and result.get("source_kind") != expected_kind)
        or (expected_path and result.get("path") != expected_path)
        or (expected_symbol and result.get("qualified_symbol") != expected_symbol)
    )


def benchmark(
    base_url: str,
    project_id: str,
    queries: list[dict[str, Any]],
    *,
    run_number: int,
) -> dict[str, Any]:
    latencies: list[float] = []
    reciprocal_ranks: list[float] = []
    recall_at_1 = 0
    recall_at_5 = 0
    critical_misses: list[str] = []
    for item in queries:
        started = time.perf_counter()
        status, payload = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/lexical",
            {"query": item["query"], "top_k": 5},
        )
        latencies.append((time.perf_counter() - started) * 1000)
        assert_equal(status, 200, f"benchmark query status: {item['query']}")
        assert isinstance(payload, dict)
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise AssertionError(f"benchmark results are not a list: {item['query']}")

        positions = [index for index, result in enumerate(results) if is_relevant(result, item)]
        if positions:
            position = positions[0]
            reciprocal_ranks.append(1 / (position + 1))
            if position == 0:
                recall_at_1 += 1
            recall_at_5 += 1
        else:
            reciprocal_ranks.append(0.0)
            if item.get("critical"):
                critical_misses.append(str(item["query"]))

    count = len(queries)
    return {
        "run": run_number,
        "query_count": count,
        "recall_at_1": recall_at_1 / count if count else 0.0,
        "recall_at_5": recall_at_5 / count if count else 0.0,
        "mrr": sum(reciprocal_ranks) / count if count else 0.0,
        "critical_context_misses": critical_misses,
        "average_latency_ms": sum(latencies) / count if count else 0.0,
        "max_latency_ms": max(latencies) if latencies else 0.0,
    }


def semantic_benchmark(
    base_url: str,
    project_id: str,
    queries: list[dict[str, Any]],
    *,
    endpoint: str,
    run_number: int,
) -> dict[str, Any]:
    latencies: list[float] = []
    reciprocal_ranks: list[float] = []
    recall_at_1 = 0
    recall_at_5 = 0
    critical_misses: list[str] = []
    for item in queries:
        started = time.perf_counter()
        status, payload = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/{endpoint}",
            {"query": item["query"], "top_k": 5},
        )
        latencies.append((time.perf_counter() - started) * 1000)
        assert_equal(status, 200, f"{endpoint} benchmark query status: {item['query']}")
        assert isinstance(payload, dict)
        results = payload.get("results", [])
        assert isinstance(results, list)
        positions = [index for index, result in enumerate(results) if is_relevant(result, item)]
        if positions:
            position = positions[0]
            reciprocal_ranks.append(1 / (position + 1))
            if position == 0:
                recall_at_1 += 1
            recall_at_5 += 1
        else:
            reciprocal_ranks.append(0.0)
            if item.get("critical"):
                critical_misses.append(str(item["query"]))
    count = len(queries)
    return {
        "run": run_number,
        "query_count": count,
        "recall_at_1": recall_at_1 / count if count else 0.0,
        "recall_at_5": recall_at_5 / count if count else 0.0,
        "mrr": sum(reciprocal_ranks) / count if count else 0.0,
        "critical_context_misses": critical_misses,
        "average_latency_ms": sum(latencies) / count if count else 0.0,
        "max_latency_ms": max(latencies) if latencies else 0.0,
    }


def rerank_benchmark(
    base_url: str,
    project_id: str,
    queries: list[dict[str, Any]],
    *,
    run_number: int,
) -> dict[str, Any]:
    latencies: list[float] = []
    reciprocal_ranks: list[float] = []
    hybrid_reciprocal_ranks: list[float] = []
    recall_at_1 = 0
    recall_at_5 = 0
    hybrid_recall_at_5 = 0
    critical_misses: list[str] = []
    strict_improvements = 0
    provenance_preserved = True
    candidate_pool_bounded = True
    for item in queries:
        started = time.perf_counter()
        status, payload = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/rerank",
            {
                "query": item["query"],
                "top_k": 5,
                "candidate_pool": 20,
            },
        )
        latencies.append((time.perf_counter() - started) * 1000)
        assert_equal(status, 200, f"rerank benchmark query status: {item['query']}")
        assert isinstance(payload, dict)
        results = payload.get("results", [])
        assert isinstance(results, list)
        assert_equal(payload.get("rerank_state"), "RERANKED", "rerank benchmark state")
        candidate_pool_bounded = candidate_pool_bounded and payload.get("candidate_pool", 101) <= 20

        hybrid_status, hybrid_payload = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/hybrid",
            {"query": item["query"], "top_k": 20},
        )
        assert_equal(hybrid_status, 200, f"hybrid comparison status: {item['query']}")
        assert isinstance(hybrid_payload, dict)
        hybrid_results = hybrid_payload.get("results", [])
        assert isinstance(hybrid_results, list)
        rerank_positions = [
            index for index, result in enumerate(results) if is_relevant(result, item)
        ]
        hybrid_positions = [
            index for index, result in enumerate(hybrid_results[:5]) if is_relevant(result, item)
        ]
        if not rerank_positions:
            if item.get("critical"):
                critical_misses.append(str(item["query"]))
            reciprocal_ranks.append(0.0)
        else:
            position = rerank_positions[0]
            reciprocal_ranks.append(1 / (position + 1))
            if position == 0:
                recall_at_1 += 1
            recall_at_5 += 1
            matching = results[position]
            pre_rank = matching.get("pre_rerank_rank")
            if isinstance(pre_rank, int) and pre_rank > position + 1:
                strict_improvements += 1
        if hybrid_positions:
            hybrid_position = hybrid_positions[0]
            hybrid_recall_at_5 += 1
            hybrid_reciprocal_ranks.append(1 / (hybrid_position + 1))
        else:
            hybrid_reciprocal_ranks.append(0.0)

        if rerank_positions:
            matching = results[rerank_positions[0]]
            matching_reference = matching.get("reference_id")
            provenance_preserved = provenance_preserved and all(
                matching.get(field) is not None
                for field in (
                    "project_id",
                    "reference_id",
                    "chunk_id",
                    "corpus_run_id",
                    "source_content_sha256",
                    "chunk_content_sha256",
                    "snippet",
                )
            )
            provenance_preserved = provenance_preserved and any(
                result.get("reference_id") == matching_reference for result in hybrid_results
            )

    count = len(queries)
    mrr = sum(reciprocal_ranks) / count if count else 0.0
    hybrid_mrr = sum(hybrid_reciprocal_ranks) / count if count else 0.0
    return {
        "run": run_number,
        "query_count": count,
        "recall_at_1": recall_at_1 / count if count else 0.0,
        "recall_at_5": recall_at_5 / count if count else 0.0,
        "mrr": mrr,
        "critical_context_misses": critical_misses,
        "average_latency_ms": sum(latencies) / count if count else 0.0,
        "max_latency_ms": max(latencies) if latencies else 0.0,
        "hybrid_recall_at_5": hybrid_recall_at_5 / count if count else 0.0,
        "hybrid_mrr": hybrid_mrr,
        "recall_at_5_gte_hybrid": recall_at_5 >= hybrid_recall_at_5,
        "mrr_gte_hybrid": mrr >= hybrid_mrr,
        "strict_rank_improvement": strict_improvements > 0,
        "strict_rank_improvements": strict_improvements,
        "candidate_pool_bounded": candidate_pool_bounded,
        "provenance_preserved": provenance_preserved,
        "mechanical_fixture_not_production_quality": True,
    }


def wait_for_fixture(port: int, label: str) -> None:
    for _ in range(30):
        try:
            fixture_status, _fixture_payload = request(f"http://127.0.0.1:{port}", "GET", "/health")
            if fixture_status == 200:
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError(f"{label} fixture did not become ready")


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    queries = manifest["queries"]
    rerank_queries = manifest.get("rerank_queries", [])
    temporary_root = Path(tempfile.mkdtemp(prefix="retrieval-", dir=ROOT / "tmp"))
    project_name = f"hive-retrieval-{os.getpid()}"
    api_port = free_port()
    dashboard_port = free_port()
    fixture_port = free_port()
    rerank_fixture_port = free_port()
    projects_root = temporary_root / "projects"
    data_root = temporary_root / "data"
    projects_root.mkdir()
    data_root.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            "HIVE_API_PORT": str(api_port),
            "HIVE_DASHBOARD_PORT": str(dashboard_port),
            "HIVE_PROJECTS_ROOT": projects_root.as_posix(),
            "HIVE_DATA_ROOT": data_root.as_posix(),
            "POSTGRES_DB": "hive",
            "POSTGRES_USER": "hive",
            "POSTGRES_PASSWORD": "hive",
            "HIVE_EMBEDDING_ENABLED": "true",
            "HIVE_EMBEDDING_BASE_URL": f"http://host.docker.internal:{fixture_port}",
            "HIVE_EMBEDDING_MODEL": "hive-fixture-v1",
            "HIVE_EMBEDDING_MODEL_REVISION": "fixture-2026-09-02",
            "HIVE_EMBEDDING_DIMENSIONS": "8",
            "HIVE_EMBEDDING_BATCH_SIZE": "2",
            "HIVE_EMBEDDING_CANDIDATE_POOL": "20",
            "HIVE_RERANK_ENABLED": "false",
            "HIVE_RERANK_BASE_URL": f"http://host.docker.internal:{rerank_fixture_port}",
            "HIVE_RERANK_MODEL": "hive-rerank-fixture-v1",
            "HIVE_RERANK_MODEL_REVISION": "fixture-2026-09-02",
            "HIVE_RERANK_TIMEOUT_SECONDS": "1",
            "HIVE_RERANK_CANDIDATE_POOL": "20",
            "HIVE_RERANK_MAX_DOCUMENT_CHARS": "6000",
            "HIVE_RERANK_MAX_QUERY_CHARS": "512",
        }
    )
    repository = projects_root / "retrieval-sample"
    isolated = projects_root / "retrieval-isolated"
    repository.mkdir()
    isolated.mkdir()
    git_environment = environment.copy()
    for path in (repository, isolated):
        run(["git", "init", "-b", "main", str(path)], env=git_environment)
        run(
            ["git", "-C", str(path), "config", "user.email", "hive-test@example.invalid"],
            env=git_environment,
        )
        run(
            ["git", "-C", str(path), "config", "user.name", "HIVE Integration Test"],
            env=git_environment,
        )

    (repository / "src").mkdir()
    (repository / "src" / "order_service.py").write_text(
        "class OrderService:\n"
        "    def get_project_order(self, order_id):\n"
        '        return {"order_id": order_id}\n'
        "\n"
        "def build_order_index(orders):\n"
        '    return {order["order_id"]: order for order in orders}\n',
        encoding="utf-8",
    )
    (repository / "src" / "api.py").write_text(
        'def health_check():\n    return {"status": "ok"}\n',
        encoding="utf-8",
    )
    (repository / "README.md").write_text(
        "# Retrieval fixture\n\nA small real Git project for lexical retrieval.\n",
        encoding="utf-8",
    )
    (repository / "src" / "durability.py").write_text(
        "def durable_retention_ledger():\n"
        '    """Durable retention ledger survives process recovery through\n'
        '    replay-safe checkpoints."""\n'
        '    return "continuation-guaranteed"\n',
        encoding="utf-8",
    )
    first_head = commit(repository, "initial retrieval fixture", git_environment)

    (isolated / "worker.py").write_text(
        "def unrelated_worker():\n    return 'project-b'\n", encoding="utf-8"
    )
    commit(isolated, "isolated fixture", git_environment)

    fixture_process = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "scripts" / "embedding_fixture.py"),
            "--host",
            "0.0.0.0",
            "--port",
            str(fixture_port),
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    rerank_fixture_process = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "scripts" / "rerank_fixture.py"),
            "--host",
            "0.0.0.0",
            "--port",
            str(rerank_fixture_port),
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_for_fixture(fixture_port, "embedding")
        wait_for_fixture(rerank_fixture_port, "rerank")
        compose(project_name, ["up", "-d", "--build"], env=environment)
        migration = scalar(project_name, environment, "SELECT version_num FROM alembic_version")
        assert_equal(migration, SCHEMA_REVISION, "retrieval migration revision")
        base_url = f"http://127.0.0.1:{api_port}"
        wait_for_health(base_url)

        status, project = request(
            base_url,
            "POST",
            "/api/v1/projects",
            {"name": "Retrieval Sample", "relative_path": "retrieval-sample"},
        )
        assert_equal(status, 201, "retrieval project registration")
        assert isinstance(project, dict)
        project_id = str(project["project_id"])
        status, other_project = request(
            base_url,
            "POST",
            "/api/v1/projects",
            {"name": "Retrieval Isolated", "relative_path": "retrieval-isolated"},
        )
        assert_equal(status, 201, "retrieval isolated project registration")
        assert isinstance(other_project, dict)
        other_project_id = str(other_project["project_id"])

        status, indexed = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
        assert_equal(status, 200, "retrieval project index")
        assert isinstance(indexed, dict)
        assert_equal(indexed["status"], "COMPLETED", "retrieval project index state")
        assert_equal(indexed["repository_head_sha"], first_head, "retrieval indexed head")
        status, isolated_index = request(
            base_url, "POST", f"/api/v1/projects/{other_project_id}/index"
        )
        assert_equal(status, 200, "isolated retrieval project index")
        assert isinstance(isolated_index, dict)

        status, task = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/tasks/text",
            {
                "title": "Checkout manifest task",
                "format": "markdown",
                "text": "Rebuild the checkout manifest before the lexical provenance review.",
            },
        )
        assert_equal(status, 201, "retrieval task intake")
        assert isinstance(task, dict)
        task_id = str(task["task_id"])
        status, duplicate_task = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/tasks/text",
            {
                "title": "Duplicate checkout manifest task",
                "format": "text",
                "text": "Rebuild the checkout manifest before the lexical provenance review.",
            },
        )
        assert_equal(status, 201, "duplicate retrieval task intake")
        assert isinstance(duplicate_task, dict)
        duplicate_task_id = str(duplicate_task["task_id"])
        status, isolated_task = request(
            base_url,
            "POST",
            f"/api/v1/projects/{other_project_id}/tasks/text",
            {
                "title": "Isolated duplicate checkout manifest task",
                "format": "text",
                "text": "Rebuild the checkout manifest before the lexical provenance review.",
            },
        )
        assert_equal(status, 201, "isolated duplicate retrieval task intake")
        assert isinstance(isolated_task, dict)
        isolated_task_id = str(isolated_task["task_id"])

        status, synced = request(
            base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/corpus/sync"
        )
        assert_equal(status, 200, "first retrieval sync")
        assert isinstance(synced, dict)
        assert_equal(synced["status"], "COMPLETED", "first retrieval sync state")
        if synced["repository_source_count"] < 3 or synced["task_source_count"] != 2:
            raise AssertionError(f"unexpected retrieval source counts: {synced}")
        if synced["reference_count"] <= synced["repository_source_count"]:
            raise AssertionError(f"symbol/task provenance was not created: {synced}")

        status, corpus = request(base_url, "GET", f"/api/v1/projects/{project_id}/retrieval/corpus")
        assert_equal(status, 200, "retrieval corpus status")
        assert isinstance(corpus, dict)
        assert_equal(corpus["state"], "CURRENT", "retrieval corpus current state")
        assert_equal(corpus["task_reference_count"] > 0, True, "task references")

        status, semantic_sync = request(
            base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/semantic/sync"
        )
        assert_equal(status, 200, "first semantic sync")
        assert isinstance(semantic_sync, dict)
        assert_equal(semantic_sync["status"], "COMPLETED", "first semantic sync state")
        assert_equal(
            semantic_sync["current_chunk_count"],
            semantic_sync["newly_embedded_count"],
            "semantic complete coverage",
        )
        status, semantic_state = request(
            base_url, "GET", f"/api/v1/projects/{project_id}/retrieval/semantic"
        )
        assert_equal(status, 200, "semantic status")
        assert isinstance(semantic_state, dict)
        assert_equal(semantic_state["state"], "CURRENT", "semantic current state")
        assert_equal(semantic_state["profile"]["dimensions"], 8, "semantic dimensions")
        vector_type = scalar(
            project_name,
            environment,
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "WHERE c.relname = 'retrieval_chunk_embeddings' AND a.attname = 'embedding'",
        )
        assert_equal(vector_type, "vector", "actual pgvector column type")
        embedding_rows = scalar(
            project_name,
            environment,
            "SELECT count(*) FROM retrieval_chunk_embeddings",
        )
        assert_equal(
            int(embedding_rows), semantic_sync["current_chunk_count"], "persisted embedding count"
        )

        status, semantic_symbol = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/semantic",
            {"query": "project order service symbol", "top_k": 5},
        )
        assert_equal(status, 200, "semantic symbol query")
        assert isinstance(semantic_symbol, dict)
        if not any(
            result.get("qualified_symbol") == "OrderService.get_project_order"
            for result in semantic_symbol["results"]
        ):
            raise AssertionError(f"semantic symbol was not retrieved: {semantic_symbol}")
        semantic_challenge = [
            {
                "query": "resilient continuity semantics",
                "expected_path": "src/durability.py",
                "critical": True,
            }
        ]
        status, lexical_challenge = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/lexical",
            {"query": semantic_challenge[0]["query"], "top_k": 5},
        )
        assert_equal(status, 200, "lexical semantic challenge")
        assert isinstance(lexical_challenge, dict)
        lexical_challenge_recovered = any(
            result.get("path") == "src/durability.py" for result in lexical_challenge["results"]
        )
        assert_equal(lexical_challenge_recovered, False, "lexical challenge remains weak")
        status, hybrid_challenge = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/hybrid",
            {"query": semantic_challenge[0]["query"], "top_k": 5},
        )
        assert_equal(status, 200, "hybrid semantic challenge")
        assert isinstance(hybrid_challenge, dict)
        assert_equal(hybrid_challenge["state"], "HYBRID", "hybrid state")
        if not any(
            result.get("path") == "src/durability.py" for result in hybrid_challenge["results"]
        ):
            raise AssertionError(f"hybrid challenge was not recovered: {hybrid_challenge}")
        before_embedding_stats = request(f"http://127.0.0.1:{fixture_port}", "GET", "/stats")[1]
        status, semantic_reused = request(
            base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/semantic/sync"
        )
        assert_equal(status, 200, "unchanged semantic sync")
        assert isinstance(semantic_reused, dict)
        assert_equal(semantic_reused["newly_embedded_count"], 0, "semantic reuse new count")
        assert_equal(
            semantic_reused["reused_embedding_count"],
            semantic_reused["current_chunk_count"],
            "semantic reuse coverage",
        )
        after_embedding_stats = request(f"http://127.0.0.1:{fixture_port}", "GET", "/stats")[1]
        assert isinstance(before_embedding_stats, dict)
        assert isinstance(after_embedding_stats, dict)
        assert_equal(
            after_embedding_stats["request_count"],
            before_embedding_stats["request_count"],
            "semantic sync avoids provider calls on reuse",
        )

        status, symbol_results = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/lexical",
            {"query": "OrderService.get_project_order", "top_k": 5},
        )
        assert_equal(status, 200, "exact symbol lexical query")
        assert isinstance(symbol_results, dict)
        results = symbol_results["results"]
        if not any(
            result.get("source_kind") == "REPOSITORY_SYMBOL"
            and result.get("qualified_symbol") == "OrderService.get_project_order"
            for result in results
        ):
            raise AssertionError(f"exact symbol was not retrieved: {symbol_results}")
        symbol_result = next(
            result
            for result in results
            if result.get("qualified_symbol") == "OrderService.get_project_order"
        )
        assert_equal(symbol_result["start_line"], 2, "symbol provenance start line")
        assert_equal(symbol_result["end_line"], 3, "symbol provenance end line")

        status, path_results = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/lexical",
            {"query": "src/order_service.py", "top_k": 5},
        )
        assert_equal(status, 200, "path lexical query")
        assert isinstance(path_results, dict)
        if not any(
            result.get("path") == "src/order_service.py" for result in path_results["results"]
        ):
            raise AssertionError(f"path was not retrieved: {path_results}")

        status, task_results = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/lexical",
            {"query": "rebuild checkout manifest", "top_k": 5},
        )
        assert_equal(status, 200, "task lexical query")
        assert isinstance(task_results, dict)
        if not any(
            result.get("source_kind") == "TASK"
            and result.get("task_id") in {task_id, duplicate_task_id}
            for result in task_results["results"]
        ):
            raise AssertionError(f"task was not retrieved: {task_results}")
        status, duplicate_results = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/lexical",
            {"query": "rebuild checkout manifest", "top_k": 5, "source_kind": "TASK"},
        )
        assert_equal(status, 200, "duplicate task lexical query")
        assert isinstance(duplicate_results, dict)
        duplicate_candidates = duplicate_results["results"]
        assert_equal(len(duplicate_candidates), 1, "duplicate task candidate collapse")
        if duplicate_candidates[0].get("task_id") not in {task_id, duplicate_task_id}:
            raise AssertionError(f"unexpected duplicate representative: {duplicate_results}")

        status, isolated_sync = request(
            base_url, "POST", f"/api/v1/projects/{other_project_id}/retrieval/corpus/sync"
        )
        assert_equal(status, 200, "isolated duplicate retrieval sync")
        assert isinstance(isolated_sync, dict)
        status, isolated_semantic_sync = request(
            base_url,
            "POST",
            f"/api/v1/projects/{other_project_id}/retrieval/semantic/sync",
        )
        assert_equal(status, 200, "isolated semantic sync")
        assert isinstance(isolated_semantic_sync, dict)
        assert_equal(isolated_semantic_sync["status"], "COMPLETED", "isolated semantic state")
        status, isolated_task_results = request(
            base_url,
            "POST",
            f"/api/v1/projects/{other_project_id}/retrieval/lexical",
            {"query": "rebuild checkout manifest", "top_k": 5, "source_kind": "TASK"},
        )
        assert_equal(status, 200, "isolated duplicate task lexical query")
        assert isinstance(isolated_task_results, dict)
        isolated_candidates = isolated_task_results["results"]
        assert_equal(len(isolated_candidates), 1, "cross-project duplicate candidate isolation")
        assert_equal(
            isolated_candidates[0].get("task_id"), isolated_task_id, "isolated task provenance"
        )

        status, isolated_query = request(
            base_url,
            "POST",
            f"/api/v1/projects/{other_project_id}/retrieval/lexical",
            {"query": "OrderService.get_project_order", "top_k": 5},
        )
        assert_equal(status, 200, "cross-project lexical query")
        assert isinstance(isolated_query, dict)
        assert_equal(isolated_query["results"], [], "cross-project retrieval isolation")
        status, isolated_semantic_query = request(
            base_url,
            "POST",
            f"/api/v1/projects/{other_project_id}/retrieval/semantic",
            {
                "query": "project order service symbol",
                "top_k": 5,
                "source_kind": "REPOSITORY_SYMBOL",
            },
        )
        assert_equal(status, 200, "cross-project semantic query")
        assert isinstance(isolated_semantic_query, dict)
        if any(
            result.get("qualified_symbol") == "OrderService.get_project_order"
            for result in isolated_semantic_query["results"]
        ):
            raise AssertionError(
                f"cross-project semantic result leaked OrderService: {isolated_semantic_query}"
            )

        first_benchmark = benchmark(base_url, project_id, queries, run_number=1)
        second_benchmark = benchmark(base_url, project_id, queries, run_number=2)
        for result in (first_benchmark, second_benchmark):
            assert_equal(result["critical_context_misses"], [], "critical benchmark misses")
            if result["recall_at_5"] < 0.90:
                raise AssertionError(f"lexical recall@5 below gate: {result}")
        lexical_extended = benchmark(
            base_url, project_id, queries + semantic_challenge, run_number=1
        )
        first_semantic_benchmark = semantic_benchmark(
            base_url,
            project_id,
            semantic_challenge,
            endpoint="semantic",
            run_number=1,
        )
        second_semantic_benchmark = semantic_benchmark(
            base_url,
            project_id,
            semantic_challenge,
            endpoint="semantic",
            run_number=2,
        )
        first_hybrid_benchmark = semantic_benchmark(
            base_url,
            project_id,
            semantic_challenge,
            endpoint="hybrid",
            run_number=1,
        )
        second_hybrid_benchmark = semantic_benchmark(
            base_url,
            project_id,
            semantic_challenge,
            endpoint="hybrid",
            run_number=2,
        )
        assert_equal(
            first_semantic_benchmark["critical_context_misses"],
            [],
            "semantic challenge recovery",
        )
        assert_equal(
            first_hybrid_benchmark["critical_context_misses"],
            [],
            "hybrid challenge recovery",
        )
        if first_hybrid_benchmark["recall_at_5"] < lexical_extended["recall_at_5"]:
            raise AssertionError(
                "hybrid recall@5 regressed against the extended lexical set: "
                f"{first_hybrid_benchmark} vs {lexical_extended}"
            )
        rerank_query = rerank_queries[0]["query"]
        status, disabled_status = request(
            base_url,
            "GET",
            f"/api/v1/projects/{project_id}/retrieval/rerank/status",
        )
        assert_equal(status, 200, "disabled rerank status")
        assert isinstance(disabled_status, dict)
        assert_equal(disabled_status["enabled"], False, "rerank disabled by default")
        assert_equal(disabled_status["configured"], False, "disabled rerank not configured")
        status, disabled_hybrid = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/hybrid",
            {"query": rerank_query, "top_k": 20},
        )
        assert_equal(status, 200, "disabled rerank hybrid comparison")
        assert isinstance(disabled_hybrid, dict)
        status, disabled_rerank = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/rerank",
            {"query": rerank_query, "top_k": 5, "candidate_pool": 20},
        )
        assert_equal(status, 200, "disabled rerank fallback")
        assert isinstance(disabled_rerank, dict)
        assert_equal(
            disabled_rerank["rerank_state"],
            "RERANK_FALLBACK_DISABLED",
            "disabled rerank state",
        )
        assert_equal(
            [item["reference_id"] for item in disabled_rerank["results"]],
            [item["reference_id"] for item in disabled_hybrid["results"][:5]],
            "disabled rerank exact order",
        )
        if any(item.get("rerank_score") is not None for item in disabled_rerank["results"]):
            raise AssertionError("disabled rerank returned a score")

        environment["HIVE_RERANK_ENABLED"] = "true"
        compose(
            project_name,
            ["up", "-d", "--force-recreate", "api"],
            env=environment,
        )
        wait_for_health(base_url)
        status, active_status = request(
            base_url,
            "GET",
            f"/api/v1/projects/{project_id}/retrieval/rerank/status",
        )
        assert_equal(status, 200, "active rerank status")
        assert isinstance(active_status, dict)
        assert_equal(active_status["enabled"], True, "rerank enabled status")
        assert_equal(active_status["configured"], True, "rerank configured status")
        profile = active_status.get("reranker_profile")
        assert isinstance(profile, dict)
        assert_equal(profile["model"], "hive-rerank-fixture-v1", "rerank profile model")
        assert isinstance(profile.get("identity_fingerprint"), str)
        if "api_key" in json.dumps(active_status).casefold():
            raise AssertionError("rerank status exposed a secret field")

        first_rerank_benchmark = rerank_benchmark(
            base_url, project_id, rerank_queries, run_number=1
        )
        second_rerank_benchmark = rerank_benchmark(
            base_url, project_id, rerank_queries, run_number=2
        )
        for result in (first_rerank_benchmark, second_rerank_benchmark):
            assert_equal(result["critical_context_misses"], [], "rerank critical misses")
            assert_equal(result["recall_at_5_gte_hybrid"], True, "rerank recall gate")
            assert_equal(result["mrr_gte_hybrid"], True, "rerank mrr gate")
            assert_equal(result["strict_rank_improvement"], True, "rerank strict improvement")
            assert_equal(result["candidate_pool_bounded"], True, "rerank candidate pool bound")
            assert_equal(result["provenance_preserved"], True, "rerank provenance")

        status, reversed_rerank = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/rerank",
            {
                "query": "OrderService __fixture_rerank_reversed__",
                "top_k": 5,
                "candidate_pool": 20,
            },
        )
        assert_equal(status, 200, "reversed explicit index rerank")
        assert isinstance(reversed_rerank, dict)
        assert_equal(reversed_rerank["rerank_state"], "RERANKED", "reversed rerank state")
        if not reversed_rerank["results"]:
            raise AssertionError("reversed rerank returned no candidates")

        failure_query = "OrderService __fixture_rerank_provider_error__"
        status, failure_hybrid = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/hybrid",
            {"query": failure_query, "top_k": 20},
        )
        assert_equal(status, 200, "rerank provider failure hybrid baseline")
        assert isinstance(failure_hybrid, dict)
        status, provider_rerank = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/rerank",
            {"query": failure_query, "top_k": 5, "candidate_pool": 20},
        )
        assert_equal(status, 200, "rerank provider failure fallback")
        assert isinstance(provider_rerank, dict)
        assert_equal(
            provider_rerank["rerank_state"],
            "RERANK_FALLBACK_PROVIDER_ERROR",
            "rerank provider failure state",
        )
        assert_equal(
            [item["reference_id"] for item in provider_rerank["results"]],
            [item["reference_id"] for item in failure_hybrid["results"][:5]],
            "rerank provider failure exact order",
        )
        status, strict_failure = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/rerank",
            {
                "query": failure_query,
                "top_k": 5,
                "candidate_pool": 20,
                "strict_rerank": True,
            },
        )
        assert_equal(status, 503, "strict rerank provider failure")
        assert isinstance(strict_failure, dict)
        if len(str(strict_failure.get("detail", ""))) > 256:
            raise AssertionError("strict rerank error was not bounded")

        invalid_query = "OrderService __fixture_rerank_duplicate__"
        status, invalid_rerank = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/rerank",
            {"query": invalid_query, "top_k": 5, "candidate_pool": 20},
        )
        assert_equal(status, 200, "invalid rerank response fallback")
        assert isinstance(invalid_rerank, dict)
        assert_equal(
            invalid_rerank["rerank_state"],
            "RERANK_FALLBACK_INVALID_RESPONSE",
            "invalid rerank response state",
        )
        if any(item.get("rerank_score") is not None for item in invalid_rerank["results"]):
            raise AssertionError("invalid rerank response returned scores")

        rerank_fixture_process.terminate()
        rerank_fixture_process.wait(timeout=10)
        status, provider_down_rerank = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/rerank",
            {"query": "OrderService provider down", "top_k": 5, "candidate_pool": 20},
        )
        assert_equal(status, 200, "rerank provider down fallback")
        assert isinstance(provider_down_rerank, dict)
        assert_equal(
            provider_down_rerank["rerank_state"],
            "RERANK_FALLBACK_PROVIDER_ERROR",
            "rerank provider down state",
        )
        rerank_fixture_process = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "scripts" / "rerank_fixture.py"),
                "--host",
                "0.0.0.0",
                "--port",
                str(rerank_fixture_port),
            ],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        wait_for_fixture(rerank_fixture_port, "rerank restart")

        status, provider_fallback = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/hybrid",
            {"query": "__fixture_provider_error__", "top_k": 5},
        )
        assert_equal(status, 200, "provider failure hybrid fallback")
        assert isinstance(provider_fallback, dict)
        assert_equal(
            provider_fallback["state"],
            "LEXICAL_FALLBACK_PROVIDER_ERROR",
            "provider failure fallback state",
        )
        status, provider_semantic_only = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/semantic",
            {"query": "__fixture_provider_error__", "top_k": 5},
        )
        assert_equal(status, 503, "provider failure semantic-only response")

        status, reused = request(
            base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/corpus/sync"
        )
        assert_equal(status, 200, "unchanged retrieval sync")
        assert isinstance(reused, dict)
        if reused["new_chunk_count"] != 0 or reused["new_reference_count"] != 0:
            raise AssertionError(f"unchanged sync did not reuse derived data: {reused}")
        if reused["reused_chunk_count"] == 0 or reused["reused_reference_count"] == 0:
            raise AssertionError(f"unchanged sync reported no reuse: {reused}")

        original_source = (repository / "src" / "order_service.py").read_text(encoding="utf-8")
        (repository / "src" / "order_service.py").write_text(
            original_source + "\ndef new_checkout_route():\n    return True\n", encoding="utf-8"
        )
        changed_head = commit(repository, "add checkout route", git_environment)
        status, reindexed = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
        assert_equal(status, 200, "changed repository re-index")
        assert isinstance(reindexed, dict)
        assert_equal(reindexed["repository_head_sha"], changed_head, "changed repository head")
        status, changed_sync = request(
            base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/corpus/sync"
        )
        assert_equal(status, 200, "changed retrieval sync")
        assert isinstance(changed_sync, dict)
        if changed_sync["new_chunk_count"] == 0:
            raise AssertionError(f"changed file did not create a new chunk: {changed_sync}")
        status, stale_semantic = request(
            base_url, "GET", f"/api/v1/projects/{project_id}/retrieval/semantic"
        )
        assert_equal(status, 200, "semantic status after lexical change")
        assert isinstance(stale_semantic, dict)
        assert_equal(stale_semantic["state"], "STALE", "semantic stale after lexical change")
        status, stale_hybrid = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/hybrid",
            {"query": semantic_challenge[0]["query"], "top_k": 5},
        )
        assert_equal(status, 200, "stale semantic hybrid fallback")
        assert isinstance(stale_hybrid, dict)
        assert_equal(stale_hybrid["state"], "LEXICAL_FALLBACK_SEMANTIC_STALE", "stale fallback")
        status, changed_semantic_sync = request(
            base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/semantic/sync"
        )
        assert_equal(status, 200, "changed semantic resync")
        assert isinstance(changed_semantic_sync, dict)
        assert_equal(changed_semantic_sync["status"], "COMPLETED", "changed semantic resync state")

        (repository / "src" / "api.py").unlink()
        removed_head = commit(repository, "remove API fixture", git_environment)
        status, removed_index = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
        assert_equal(status, 200, "removed repository re-index")
        assert isinstance(removed_index, dict)
        assert_equal(removed_index["repository_head_sha"], removed_head, "removed repository head")
        status, removed_sync = request(
            base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/corpus/sync"
        )
        assert_equal(status, 200, "removed retrieval sync")
        assert isinstance(removed_sync, dict)
        if removed_sync["removed_reference_count"] == 0:
            raise AssertionError(f"removed file references remained current: {removed_sync}")
        status, removed_query = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/lexical",
            {"query": "health_check", "top_k": 5},
        )
        assert_equal(status, 200, "removed source lexical query")
        assert isinstance(removed_query, dict)
        assert_equal(removed_query["results"], [], "removed source absent")

        status, new_task = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/tasks/text",
            {
                "title": "Second task",
                "format": "text",
                "text": "Validate the second task watermark in the retrieval corpus.",
            },
        )
        assert_equal(status, 201, "second retrieval task intake")
        status, task_sync = request(
            base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/corpus/sync"
        )
        assert_equal(status, 200, "new task retrieval sync")
        assert isinstance(task_sync, dict)
        assert_equal(task_sync["task_source_count"], 3, "task source expansion")
        if task_sync["task_reference_count"] <= synced["task_reference_count"]:
            raise AssertionError(f"new task did not expand task corpus: {task_sync}")

        (repository / "src" / "order_service.py").write_text(
            "mutated after indexing\n", encoding="utf-8"
        )
        status, stale = request(
            base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/corpus/sync"
        )
        assert_equal(status, 200, "stale source sync response")
        assert isinstance(stale, dict)
        assert_equal(stale["status"], "STALE", "stale source status")
        assert_equal(stale["error"], "repository_source_stale", "stale source error")
        status, after_stale = request(
            base_url, "GET", f"/api/v1/projects/{project_id}/retrieval/corpus"
        )
        assert_equal(status, 200, "stale corpus status")
        assert isinstance(after_stale, dict)
        assert_equal(after_stale["state"], "STALE", "stale corpus state")
        status, preserved = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/lexical",
            {"query": "OrderService.get_project_order", "top_k": 5},
        )
        assert_equal(status, 200, "query after failed sync")
        assert isinstance(preserved, dict)
        if not preserved["results"]:
            raise AssertionError("failed sync destroyed the previous valid corpus")

        (repository / "src" / "order_service.py").write_text(
            original_source + "\n", encoding="utf-8"
        )
        restored_head = commit(repository, "restore indexed source", git_environment)
        status, restored_index = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
        assert_equal(status, 200, "restored repository re-index")
        assert isinstance(restored_index, dict)
        assert_equal(restored_index["repository_head_sha"], restored_head, "restored head")
        status, recovered = request(
            base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/corpus/sync"
        )
        assert_equal(status, 200, "recovered retrieval sync")
        assert isinstance(recovered, dict)
        assert_equal(recovered["status"], "COMPLETED", "recovered retrieval state")

        status, inventory_baseline = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/lexical",
            {"query": "OrderService.get_project_order", "top_k": 5},
        )
        assert_equal(status, 200, "race baseline lexical query")
        assert isinstance(inventory_baseline, dict)
        if not inventory_baseline["results"]:
            raise AssertionError("race baseline corpus is not queryable")

        staged_path = repository / "src" / "staged_inventory_race.py"
        staged_path.write_text("def staged_only():\n    return True\n", encoding="utf-8")
        run(
            ["git", "-C", str(repository), "add", "src/staged_inventory_race.py"],
            env=git_environment,
        )
        try:
            status, inventory_race = request(
                base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/corpus/sync"
            )
            assert_equal(status, 200, "inventory race sync response")
            assert isinstance(inventory_race, dict)
            assert_equal(inventory_race["status"], "STALE", "inventory race status")
            assert_equal(inventory_race["error"], "repository_index_stale", "inventory race error")
            status, inventory_preserved = request(
                base_url,
                "POST",
                f"/api/v1/projects/{project_id}/retrieval/lexical",
                {"query": "OrderService.get_project_order", "top_k": 5},
            )
            assert_equal(status, 200, "inventory race preserved query")
            assert isinstance(inventory_preserved, dict)
            if not inventory_preserved["results"]:
                raise AssertionError("inventory race destroyed the previous valid corpus")
        finally:
            run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "restore",
                    "--staged",
                    "src/staged_inventory_race.py",
                ],
                env=git_environment,
            )
            staged_path.unlink()

        (repository / "src" / "head_race.py").write_text(
            "def committed_after_bundle():\n    return True\n", encoding="utf-8"
        )
        head_race_head = commit(repository, "commit after retrieval bundle", git_environment)
        status, head_race = request(
            base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/corpus/sync"
        )
        assert_equal(status, 200, "head race sync response")
        assert isinstance(head_race, dict)
        assert_equal(head_race["status"], "STALE", "head race status")
        assert_equal(head_race["error"], "repository_index_stale", "head race error")
        status, head_preserved = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/lexical",
            {"query": "OrderService.get_project_order", "top_k": 5},
        )
        assert_equal(status, 200, "head race preserved query")
        assert isinstance(head_preserved, dict)
        if not head_preserved["results"]:
            raise AssertionError("head race destroyed the previous valid corpus")
        status, race_reindex = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
        assert_equal(status, 200, "head race recovery index")
        assert isinstance(race_reindex, dict)
        assert_equal(race_reindex["repository_head_sha"], head_race_head, "head race reindex head")
        status, race_recovered = request(
            base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/corpus/sync"
        )
        assert_equal(status, 200, "head race recovery sync")
        assert isinstance(race_recovered, dict)
        assert_equal(race_recovered["status"], "COMPLETED", "head race recovery state")
        status, final_semantic_sync = request(
            base_url, "POST", f"/api/v1/projects/{project_id}/retrieval/semantic/sync"
        )
        assert_equal(status, 200, "final semantic resync")
        assert isinstance(final_semantic_sync, dict)
        assert_equal(final_semantic_sync["status"], "COMPLETED", "final semantic state")

        compose(project_name, ["restart", "redis"], env=environment)
        compose(project_name, ["restart", "api"], env=environment)
        wait_for_health(base_url)
        status, after_restart = request(
            base_url, "GET", f"/api/v1/projects/{project_id}/retrieval/corpus"
        )
        assert_equal(status, 200, "retrieval status after restart")
        assert isinstance(after_restart, dict)
        assert_equal(after_restart["state"], "CURRENT", "retrieval persistence after restart")
        status, semantic_after_restart = request(
            base_url, "GET", f"/api/v1/projects/{project_id}/retrieval/semantic"
        )
        assert_equal(status, 200, "semantic status after restart")
        assert isinstance(semantic_after_restart, dict)
        assert_equal(
            semantic_after_restart["state"], "CURRENT", "semantic persistence after restart"
        )
        status, rerank_after_restart = request(
            base_url,
            "GET",
            f"/api/v1/projects/{project_id}/retrieval/rerank/status",
        )
        assert_equal(status, 200, "rerank status after restart")
        assert isinstance(rerank_after_restart, dict)
        assert_equal(rerank_after_restart["enabled"], True, "rerank enabled after restart")
        assert_equal(rerank_after_restart["configured"], True, "rerank configured after restart")

        benchmark_result = {
            "schema_version": 3,
            "fixture": manifest["name"],
            "repository": "KayzenRoot/hive",
            "work_order": "WO-008",
            "project_id": project_id,
            "query_count": first_benchmark["query_count"],
            "recall_at_1": first_benchmark["recall_at_1"],
            "recall_at_5": first_benchmark["recall_at_5"],
            "mrr": first_benchmark["mrr"],
            "critical_context_misses": first_benchmark["critical_context_misses"],
            "average_latency_ms": first_benchmark["average_latency_ms"],
            "max_latency_ms": first_benchmark["max_latency_ms"],
            "reproducibility": {
                "runs": [first_benchmark, second_benchmark],
                "same_query_count": first_benchmark["query_count"]
                == second_benchmark["query_count"],
                "same_recall_at_5": first_benchmark["recall_at_5"]
                == second_benchmark["recall_at_5"],
            },
            "semantic": {
                "queries": semantic_challenge,
                "run_1": first_semantic_benchmark,
                "run_2": second_semantic_benchmark,
                "provider": "deterministic local OpenAI-compatible fixture",
                "mechanical_fixture_not_production_quality": True,
            },
            "hybrid": {
                "run_1": first_hybrid_benchmark,
                "run_2": second_hybrid_benchmark,
                "fusion": "weighted reciprocal rank fusion",
                "rrf_k": 60,
            },
            "rerank": {
                "queries": rerank_queries,
                "run_1": first_rerank_benchmark,
                "run_2": second_rerank_benchmark,
                "provider": "deterministic local OpenAI-compatible fixture",
                "disabled_exact_fallback": True,
                "invalid_response_exact_fallback": True,
                "provider_failure_exact_fallback": True,
                "provider_down_exact_fallback": True,
                "strict_failure_bounded": True,
                "profile_visible_without_secret": True,
                "reproducible": all(
                    first_rerank_benchmark[field] == second_rerank_benchmark[field]
                    for field in (
                        "query_count",
                        "recall_at_1",
                        "recall_at_5",
                        "mrr",
                        "critical_context_misses",
                        "hybrid_recall_at_5",
                        "hybrid_mrr",
                        "recall_at_5_gte_hybrid",
                        "mrr_gte_hybrid",
                        "strict_rank_improvement",
                        "strict_rank_improvements",
                    )
                ),
            },
            "corpus": {
                "chunks": race_recovered["chunk_count"],
                "references": race_recovered["reference_count"],
                "repository_references": race_recovered["repository_reference_count"],
                "task_references": race_recovered["task_reference_count"],
            },
            "thresholds": {
                "recall_at_5_minimum": 0.90,
                "critical_queries_top_5": True,
                "cross_project_isolation": True,
                "hybrid_recall_at_5_gte_extended_lexical": True,
                "semantic_challenge_recovered": True,
                "rerank_recall_at_5_gte_hybrid": first_rerank_benchmark["recall_at_5_gte_hybrid"],
                "rerank_mrr_gte_hybrid": first_rerank_benchmark["mrr_gte_hybrid"],
                "rerank_strict_rank_improvement": first_rerank_benchmark["strict_rank_improvement"],
                "rerank_candidate_pool_bounded": first_rerank_benchmark["candidate_pool_bounded"],
                "rerank_provenance_preserved": first_rerank_benchmark["provenance_preserved"],
                "rerank_disabled_exact_fallback": True,
                "rerank_invalid_response_safe": True,
                "rerank_provider_failure_safe": True,
                "rerank_provider_down_safe": True,
            },
            "cross_project_isolation": True,
            "persistence": {
                "redis_restart": True,
                "api_restart": True,
                "semantic_current_after_restart": True,
                "rerank_configured_after_restart": True,
            },
            "fallback": {
                "provider_failure": provider_fallback["state"],
                "semantic_only_provider_failure_status": 503,
                "stale_after_lexical_change": stale_hybrid["state"],
            },
            "semantic_integrity": {
                "migration": SCHEMA_REVISION,
                "actual_pgvector_type": vector_type,
                "project_scoped": True,
                "current_only_after_complete_run": True,
                "unchanged_sync_reused_embeddings": True,
                "provider_requests_on_reuse": 0,
                "profile_dimensions": semantic_state["profile"]["dimensions"],
            },
            "lexical_extended": lexical_extended,
            "retrieval_integrity": {
                "head_race_rejected": True,
                "inventory_race_rejected": True,
                "prior_corpus_preserved": True,
                "duplicate_task_candidate_collapsed": True,
                "task_provenance_preserved": True,
                "cross_project_duplicate_isolation": True,
                "semantic_challenge_recovered": True,
                "hybrid_fallback_provider_error": True,
                "hybrid_fallback_stale": True,
                "semantic_project_isolation": True,
                "rerank_recall_at_5_gte_hybrid": first_rerank_benchmark["recall_at_5_gte_hybrid"],
                "rerank_mrr_gte_hybrid": first_rerank_benchmark["mrr_gte_hybrid"],
                "rerank_strict_rank_improvement": first_rerank_benchmark["strict_rank_improvement"],
                "rerank_candidate_pool_bounded": first_rerank_benchmark["candidate_pool_bounded"],
                "rerank_provenance_preserved": first_rerank_benchmark["provenance_preserved"],
                "rerank_disabled_exact_fallback": True,
                "rerank_invalid_response_safe": True,
                "rerank_provider_failure_safe": True,
                "rerank_provider_down_safe": True,
            },
        }
        BENCHMARK_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        BENCHMARK_OUTPUT.write_text(
            json.dumps(benchmark_result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(benchmark_result, indent=2, sort_keys=True))
        print(
            "retrieval_integrity="
            + json.dumps(benchmark_result["retrieval_integrity"], sort_keys=True)
        )
        print("Retrieval Corpus/Lexical/Semantic/Hybrid/Rerank integration passed.")
        return 0
    except Exception:
        logs = compose(project_name, ["logs", "--no-color"], env=environment, check=False)
        print(logs.stdout, flush=True)
        print(logs.stderr, flush=True)
        raise
    finally:
        compose(project_name, ["down", "--remove-orphans"], env=environment, check=False)
        fixture_process.terminate()
        fixture_process.wait(timeout=10)
        rerank_fixture_process.terminate()
        rerank_fixture_process.wait(timeout=10)
        cleanup_temporary_root(temporary_root, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
