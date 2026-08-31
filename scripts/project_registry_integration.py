from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_REVISION = "0001_create_projects"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run(
    command: list[str], *, env: dict[str, str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def compose(
    project_name: str, arguments: list[str], *, env: dict[str, str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    return run(["docker", "compose", "-p", project_name, *arguments], env=env, check=check)


def git(repo: Path, arguments: list[str], *, env: dict[str, str]) -> str:
    result = run(["git", "-C", str(repo), *arguments], env=env)
    return result.stdout.strip()


def request(
    base_url: str, method: str, path: str, payload: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any] | list[Any]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_object = urllib.request.Request(
        base_url + path,
        data=body,
        headers={"Content-Type": "application/json"} if body else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(request_object, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def wait_for_health(base_url: str) -> dict[str, Any]:
    last_error = "unknown"
    for _ in range(60):
        try:
            status, payload = request(base_url, "GET", "/api/v1/health")
            if status == 200 and isinstance(payload, dict) and payload.get("status") == "ok":
                return payload
            last_error = f"status={status} payload={payload}"
        except (OSError, ValueError) as exc:
            last_error = repr(exc)
        time.sleep(1)
    raise RuntimeError(f"health did not become ready: {last_error}")


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def cleanup_temporary_root(temporary_root: Path, *, env: dict[str, str]) -> None:
    """Remove container-owned files from the isolated fixture before host cleanup."""
    if not temporary_root.exists():
        return
    cleanup = run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "0:0",
            "--mount",
            f"type=bind,source={temporary_root.resolve()},target=/cleanup",
            "redis:7.4.2-alpine",
            "find",
            "/cleanup",
            "-mindepth",
            "1",
            "-maxdepth",
            "1",
            "-exec",
            "rm",
            "-rf",
            "--",
            "{}",
            "+",
        ],
        env=env,
        check=False,
    )
    if cleanup.returncode != 0:
        raise RuntimeError(
            f"container fixture cleanup failed ({cleanup.returncode}):\n"
            f"{cleanup.stdout}\n{cleanup.stderr}"
        )
    shutil.rmtree(temporary_root)


def main() -> int:
    api_port = free_port()
    dashboard_port = free_port()
    project_name = f"hive-registry-{os.getpid()}"
    temporary_parent = ROOT / "tmp"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "HIVE_DATA_ROOT": "",
            "HIVE_PROJECTS_ROOT": "",
            "HIVE_API_PORT": str(api_port),
            "HIVE_DASHBOARD_PORT": str(dashboard_port),
            "POSTGRES_DB": "hive",
            "POSTGRES_USER": "hive",
            "POSTGRES_PASSWORD": "hive",
        }
    )

    temporary_root = Path(tempfile.mkdtemp(prefix="project-registry-", dir=temporary_parent))
    try:
        temporary_path = temporary_root
        projects_root = temporary_path / "projects"
        data_root = temporary_path / "data"
        projects_root.mkdir()
        data_root.mkdir()
        environment["HIVE_PROJECTS_ROOT"] = projects_root.as_posix()
        environment["HIVE_DATA_ROOT"] = data_root.as_posix()
        repository = projects_root / "sample-python"
        repository.mkdir()
        git_environment = environment.copy()

        run(["git", "init", "-b", "main", str(repository)], env=git_environment)
        git(repository, ["config", "user.email", "hive-test@example.invalid"], env=git_environment)
        git(repository, ["config", "user.name", "HIVE Integration Test"], env=git_environment)
        (repository / "pyproject.toml").write_text(
            "[project]\nname = 'sample-python'\nversion = '0.1.0'\n", encoding="utf-8"
        )
        (repository / "app.py").write_text("print('first')\n", encoding="utf-8")
        git(repository, ["add", "pyproject.toml", "app.py"], env=git_environment)
        git(repository, ["commit", "-m", "initial sample"], env=git_environment)
        first_head = git(repository, ["rev-parse", "HEAD"], env=git_environment)
        alias = projects_root / "sample-alias"
        try:
            alias.symlink_to(repository.name, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            raise RuntimeError(f"canonical alias test requires symlink support: {exc}") from exc

        transition_repository = projects_root / "transition-project"
        transition_repository.mkdir()
        run(["git", "init", "-b", "main", str(transition_repository)], env=git_environment)
        git(
            transition_repository,
            ["config", "user.email", "hive-test@example.invalid"],
            env=git_environment,
        )
        git(
            transition_repository,
            ["config", "user.name", "HIVE Integration Test"],
            env=git_environment,
        )
        (transition_repository / "app.py").write_text("print('transition')\n", encoding="utf-8")
        git(transition_repository, ["add", "app.py"], env=git_environment)
        git(transition_repository, ["commit", "-m", "transition sample"], env=git_environment)
        transition_head = git(transition_repository, ["rev-parse", "HEAD"], env=git_environment)
        transition_backup = projects_root / "transition-project-real"
        outside_repository = temporary_path / "outside-project"
        outside_repository.mkdir()
        (outside_repository / "outside-marker.txt").write_text("outside\n", encoding="utf-8")
        loop = projects_root / "symlink-loop"
        try:
            loop.symlink_to(loop.name)
        except (OSError, NotImplementedError) as exc:
            raise RuntimeError(f"resolution-error test requires symlink support: {exc}") from exc

        try:
            try:
                compose(project_name, ["up", "-d", "--build"], env=environment)
            except RuntimeError:
                logs = compose(project_name, ["logs", "--no-color"], env=environment, check=False)
                print(logs.stdout, flush=True)
                raise
            migration_version = compose(
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
            assert_equal(migration_version, SCHEMA_REVISION, "migration revision")

            api_url = f"http://127.0.0.1:{api_port}"
            health = wait_for_health(api_url)
            assert_equal(health["status"], "ok", "health status")

            container_id = compose(
                project_name, ["ps", "-q", "api"], env=environment
            ).stdout.strip()
            inspected = json.loads(
                run(["docker", "inspect", container_id], env=environment).stdout
            )[0]
            mounts = inspected.get("Mounts", [])
            project_mount = next(
                (mount for mount in mounts if mount.get("Destination") == "/workspace/projects"),
                None,
            )
            if not project_mount or project_mount.get("RW") is not False:
                raise AssertionError(f"project root is not read-only: {project_mount}")
            if any(mount.get("Destination") == "/var/run/docker.sock" for mount in mounts):
                raise AssertionError("Docker socket is exposed to the API")

            status, registered = request(
                api_url,
                "POST",
                "/api/v1/projects",
                {"name": "Sample Python", "relative_path": "sample-python"},
            )
            assert_equal(status, 201, "registration status")
            assert isinstance(registered, dict)
            project_id = registered["project_id"]
            assert_equal(registered["name"], "Sample Python", "registered name")
            assert_equal(registered["relative_path"], "sample-python", "registered path")
            assert_equal(registered["git_branch"], "main", "registered branch")
            assert_equal(registered["git_head_sha"], first_head, "registered HEAD")
            assert_equal(registered["state"], "READY", "registered state")
            if "python" not in registered["language_stack"]:
                raise AssertionError(f"Python was not detected: {registered['language_stack']}")

            status, alias_duplicate = request(
                api_url,
                "POST",
                "/api/v1/projects",
                {"name": "Sample Alias", "relative_path": "sample-alias"},
            )
            assert_equal(status, 409, "canonical alias duplicate status")
            assert isinstance(alias_duplicate, dict)
            canonical_count = compose(
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
                    "SELECT count(*) FROM projects WHERE relative_path = 'sample-python'",
                ],
                env=environment,
            ).stdout.strip()
            assert_equal(canonical_count, "1", "canonical alias database count")

            status, loop_error = request(
                api_url,
                "POST",
                "/api/v1/projects",
                {"name": "Loop", "relative_path": "symlink-loop"},
            )
            assert_equal(status, 400, "symlink loop status")
            assert isinstance(loop_error, dict)

            status, listed = request(api_url, "GET", "/api/v1/projects")
            assert_equal(status, 200, "list status")
            assert isinstance(listed, list)
            assert_equal(len(listed), 1, "registered project count")
            assert_equal(listed[0]["project_id"], project_id, "listed project ID")

            status, fetched = request(api_url, "GET", f"/api/v1/projects/{project_id}")
            assert_equal(status, 200, "fetch status")
            assert isinstance(fetched, dict)
            assert_equal(fetched["git_head_sha"], first_head, "fetched HEAD")

            (repository / "app.py").write_text("print('second')\n", encoding="utf-8")
            git(repository, ["add", "app.py"], env=git_environment)
            git(repository, ["commit", "-m", "second sample"], env=git_environment)
            second_head = git(repository, ["rev-parse", "HEAD"], env=git_environment)
            status, inspected_project = request(
                api_url, "POST", f"/api/v1/projects/{project_id}/inspect"
            )
            assert_equal(status, 200, "re-inspection status")
            assert isinstance(inspected_project, dict)
            assert_equal(inspected_project["git_head_sha"], second_head, "re-inspected HEAD")

            status, duplicate = request(
                api_url,
                "POST",
                "/api/v1/projects",
                {"name": "Duplicate", "relative_path": "sample-python"},
            )
            assert_equal(status, 409, "duplicate status")
            assert isinstance(duplicate, dict)

            status, traversal = request(
                api_url,
                "POST",
                "/api/v1/projects",
                {"name": "Outside", "relative_path": "../outside"},
            )
            assert_equal(status, 400, "traversal status")
            assert isinstance(traversal, dict)

            status, transition = request(
                api_url,
                "POST",
                "/api/v1/projects",
                {"name": "Transition", "relative_path": "transition-project"},
            )
            assert_equal(status, 201, "transition registration status")
            assert isinstance(transition, dict)
            transition_id = transition["project_id"]
            assert_equal(transition["state"], "READY", "transition initial state")
            assert_equal(transition["git_head_sha"], transition_head, "transition initial HEAD")
            ready_inspection_time = parse_timestamp(transition["last_inspected_at"])

            transition_repository.rename(transition_backup)
            try:
                (projects_root / "transition-project").symlink_to(
                    Path("..") / outside_repository.name, target_is_directory=True
                )
                status, blocked = request(
                    api_url, "POST", f"/api/v1/projects/{transition_id}/inspect"
                )
                assert_equal(status, 200, "unsafe transition inspection status")
                assert isinstance(blocked, dict)
                assert_equal(blocked["state"], "BLOCKED", "unsafe transition state")
                assert_equal(
                    blocked["inspection_error"],
                    "path_boundary_violation",
                    "unsafe transition error",
                )
                assert blocked["git_head_sha"] is None
                assert blocked["git_branch"] is None
                assert blocked["repository_accessible"] is False
                assert parse_timestamp(blocked["last_inspected_at"]) > ready_inspection_time

                status, blocked_get = request(api_url, "GET", f"/api/v1/projects/{transition_id}")
                assert_equal(status, 200, "blocked persisted fetch status")
                assert isinstance(blocked_get, dict)
                assert_equal(blocked_get["state"], "BLOCKED", "blocked persisted state")
                assert_equal(
                    blocked_get["inspection_error"],
                    "path_boundary_violation",
                    "blocked persisted error",
                )
            finally:
                outside_route = projects_root / "transition-project"
                if outside_route.is_symlink():
                    outside_route.unlink()
                transition_backup.rename(outside_route)

            status, recovered = request(
                api_url, "POST", f"/api/v1/projects/{transition_id}/inspect"
            )
            assert_equal(status, 200, "transition recovery status")
            assert isinstance(recovered, dict)
            assert_equal(recovered["state"], "READY", "transition recovery state")
            assert_equal(recovered["relative_path"], "transition-project", "recovered identity")
            assert_equal(recovered["git_head_sha"], transition_head, "recovered HEAD")

            status, after_recovery_list = request(api_url, "GET", "/api/v1/projects")
            assert_equal(status, 200, "post-recovery list status")
            assert isinstance(after_recovery_list, list)
            assert_equal(len(after_recovery_list), 2, "post-recovery project count")

            compose(project_name, ["exec", "-T", "redis", "redis-cli", "FLUSHALL"], env=environment)
            compose(project_name, ["restart", "redis"], env=environment)
            wait_for_health(api_url)
            status, after_redis_loss = request(api_url, "GET", f"/api/v1/projects/{project_id}")
            assert_equal(status, 200, "post-Redis-loss fetch status")
            assert isinstance(after_redis_loss, dict)
            assert_equal(after_redis_loss["git_head_sha"], second_head, "post-Redis-loss HEAD")

            compose(
                project_name,
                ["up", "-d", "--force-recreate", "api"],
                env=environment,
            )
            wait_for_health(api_url)
            status, after_api_restart = request(api_url, "GET", f"/api/v1/projects/{project_id}")
            assert_equal(status, 200, "post-API-restart fetch status")
            assert isinstance(after_api_restart, dict)
            assert_equal(after_api_restart["git_head_sha"], second_head, "post-API-restart HEAD")
            print("Project Registry integration passed.")
            print(f"migration_revision={migration_version}")
            print(f"first_head={first_head}")
            print(f"second_head={second_head}")
            print("canonical_alias_duplicate=passed")
            print("samefile_identity_guard=passed")
            print("unsafe_transition_blocked=passed")
            print("unsafe_transition_persisted=passed")
            print("unsafe_transition_recovery=passed")
            print("symlink_resolution_failure=passed")
            print("redis_loss_persistence=passed")
            print("api_restart_persistence=passed")
            print("read_only_project_mount=passed")
        finally:
            compose(project_name, ["down", "--remove-orphans"], env=environment, check=False)
    finally:
        cleanup_temporary_root(temporary_root, env=environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
