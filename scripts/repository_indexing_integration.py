from __future__ import annotations

import os
import tempfile
from pathlib import Path

from project_registry_integration import (
    ROOT,
    assert_equal,
    cleanup_temporary_root,
    compose,
    request,
    run,
    wait_for_health,
)

SCHEMA_REVISION = "0003_repository_indexing"


def scalar(project_name: str, environment: dict[str, str], query: str) -> str:
    return compose(
        project_name,
        ["exec", "-T", "postgres", "psql", "-U", "hive", "-d", "hive", "-Atqc", query],
        env=environment,
    ).stdout.strip()


def commit(repository: Path, message: str, environment: dict[str, str]) -> None:
    run(["git", "-C", str(repository), "add", "-A"], env=environment)
    run(["git", "-C", str(repository), "commit", "-m", message], env=environment)


def main() -> int:
    temporary_root = Path(tempfile.mkdtemp(prefix="repository-indexing-", dir=ROOT / "tmp"))
    project_name = f"hive-indexing-{os.getpid()}"
    api_port = __import__("socket").socket()
    api_port.bind(("127.0.0.1", 0))
    selected_api_port = int(api_port.getsockname()[1])
    api_port.close()
    dashboard_port = __import__("socket").socket()
    dashboard_port.bind(("127.0.0.1", 0))
    selected_dashboard_port = int(dashboard_port.getsockname()[1])
    dashboard_port.close()
    projects_root = temporary_root / "projects"
    data_root = temporary_root / "data"
    projects_root.mkdir()
    data_root.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            "HIVE_API_PORT": str(selected_api_port),
            "HIVE_DASHBOARD_PORT": str(selected_dashboard_port),
            "HIVE_PROJECTS_ROOT": projects_root.as_posix(),
            "HIVE_DATA_ROOT": data_root.as_posix(),
            "POSTGRES_DB": "hive",
            "POSTGRES_USER": "hive",
            "POSTGRES_PASSWORD": "hive",
        }
    )
    repository = projects_root / "sample"
    repository.mkdir()
    run(["git", "init", "-b", "main", str(repository)], env=environment)
    run(
        ["git", "-C", str(repository), "config", "user.email", "hive-test@example.invalid"],
        env=environment,
    )
    run(
        ["git", "-C", str(repository), "config", "user.name", "HIVE Integration Test"],
        env=environment,
    )
    (repository / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")
    (repository / "app.py").write_text(
        "class Initial:\n    def old(self):\n        return 1\n", encoding="utf-8"
    )
    commit(repository, "initial repository", environment)
    try:
        compose(project_name, ["up", "-d", "--build"], env=environment)
        migration = scalar(project_name, environment, "SELECT version_num FROM alembic_version")
        assert_equal(migration, SCHEMA_REVISION, "repository indexing migration revision")
        base_url = f"http://127.0.0.1:{selected_api_port}"
        wait_for_health(base_url)
        status, project = request(
            base_url,
            "POST",
            "/api/v1/projects",
            {"name": "Indexed Sample", "relative_path": "sample"},
        )
        assert_equal(status, 201, "repository project registration")
        assert isinstance(project, dict)
        project_id = str(project["project_id"])

        status, first = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
        assert_equal(status, 200, "first index HTTP status")
        assert isinstance(first, dict)
        assert_equal(first["status"], "COMPLETED", "first index state")
        assert_equal(first["added_file_count"], 2, "first added files")
        assert_equal(first["indexed_file_count"], 2, "first indexed files")
        assert_equal(first["parsed_file_count"], 1, "first parsed files")
        assert_equal(first["symbol_count"], 2, "first symbol count")
        assert_equal(
            scalar(
                project_name,
                environment,
                f"SELECT string_agg(qualified_name, ',' ORDER BY qualified_name) "
                f"FROM repository_symbols WHERE project_id = '{project_id}'",
            ),
            "Initial,Initial.old",
            "first symbols",
        )

        (repository / "generated.py").write_text("def not_indexed():\n    pass\n", encoding="utf-8")
        status, second = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
        assert_equal(status, 200, "reuse index HTTP status")
        assert isinstance(second, dict)
        assert_equal(second["reused_file_count"], 2, "unchanged file reuse")
        assert_equal(second["indexed_file_count"], 0, "no unnecessary indexing")
        assert_equal(second["parsed_file_count"], 0, "no unnecessary Python parsing")
        # The file above intentionally proves untracked files are excluded.
        # Remove it before later commit(...)->git add -A lifecycle steps so it
        # cannot accidentally become a second added tracked file.
        (repository / "generated.py").unlink()

        (repository / "app.py").write_text(
            "class Updated:\n    async def fresh(self):\n        return 2\n", encoding="utf-8"
        )
        status, changed = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
        assert_equal(status, 200, "changed index HTTP status")
        assert isinstance(changed, dict)
        assert_equal(changed["changed_file_count"], 1, "changed file count")
        assert_equal(changed["parsed_file_count"], 1, "changed parse count")
        assert_equal(
            scalar(
                project_name,
                environment,
                f"SELECT string_agg(qualified_name, ',' ORDER BY qualified_name) "
                f"FROM repository_symbols WHERE project_id = '{project_id}'",
            ),
            "Updated,Updated.fresh",
            "updated symbols",
        )

        (repository / "README.md").write_text("# sample\n", encoding="utf-8")
        commit(repository, "add documentation", environment)
        status, added = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
        assert_equal(status, 200, "added index HTTP status")
        assert isinstance(added, dict)
        assert_equal(added["added_file_count"], 1, "added file count")

        (repository / "README.md").unlink()
        commit(repository, "remove documentation", environment)
        status, removed = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
        assert_equal(status, 200, "removed index HTTP status")
        assert isinstance(removed, dict)
        assert_equal(removed["removed_file_count"], 1, "removed file count")
        assert_equal(
            scalar(
                project_name,
                environment,
                f"SELECT count(*) FROM repository_files "
                f"WHERE project_id = '{project_id}' AND is_current",
            ),
            "2",
            "current file count after removal",
        )

        (repository / "app.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
        status, failed = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
        assert_equal(status, 200, "syntax failure HTTP status")
        assert isinstance(failed, dict)
        assert_equal(failed["status"], "FAILED", "syntax failure state")
        assert_equal(failed["error"], "python_syntax_error", "syntax failure error")
        assert_equal(
            scalar(
                project_name,
                environment,
                f"SELECT string_agg(qualified_name, ',' ORDER BY qualified_name) "
                f"FROM repository_symbols WHERE project_id = '{project_id}'",
            ),
            "Updated,Updated.fresh",
            "prior symbols preserved after syntax failure",
        )

        status, status_payload = request(
            base_url, "GET", f"/api/v1/projects/{project_id}/index/status"
        )
        assert_equal(status, 200, "index status HTTP status")
        assert isinstance(status_payload, dict)
        assert_equal(status_payload["run_id"], failed["run_id"], "latest run status identity")
        compose(project_name, ["restart", "api"], env=environment)
        wait_for_health(base_url)
        status, after_restart = request(base_url, "GET", f"/api/v1/projects/{project_id}/index")
        assert_equal(status, 200, "index status after API restart")
        assert isinstance(after_restart, dict)
        assert_equal(after_restart["status"], "FAILED", "durable failed status after restart")
        print({"migration": migration, "project_id": project_id, "repository_indexing": "passed"})
        print("tracked_only=passed")
        print("incremental_reuse=passed")
        print("added_changed_removed=passed")
        print("python_symbols=passed")
        print("syntax_failure_atomicity=passed")
        print("restart_persistence=passed")
        return 0
    finally:
        compose(project_name, ["down", "--remove-orphans"], env=environment, check=False)
        cleanup_temporary_root(temporary_root, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
