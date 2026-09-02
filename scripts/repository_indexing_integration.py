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

SCHEMA_REVISION = "0004_retrieval_lexical"


def postgres_sql(project_name: str, environment: dict[str, str], query: str, *, check: bool = True):
    return compose(
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
            "-v",
            "ON_ERROR_STOP=1",
            "-Atqc",
            query,
        ],
        env=environment,
        check=check,
    )


def scalar(project_name: str, environment: dict[str, str], query: str) -> str:
    return postgres_sql(project_name, environment, query).stdout.strip()


def assert_database_failure(
    project_name: str, environment: dict[str, str], query: str, label: str
) -> None:
    result = postgres_sql(project_name, environment, query, check=False)
    if result.returncode == 0:
        raise AssertionError(f"{label}: SQL unexpectedly succeeded")
    if "foreign key constraint" not in result.stderr.lower():
        raise AssertionError(f"{label}: SQL failed without foreign-key evidence: {result.stderr}")


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
    second_repository = projects_root / "isolated"
    second_repository.mkdir()
    run(["git", "init", "-b", "main", str(second_repository)], env=environment)
    run(
        [
            "git",
            "-C",
            str(second_repository),
            "config",
            "user.email",
            "hive-test@example.invalid",
        ],
        env=environment,
    )
    run(
        [
            "git",
            "-C",
            str(second_repository),
            "config",
            "user.name",
            "HIVE Integration Test",
        ],
        env=environment,
    )
    (second_repository / "pyproject.toml").write_text(
        "[project]\nname = 'isolated'\n", encoding="utf-8"
    )
    (second_repository / "worker.py").write_text(
        "class Secondary:\n    def worker(self):\n        return 3\n",
        encoding="utf-8",
    )
    commit(second_repository, "initial isolated repository", environment)
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

        status, second_project = request(
            base_url,
            "POST",
            "/api/v1/projects",
            {"name": "Indexed Isolated", "relative_path": "isolated"},
        )
        assert_equal(status, 201, "isolated project registration")
        assert isinstance(second_project, dict)
        second_project_id = str(second_project["project_id"])
        if second_project_id == project_id:
            raise AssertionError("isolated project reused the first project ID")

        status, first = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
        assert_equal(status, 200, "first index HTTP status")
        assert isinstance(first, dict)
        assert_equal(first["status"], "COMPLETED", "first index state")
        assert_equal(first["project_id"], project_id, "first index project scope")
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

        status, second_first = request(
            base_url, "POST", f"/api/v1/projects/{second_project_id}/index"
        )
        assert_equal(status, 200, "isolated first index HTTP status")
        assert isinstance(second_first, dict)
        assert_equal(second_first["status"], "COMPLETED", "isolated first index state")
        assert_equal(second_first["project_id"], second_project_id, "isolated index project scope")
        assert_equal(second_first["added_file_count"], 2, "isolated added files")
        assert_equal(second_first["indexed_file_count"], 2, "isolated indexed files")
        assert_equal(second_first["parsed_file_count"], 1, "isolated parsed files")
        assert_equal(second_first["symbol_count"], 2, "isolated symbol count")
        assert_equal(
            scalar(
                project_name,
                environment,
                "SELECT string_agg(qualified_name, ',' ORDER BY qualified_name) "
                f"FROM repository_symbols WHERE project_id = '{second_project_id}'",
            ),
            "Secondary,Secondary.worker",
            "isolated symbols",
        )
        assert_equal(
            scalar(
                project_name,
                environment,
                "SELECT count(*) FROM repository_files "
                f"WHERE project_id = '{project_id}' AND is_current",
            ),
            "2",
            "first project current files",
        )
        assert_equal(
            scalar(
                project_name,
                environment,
                "SELECT count(*) FROM repository_files "
                f"WHERE project_id = '{second_project_id}' AND is_current",
            ),
            "2",
            "isolated project current files",
        )
        assert_equal(
            scalar(
                project_name,
                environment,
                "SELECT count(*) FROM repository_files "
                f"WHERE project_id = '{project_id}' "
                "AND path = 'worker.py' AND is_current",
            ),
            "0",
            "first project has no isolated file",
        )
        assert_equal(
            scalar(
                project_name,
                environment,
                "SELECT count(*) FROM repository_files "
                f"WHERE project_id = '{second_project_id}' "
                "AND path = 'app.py' AND is_current",
            ),
            "0",
            "isolated project has no first file",
        )
        assert_equal(
            scalar(
                project_name,
                environment,
                "SELECT count(*) FROM repository_symbols "
                f"WHERE project_id = '{project_id}' "
                "AND qualified_name LIKE 'Secondary%'",
            ),
            "0",
            "first project has no isolated symbols",
        )
        assert_equal(
            scalar(
                project_name,
                environment,
                "SELECT count(*) FROM repository_symbols "
                f"WHERE project_id = '{second_project_id}' "
                "AND qualified_name LIKE 'Initial%'",
            ),
            "0",
            "isolated project has no first symbols",
        )

        status, first_latest = request(
            base_url, "GET", f"/api/v1/projects/{project_id}/index/status"
        )
        assert_equal(status, 200, "first latest index status HTTP status")
        assert isinstance(first_latest, dict)
        assert_equal(first_latest["run_id"], first["run_id"], "first latest run identity")
        assert_equal(first_latest["project_id"], project_id, "first latest project scope")
        status, second_latest = request(
            base_url, "GET", f"/api/v1/projects/{second_project_id}/index/status"
        )
        assert_equal(status, 200, "isolated latest index status HTTP status")
        assert isinstance(second_latest, dict)
        assert_equal(
            second_latest["run_id"], second_first["run_id"], "isolated latest run identity"
        )
        assert_equal(
            second_latest["project_id"], second_project_id, "isolated latest project scope"
        )

        first_run_id = str(first["run_id"])
        second_run_id = str(second_first["run_id"])
        assert_equal(
            scalar(
                project_name,
                environment,
                "SELECT project_id::text FROM repository_index_runs "
                f"WHERE run_id = '{first_run_id}'",
            ),
            project_id,
            "first run project ownership",
        )
        assert_equal(
            scalar(
                project_name,
                environment,
                "SELECT project_id::text FROM repository_index_runs "
                f"WHERE run_id = '{second_run_id}'",
            ),
            second_project_id,
            "isolated run project ownership",
        )
        first_file_id = scalar(
            project_name,
            environment,
            "SELECT file_id::text FROM repository_files "
            f"WHERE project_id = '{project_id}' "
            "AND path = 'app.py' AND is_current",
        )
        second_file_id = scalar(
            project_name,
            environment,
            "SELECT file_id::text FROM repository_files "
            f"WHERE project_id = '{second_project_id}' "
            "AND path = 'worker.py' AND is_current",
        )
        first_symbol_id = scalar(
            project_name,
            environment,
            "SELECT symbol_id::text FROM repository_symbols "
            f"WHERE project_id = '{project_id}' "
            f"AND file_id = '{first_file_id}' "
            "ORDER BY symbol_id LIMIT 1",
        )
        for identifier, label in (
            (first_run_id, "first run"),
            (second_run_id, "isolated run"),
            (first_file_id, "first file"),
            (second_file_id, "isolated file"),
            (first_symbol_id, "first symbol"),
        ):
            if not identifier:
                raise AssertionError(f"{label} identifier was not returned by PostgreSQL")

        assert_database_failure(
            project_name,
            environment,
            (
                "UPDATE repository_files "
                f"SET last_seen_run_id = '{second_run_id}' "
                f"WHERE project_id = '{project_id}' "
                f"AND file_id = '{first_file_id}';"
            ),
            "cross-project repository file run FK",
        )
        assert_equal(
            scalar(
                project_name,
                environment,
                "SELECT count(*) FROM repository_files "
                f"WHERE project_id = '{project_id}' "
                f"AND file_id = '{first_file_id}' "
                f"AND last_seen_run_id = '{second_run_id}'",
            ),
            "0",
            "invalid cross-project repository file relationship absent",
        )
        assert_database_failure(
            project_name,
            environment,
            (
                "UPDATE repository_symbols "
                f"SET file_id = '{second_file_id}' "
                f"WHERE project_id = '{project_id}' "
                f"AND symbol_id = '{first_symbol_id}';"
            ),
            "cross-project repository symbol file FK",
        )
        assert_equal(
            scalar(
                project_name,
                environment,
                "SELECT count(*) FROM repository_symbols "
                f"WHERE project_id = '{project_id}' "
                f"AND symbol_id = '{first_symbol_id}' "
                f"AND file_id = '{second_file_id}'",
            ),
            "0",
            "invalid cross-project repository symbol relationship absent",
        )
        print("project_isolation=passed")
        print("cross_project_fk_rejection=passed")

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
        prior_file_state = scalar(
            project_name,
            environment,
            "SELECT content_sha256 || ':' || is_current::text "
            "FROM repository_files "
            f"WHERE project_id = '{project_id}' AND file_id = '{first_file_id}'",
        )
        prior_symbol_identities = scalar(
            project_name,
            environment,
            "SELECT string_agg("
            "symbol_id::text || ':' || qualified_name || ':' || kind, "
            "',' ORDER BY symbol_id) "
            "FROM repository_symbols "
            f"WHERE project_id = '{project_id}' AND file_id = '{first_file_id}'",
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

        (repository / "app.py").write_text(
            "class RollbackCandidate:\n    def changed(self):\n        return 99\n",
            encoding="utf-8",
        )
        rollback_trigger_sql = f"""
DROP TRIGGER IF EXISTS hive_test_fail_repository_file_update ON repository_files;
DROP FUNCTION IF EXISTS hive_test_fail_repository_file_update();
CREATE OR REPLACE FUNCTION hive_test_fail_repository_file_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.project_id = '{project_id}'::uuid
       AND OLD.content_sha256 IS DISTINCT FROM NEW.content_sha256 THEN
        RAISE EXCEPTION 'hive integration rollback injection';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER hive_test_fail_repository_file_update
AFTER UPDATE OF content_sha256 ON repository_files
FOR EACH ROW
EXECUTE FUNCTION hive_test_fail_repository_file_update();
"""
        rollback_cleanup_sql = (
            "DROP TRIGGER IF EXISTS hive_test_fail_repository_file_update "
            "ON repository_files; "
            "DROP FUNCTION IF EXISTS hive_test_fail_repository_file_update();"
        )
        try:
            postgres_sql(project_name, environment, rollback_trigger_sql)
            status, rollback_failed = request(
                base_url, "POST", f"/api/v1/projects/{project_id}/index"
            )
            assert_equal(status, 200, "rollback index HTTP status")
            assert isinstance(rollback_failed, dict)
            assert_equal(rollback_failed["status"], "FAILED", "rollback durable run state")
            if not str(rollback_failed["error"]).startswith("database_error_"):
                raise AssertionError(
                    f"rollback did not report a database failure: {rollback_failed}"
                )
            status, rollback_status = request(
                base_url, "GET", f"/api/v1/projects/{project_id}/index/status"
            )
            assert_equal(status, 200, "rollback latest status HTTP status")
            assert isinstance(rollback_status, dict)
            assert_equal(
                rollback_status["run_id"], rollback_failed["run_id"], "rollback run identity"
            )
            assert_equal(rollback_status["status"], "FAILED", "rollback latest durable state")
            assert_equal(
                scalar(
                    project_name,
                    environment,
                    "SELECT content_sha256 || ':' || is_current::text "
                    "FROM repository_files "
                    f"WHERE project_id = '{project_id}' "
                    f"AND file_id = '{first_file_id}'",
                ),
                prior_file_state,
                "previous repository file state preserved after rollback",
            )
            assert_equal(
                scalar(
                    project_name,
                    environment,
                    "SELECT string_agg("
                    "symbol_id::text || ':' || qualified_name || ':' || kind, "
                    "',' ORDER BY symbol_id) "
                    "FROM repository_symbols "
                    f"WHERE project_id = '{project_id}' "
                    f"AND file_id = '{first_file_id}'",
                ),
                prior_symbol_identities,
                "previous symbol identities preserved after rollback",
            )
        finally:
            cleanup_result = postgres_sql(
                project_name, environment, rollback_cleanup_sql, check=False
            )
            if cleanup_result.returncode != 0:
                raise RuntimeError(
                    "rollback trigger cleanup failed:\n"
                    f"{cleanup_result.stdout}\n{cleanup_result.stderr}"
                )
        print("transaction_rollback=passed")
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
