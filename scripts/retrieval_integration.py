from __future__ import annotations

import json
import os
import socket
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

SCHEMA_REVISION = "0004_retrieval_lexical"
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


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    queries = manifest["queries"]
    temporary_root = Path(tempfile.mkdtemp(prefix="retrieval-", dir=ROOT / "tmp"))
    project_name = f"hive-retrieval-{os.getpid()}"
    api_port = free_port()
    dashboard_port = free_port()
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
    first_head = commit(repository, "initial retrieval fixture", git_environment)

    (isolated / "worker.py").write_text(
        "def unrelated_worker():\n    return 'project-b'\n", encoding="utf-8"
    )
    commit(isolated, "isolated fixture", git_environment)

    try:
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

        first_benchmark = benchmark(base_url, project_id, queries, run_number=1)
        second_benchmark = benchmark(base_url, project_id, queries, run_number=2)
        for result in (first_benchmark, second_benchmark):
            assert_equal(result["critical_context_misses"], [], "critical benchmark misses")
            if result["recall_at_5"] < 0.90:
                raise AssertionError(f"lexical recall@5 below gate: {result}")

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

        compose(project_name, ["restart", "redis"], env=environment)
        compose(project_name, ["restart", "api"], env=environment)
        wait_for_health(base_url)
        status, after_restart = request(
            base_url, "GET", f"/api/v1/projects/{project_id}/retrieval/corpus"
        )
        assert_equal(status, 200, "retrieval status after restart")
        assert isinstance(after_restart, dict)
        assert_equal(after_restart["state"], "CURRENT", "retrieval persistence after restart")

        benchmark_result = {
            "schema_version": 1,
            "fixture": manifest["name"],
            "repository": "KayzenRoot/hive",
            "work_order": "WO-006",
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
            },
            "cross_project_isolation": True,
            "persistence": {"redis_restart": True, "api_restart": True},
            "retrieval_integrity": {
                "head_race_rejected": True,
                "inventory_race_rejected": True,
                "prior_corpus_preserved": True,
                "duplicate_task_candidate_collapsed": True,
                "task_provenance_preserved": True,
                "cross_project_duplicate_isolation": True,
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
        print("Retrieval Corpus/Lexical integration passed.")
        return 0
    except Exception:
        logs = compose(project_name, ["logs", "--no-color"], env=environment, check=False)
        print(logs.stdout, flush=True)
        print(logs.stderr, flush=True)
        raise
    finally:
        compose(project_name, ["down", "--remove-orphans"], env=environment, check=False)
        cleanup_temporary_root(temporary_root, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
