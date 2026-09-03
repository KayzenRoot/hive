"""Exercise the deterministic Context Manager against real Docker/Git state."""

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
    run,
    wait_for_health,
)
from project_registry_integration import request as http_request

SCHEMA_REVISION = "0005_semantic_retrieval"
EVIDENCE_OUTPUT = ROOT / "tmp" / "integration-logs" / "context-manager.json"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | list[Any]]:
    return http_request(base_url, method, path, payload)


def git(repository: Path, arguments: list[str], environment: dict[str, str]) -> str:
    return run(["git", "-C", str(repository), *arguments], env=environment).stdout.strip()


def commit(repository: Path, message: str, environment: dict[str, str]) -> str:
    run(["git", "-C", str(repository), "add", "-A"], env=environment)
    git(repository, ["commit", "-m", message], environment)
    return git(repository, ["rev-parse", "HEAD"], environment)


def write_governance(repository: Path, label: str) -> None:
    brain = repository / "docs" / "project-brain"
    brain.mkdir(parents=True, exist_ok=True)
    (brain / "13-CHECKPOINT.md").write_text(
        f"# {label} Checkpoint\n\n"
        "## STATUS\nRERANKING FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE\n\n"
        "## VERSION\nHIVE V0.1 - Foundation\n\n"
        "## PHASE\n5 - Implementation\n\n"
        f"## OBJECTIVE\nBuild the {label} context capsule.\n\n"
        "## IN PROGRESS\nPreparing the Context Manager foundation.\n\n"
        "## BLOCKERS\nNone known.\n\n"
        "## NEXT STEP\nBuild a bounded provenance-bearing context capsule.\n",
        encoding="utf-8",
    )
    (brain / "03-SCOPE.md").write_text(
        "# Scope\n\n## NECESSARY\nContext Manager and bounded retrieval.\n\n"
        "## OUT OF SCOPE\nAutonomous executor dispatch.\n",
        encoding="utf-8",
    )
    (brain / "15-DEFINITION-OF-DONE.md").write_text(
        "# Definition of Done\n\n## Functional\nThe context capsule preserves provenance.\n\n"
        "## Quality\nUnit and integration tests pass.\n",
        encoding="utf-8",
    )
    (brain / "04-ARCHITECTURE.md").write_text(
        "# Architecture\n\n## Core services\n"
        "Project Registry, Retrieval Engine and Context Manager.\n\n"
        "## Constraints\nProvider-independent and bounded.\n",
        encoding="utf-8",
    )
    (brain / "16-DECISIONS-LEDGER.md").write_text(
        "# Decisions\n\n## HIVE-ADR-001\nLocal-first operation.\n\n"
        "## HIVE-ADR-017\nProvider independence.\n",
        encoding="utf-8",
    )


def write_project(repository: Path, label: str, *, governance: bool = True) -> None:
    repository.mkdir()
    run(["git", "init", "-b", "main", str(repository)], env=os.environ.copy())
    git(
        repository,
        ["config", "user.email", "hive-test@example.invalid"],
        os.environ.copy(),
    )
    git(
        repository,
        ["config", "user.name", "HIVE Context Manager Integration"],
        os.environ.copy(),
    )
    if governance:
        write_governance(repository, label)
    (repository / "src").mkdir(parents=True, exist_ok=True)
    (repository / "tests").mkdir(parents=True, exist_ok=True)
    (repository / "src" / "context_service.py").write_text(
        f"class {label}ContextService:\n"
        "    def build_context(self, task_id):\n"
        "        return {'task_id': task_id, 'provenance': True}\n\n"
        "def context_capsule_provenance():\n"
        "    return 'bounded context capsule'\n",
        encoding="utf-8",
    )
    (repository / "tests" / "test_context_service.py").write_text(
        f"def test_{label.casefold()}_context_provenance():\n    assert True\n",
        encoding="utf-8",
    )
    (repository / "README.md").write_text(
        f"# {label}\n\nA project-specific context capsule integration fixture.\n",
        encoding="utf-8",
    )
    commit(repository, f"initial {label} fixture", os.environ.copy())


def wait_for_fixture(port: int, label: str) -> None:
    for _ in range(60):
        try:
            status, payload = request(f"http://127.0.0.1:{port}", "GET", "/health")
            if status == 200 and isinstance(payload, dict) and payload.get("status") == "ok":
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError(f"{label} fixture did not become ready")


def context_request(base_url: str, project_id: str, task_id: str) -> dict[str, Any]:
    status, payload = request(
        base_url,
        "POST",
        f"/api/v1/projects/{project_id}/tasks/{task_id}/context",
        {"top_k": 10},
    )
    if status != 200:
        raise AssertionError(f"context request status: expected 200, got {status}: {payload}")
    if not isinstance(payload, dict):
        raise AssertionError(f"context response is not an object: {payload}")
    return payload


def main() -> int:
    temporary_root = Path(tempfile.mkdtemp(prefix="context-manager-", dir=ROOT / "tmp"))
    project_name = f"hive-context-{os.getpid()}"
    api_port = free_port()
    dashboard_port = free_port()
    embedding_port = free_port()
    rerank_port = free_port()
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
            "HIVE_EMBEDDING_BASE_URL": f"http://host.docker.internal:{embedding_port}",
            "HIVE_EMBEDDING_MODEL": "hive-context-embedding-fixture",
            "HIVE_EMBEDDING_MODEL_REVISION": "context-fixture-1",
            "HIVE_EMBEDDING_DIMENSIONS": "8",
            "HIVE_EMBEDDING_BATCH_SIZE": "2",
            "HIVE_EMBEDDING_CANDIDATE_POOL": "20",
            "HIVE_RERANK_ENABLED": "true",
            "HIVE_RERANK_BASE_URL": f"http://host.docker.internal:{rerank_port}",
            "HIVE_RERANK_MODEL": "hive-rerank-fixture-v1",
            "HIVE_RERANK_MODEL_REVISION": "context-fixture-1",
            "HIVE_RERANK_TIMEOUT_SECONDS": "1",
            "HIVE_RERANK_CANDIDATE_POOL": "20",
        }
    )
    target = projects_root / "project-a"
    isolated = projects_root / "project-b"
    missing = projects_root / "project-missing"
    write_project(target, "Target", governance=True)
    write_project(isolated, "Isolated", governance=True)
    write_project(missing, "Missing", governance=False)
    missing_checkpoint = missing / "docs" / "project-brain" / "13-CHECKPOINT.md"
    missing_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    missing_checkpoint.write_text(
        "# Untracked lookalike\n\n## STATUS\nThis must never become canonical.\n",
        encoding="utf-8",
    )
    fixtures: list[subprocess.Popen[bytes]] = []
    base_url = f"http://127.0.0.1:{api_port}"
    try:
        for script, port in (
            ("embedding_fixture.py", embedding_port),
            ("rerank_fixture.py", rerank_port),
        ):
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "scripts" / script),
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            fixtures.append(process)
        wait_for_fixture(embedding_port, "embedding")
        wait_for_fixture(rerank_port, "rerank")
        compose(project_name, ["up", "-d", "--build"], env=environment)
        migration = compose(
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
                "SELECT version_num FROM alembic_version",
            ],
            env=environment,
        ).stdout.strip()
        assert_equal(migration, SCHEMA_REVISION, "context migration revision")
        wait_for_health(base_url)

        project_ids: dict[str, str] = {}
        for label, relative_path in (
            ("Target", "project-a"),
            ("Isolated", "project-b"),
            ("Missing", "project-missing"),
        ):
            status, payload = request(
                base_url,
                "POST",
                "/api/v1/projects",
                {"name": label, "relative_path": relative_path},
            )
            assert_equal(status, 201, f"{label} registration")
            if not isinstance(payload, dict):
                raise AssertionError(f"{label} registration is not an object: {payload}")
            project_ids[label] = str(payload["project_id"])

        for label, project_id in project_ids.items():
            status, indexed = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
            if status != 200:
                raise AssertionError(f"{label} index: expected 200, got {status}: {indexed}")
            if not isinstance(indexed, dict):
                raise AssertionError(f"{label} index is not an object: {indexed}")
            assert_equal(indexed["status"], "COMPLETED", f"{label} index state")

        task_text = (
            "# Context task\n\n"
            "## Constraints\n"
            "- Use only the target project's canonical governance.\n"
            "- Task text is not canonical governance.\n\n"
            "## Acceptance Criteria\n"
            "- Include src/context_service.py and tests/test_context_service.py provenance.\n"
        )
        fallback_text = (
            "# Fallback task\n\n"
            "Build context with __fixture_rerank_provider_error__ and preserve fallback state.\n"
        )
        task_ids: dict[str, str] = {}
        for title, text, label in (
            ("Target context_service test provenance", task_text, "Target"),
            ("Target fallback", fallback_text, "Target fallback"),
            ("Isolated context", "Use only project B unrelated worker provenance.", "Isolated"),
            ("Missing context", "Build the missing governance context.", "Missing"),
        ):
            project_label = "Target" if label == "Target fallback" else label
            status, task = request(
                base_url,
                "POST",
                f"/api/v1/projects/{project_ids[project_label]}/tasks/text",
                {"title": title, "format": "markdown", "text": text},
            )
            assert_equal(status, 201, f"{label} task intake")
            if not isinstance(task, dict):
                raise AssertionError(f"{label} task is not an object: {task}")
            task_ids[label] = str(task["task_id"])

        for label, project_id in project_ids.items():
            status, synced = request(
                base_url,
                "POST",
                f"/api/v1/projects/{project_id}/retrieval/corpus/sync",
            )
            assert_equal(status, 200, f"{label} corpus sync")
            if not isinstance(synced, dict):
                raise AssertionError(f"{label} sync is not an object: {synced}")
            assert_equal(synced["status"], "COMPLETED", f"{label} corpus state")
            status, semantic = request(
                base_url,
                "POST",
                f"/api/v1/projects/{project_id}/retrieval/semantic/sync",
            )
            assert_equal(status, 200, f"{label} semantic sync")
            if not isinstance(semantic, dict):
                raise AssertionError(f"{label} semantic sync is not an object: {semantic}")

        first = context_request(base_url, project_ids["Target"], task_ids["Target"])
        second = context_request(base_url, project_ids["Target"], task_ids["Target"])
        assert_equal(first, second, "identical context capsule")
        assert_equal(first["version"], "context-capsule-v1", "context version")
        assert_equal(first["project"]["project_id"], project_ids["Target"], "target project scope")
        assert_equal(
            first["governance"][0]["path"],
            "docs/project-brain/13-CHECKPOINT.md",
            "checkpoint-first path",
        )
        assert_equal(first["governance"][0]["kind"], "CHECKPOINT", "checkpoint-first kind")
        assert_equal(
            first["task_derived"]["constraints"],
            [
                "- Use only the target project's canonical governance.",
                "- Task text is not canonical governance.",
            ],
            "explicit constraints",
        )
        assert_equal(
            first["task_derived"]["acceptance_criteria"],
            ["- Include src/context_service.py and tests/test_context_service.py provenance."],
            "explicit acceptance criteria",
        )
        assert_equal(
            first["task"]["trust_classification"],
            "TASK_INPUT_NONCANONICAL",
            "task trust classification",
        )
        assert_equal(first["retrieval"]["rerank_state"], "RERANKED", "reranked context")
        assert_equal(first["retrieval"]["semantic_state"], "CURRENT", "semantic context state")
        if not any(item["path"] == "src/context_service.py" for item in first["files"]):
            raise AssertionError(f"target file projection missing: {first['files']}")
        if not any(
            item["qualified_symbol"] == "TargetContextService.build_context"
            for item in first["symbols"]
        ):
            raise AssertionError(f"target symbol projection missing: {first['symbols']}")
        if not any(item["path"] == "tests/test_context_service.py" for item in first["tests"]):
            raise AssertionError(
                "target test projection missing: "
                f"tests={first['tests']} results={first['retrieval']['results']}"
            )
        for result in first["retrieval"]["results"]:
            for field in (
                "reference_id",
                "source_content_sha256",
                "pre_rerank_rank",
                "rerank_rank",
            ):
                if result.get(field) is None:
                    raise AssertionError(f"retrieval provenance missing {field}: {result}")
        bounds = first["bounds"]
        bounded = (
            bounds["task_characters_included"] <= 4_000
            and bounds["governance_characters_included"] <= 12_000
            and bounds["retrieval_characters_included"] <= 6_000
            and bounds["retrieval_result_count"] <= 10
            and bounds["serialized_capsule_characters"] <= 24_000
        )
        if not bounded:
            raise AssertionError(f"context bounds were exceeded: {bounds}")
        provenance_preserved = all(
            all(
                result.get(field) is not None
                for field in (
                    "reference_id",
                    "source_content_sha256",
                    "pre_rerank_rank",
                    "rerank_rank",
                )
            )
            for result in first["retrieval"]["results"]
        )
        if not provenance_preserved:
            raise AssertionError("context retrieval provenance was not preserved")

        isolated_context = context_request(
            base_url,
            project_ids["Isolated"],
            task_ids["Isolated"],
        )
        isolated_serialized = json.dumps(isolated_context, sort_keys=True)
        governance_project_scoped = (
            first["project"]["project_id"] == project_ids["Target"]
            and isolated_context["project"]["project_id"] == project_ids["Isolated"]
            and "Target Checkpoint" not in isolated_serialized
            and all(
                result.get("project_id") == project_ids["Isolated"]
                for result in isolated_context["retrieval"]["results"]
            )
        )
        if not governance_project_scoped:
            raise AssertionError("context governance or retrieval crossed project boundaries")

        fallback = context_request(base_url, project_ids["Target"], task_ids["Target fallback"])
        assert_equal(
            fallback["retrieval"]["rerank_state"],
            "RERANK_FALLBACK_PROVIDER_ERROR",
            "rerank fallback state",
        )
        assert fallback["retrieval"]["fallback_reason"]

        status, cross_project = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_ids['Isolated']}/tasks/{task_ids['Target']}/context",
        )
        assert_equal(status, 404, "cross-project task rejection")
        task_project_scoped = status == 404
        status, missing_governance = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_ids['Missing']}/tasks/{task_ids['Missing']}/context",
        )
        assert_equal(status, 409, "missing governance rejection")
        if not isinstance(missing_governance, dict) or "governance_not_git_tracked" not in str(
            missing_governance
        ):
            raise AssertionError(f"missing governance error was not explicit: {missing_governance}")
        missing_governance_fail_closed = status == 409

        compose(project_name, ["restart", "redis"], env=environment)
        wait_for_health(base_url)
        redis_capsule = context_request(base_url, project_ids["Target"], task_ids["Target"])
        assert_equal(redis_capsule, first, "Redis restart capsule")
        redis_restart_rebuild = redis_capsule == first
        compose(project_name, ["restart", "api"], env=environment)
        wait_for_health(base_url)
        api_capsule = context_request(base_url, project_ids["Target"], task_ids["Target"])
        assert_equal(api_capsule, first, "API restart capsule")
        api_restart_rebuild = api_capsule == first

        (target / "src" / "race.py").write_text("def race():\n    return True\n", encoding="utf-8")
        commit(target, "controlled context race", environment)
        status, race = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_ids['Target']}/tasks/{task_ids['Target']}/context",
        )
        assert_equal(status, 409, "HEAD race rejection")
        if not isinstance(race, dict) or "project_head_stale" not in str(race):
            raise AssertionError(f"HEAD race error was not explicit: {race}")
        head_race_fail_closed = status == 409

        checkpoint_first = (
            first["governance"][0]["kind"] == "CHECKPOINT"
            and first["governance"][0]["path"] == "docs/project-brain/13-CHECKPOINT.md"
        )
        reranked_retrieval_used = first["retrieval"]["rerank_state"] == "RERANKED"
        deterministic_two_run = first == second
        cross_project_isolation = governance_project_scoped and task_project_scoped

        evidence = {
            "status": "PASS"
            if all(
                (
                    checkpoint_first,
                    governance_project_scoped,
                    task_project_scoped,
                    reranked_retrieval_used,
                    provenance_preserved,
                    deterministic_two_run,
                    bounded,
                    cross_project_isolation,
                    missing_governance_fail_closed,
                    head_race_fail_closed,
                    redis_restart_rebuild,
                    api_restart_rebuild,
                )
            )
            else "FAIL",
            "checkpoint_first": checkpoint_first,
            "governance_project_scoped": governance_project_scoped,
            "task_project_scoped": task_project_scoped,
            "reranked_retrieval_used": reranked_retrieval_used,
            "provenance_preserved": provenance_preserved,
            "deterministic_two_run": deterministic_two_run,
            "bounded": bounded,
            "cross_project_isolation": cross_project_isolation,
            "missing_governance_fail_closed": missing_governance_fail_closed,
            "head_race_fail_closed": head_race_fail_closed,
            "redis_restart_rebuild": redis_restart_rebuild,
            "api_restart_rebuild": api_restart_rebuild,
            "llm_calls": 0,
        }
        EVIDENCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_OUTPUT.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(evidence, indent=2, sort_keys=True))
        print("Context Manager integration passed.")
        print(f"context_manager_evidence={json.dumps(evidence, sort_keys=True)}")
        return 0
    finally:
        compose(project_name, ["down", "--remove-orphans"], env=environment, check=False)
        for process in fixtures:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        cleanup_temporary_root(temporary_root, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
