from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def safe_roots(data_root: Path, projects_root: Path) -> tuple[Path, Path]:
    data = data_root.expanduser().resolve()
    projects = projects_root.expanduser().resolve()
    if data == projects or data in projects.parents or projects in data.parents:
        raise ValueError("HIVE_DATA_ROOT and HIVE_PROJECTS_ROOT must be separate, non-nested roots")
    if data.parent == data or projects.parent == projects:
        raise ValueError("HIVE roots may not be filesystem roots")
    return data, projects


def run_capture(command: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            check=False,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"command_unavailable:{type(exc).__name__}") from exc
    return result


def compose_configuration() -> dict[str, Any]:
    result = run_capture(["docker", "compose", "config", "--format", "json"], timeout=30)
    if result.returncode != 0:
        raise RuntimeError("compose_configuration_failed")
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("compose_configuration_unreadable") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("services"), dict):
        raise RuntimeError("compose_configuration_missing_services")
    return payload


def _mount_source(service: object, target: str) -> Path:
    if not isinstance(service, dict) or not isinstance(service.get("volumes"), list):
        raise RuntimeError("compose_mounts_unavailable")
    for volume in service["volumes"]:
        if isinstance(volume, dict) and volume.get("target") == target:
            source = volume.get("source")
            if isinstance(source, str) and source:
                return Path(source).expanduser().resolve()
    raise RuntimeError("compose_mount_source_missing")


def configured_roots(configuration: dict[str, Any]) -> tuple[Path, Path]:
    services = configuration["services"]
    data_api = _mount_source(services.get("api"), "/var/lib/hive")
    data_postgres = _mount_source(services.get("postgres"), "/var/lib/postgresql/data")
    if data_postgres != data_api / "postgres":
        raise ValueError("PostgreSQL data mount is not the expected child of HIVE_DATA_ROOT")
    projects = _mount_source(services.get("api"), "/workspace/projects")
    return safe_roots(data_api, projects)


def doctor_report() -> dict[str, object]:
    docker = shutil.which("docker")
    if docker is None:
        return {"status": "BLOCKED", "docker_cli": "MISSING", "compose_config": "NOT_RUN"}
    info = run_capture([docker, "info", "--format", "{{.ServerVersion}}"], timeout=20)
    if info.returncode != 0:
        return {"status": "BLOCKED", "docker_cli": "AVAILABLE", "docker_daemon": "UNAVAILABLE"}
    try:
        configuration = compose_configuration()
        data_root, projects_root = configured_roots(configuration)
    except (RuntimeError, ValueError) as exc:
        return {
            "status": "BLOCKED",
            "docker_cli": "AVAILABLE",
            "docker_daemon": "AVAILABLE",
            "compose_config": "INVALID",
            "diagnostic_code": str(exc),
        }
    return {
        "status": "READY",
        "docker_cli": "AVAILABLE",
        "docker_daemon": "AVAILABLE",
        "docker_server_version": info.stdout.decode("utf-8", errors="replace").strip(),
        "compose_config": "VALID",
        "env_file": "PRESENT" if (ROOT / ".env").is_file() else "MISSING",
        "data_root": str(data_root),
        "data_root_exists": data_root.exists(),
        "projects_root": str(projects_root),
        "projects_root_exists": projects_root.exists(),
        "roots_separate": True,
        "auto_discovery": os.environ.get("HIVE_AUTO_DISCOVERY_ENABLED", "true").lower()
        in {"1", "true", "yes", "on"},
        "secrets_emitted": False,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_upgrade_backup(
    configuration: dict[str, Any], data_root: Path, projects_root: Path, destination: Path
) -> dict[str, object]:
    backup = destination.expanduser().resolve()
    if backup.exists():
        raise ValueError("backup destination already exists; choose a new empty path")
    if any(
        root == backup or root in backup.parents or backup in root.parents
        for root in (data_root, projects_root, ROOT)
    ):
        raise ValueError("backup destination must be separate from HIVE roots and the checkout")
    postgres_status = run_capture(
        ["docker", "compose", "ps", "--status", "running", "-q", "postgres"], timeout=20
    )
    if postgres_status.returncode != 0 or not postgres_status.stdout.strip():
        raise RuntimeError("upgrade_backup_requires_running_postgres")
    services = configuration["services"]
    postgres = services.get("postgres")
    environment = postgres.get("environment", {}) if isinstance(postgres, dict) else {}
    if not isinstance(environment, dict):
        raise RuntimeError("postgres_configuration_unavailable")
    user = str(environment.get("POSTGRES_USER", "hive"))
    database = str(environment.get("POSTGRES_DB", "hive"))
    backup.mkdir(parents=True)
    dump_path = backup / "postgres.dump"
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres",
        "pg_dump",
        "--format=custom",
        "--username",
        user,
        database,
    ]
    try:
        with dump_path.open("xb") as output:
            dump_result = subprocess.run(
                command,
                cwd=ROOT,
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
                timeout=300,
                shell=False,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"postgres_logical_backup_failed:{type(exc).__name__}") from exc
    with dump_path.open("rb") as dump_file:
        valid_dump_header = dump_file.read(5) == b"PGDMP"
    if dump_result.returncode != 0 or not valid_dump_header:
        raise RuntimeError("postgres_logical_backup_failed")
    cas_source = (data_root / "cas").resolve()
    cas_files = 0
    cas_bytes = 0
    cas_destination = backup / "cas"
    if cas_source.is_dir():
        if cas_source.is_symlink() or data_root not in cas_source.parents:
            raise ValueError("CAS source failed the HIVE_DATA_ROOT boundary check")
        if any(
            item.is_symlink() or bool(getattr(item, "is_junction", lambda: False)())
            for item in cas_source.rglob("*")
        ):
            raise ValueError("CAS backup refused a symbolic link or junction")
        shutil.copytree(cas_source, cas_destination, symlinks=False)
        for item in cas_destination.rglob("*"):
            if item.is_file():
                cas_files += 1
                cas_bytes += item.stat().st_size
    manifest: dict[str, object] = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "postgres_dump_sha256": _sha256(dump_path),
        "postgres_dump_bytes": dump_path.stat().st_size,
        "cas_files": cas_files,
        "cas_bytes": cas_bytes,
        "redis_backed_up": False,
        "configuration_secrets_copied": False,
    }
    (backup / "backup-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _copy_env_example_if_missing() -> str:
    env_path = ROOT / ".env"
    if env_path.exists():
        return "PRESERVED"
    example = ROOT / ".env.example"
    if not example.is_file():
        raise RuntimeError("env_example_missing")
    with example.open("rb") as source, env_path.open("xb") as destination:
        shutil.copyfileobj(source, destination)
    return "CREATED_FROM_EXAMPLE"


def _compose_up() -> None:
    result = run_capture(["docker", "compose", "up", "-d", "--build"], timeout=1_800)
    if result.returncode != 0:
        raise RuntimeError("compose_up_failed; persistent data and backup were preserved")


def wait_for_api_health() -> bool:
    port = os.environ.get("HIVE_API_PORT", "8000")
    url = f"http://127.0.0.1:{port}/api/v1/health"
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if response.status == 200 and payload.get("status") == "ok":
                return True
        except (OSError, ValueError):
            pass
        time.sleep(2)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="HIVE local Compose install, upgrade and doctor")
    parser.add_argument("command", choices=("doctor", "install", "upgrade"))
    parser.add_argument(
        "--yes", action="store_true", help="confirm the requested local Compose operation"
    )
    parser.add_argument(
        "--backup-dir", type=Path, help="new, empty destination for a verified upgrade backup"
    )
    args = parser.parse_args()

    if args.command == "doctor":
        doctor = doctor_report()
        print(json.dumps(doctor, indent=2, sort_keys=True), flush=True)
        return 0 if doctor["status"] == "READY" else 1
    if not args.yes:
        print(
            "Install/upgrade changes local Compose services; pass --yes to proceed.",
            file=sys.stderr,
        )
        return 2

    try:
        if args.command == "upgrade" and not (ROOT / ".env").is_file():
            raise ValueError(
                "upgrade requires the existing .env so the data-root identity is explicit"
            )
        configuration = compose_configuration()
        data_root, projects_root = configured_roots(configuration)
        report: dict[str, object] = {
            "command": args.command,
            "data_root": str(data_root),
            "projects_root": str(projects_root),
            "secrets_emitted": False,
        }
        if args.command == "install":
            if data_root.exists() and any(data_root.iterdir()):
                raise ValueError(
                    "install refused: HIVE_DATA_ROOT is not empty; use upgrade with a backup"
                )
            env_state = _copy_env_example_if_missing()
            if env_state == "CREATED_FROM_EXAMPLE":
                configuration = compose_configuration()
                data_root, projects_root = configured_roots(configuration)
                if data_root.exists() and any(data_root.iterdir()):
                    raise ValueError("install refused: expanded HIVE_DATA_ROOT is not empty")
            report["env_file"] = env_state
        else:
            report["env_file"] = "PRESERVED"
            if args.backup_dir is None:
                raise ValueError("upgrade requires --backup-dir")
            report["backup"] = create_upgrade_backup(
                configuration, data_root, projects_root, args.backup_dir
            )
            report["backup_path"] = str(args.backup_dir.expanduser().resolve())
        _compose_up()
        report["compose_up"] = "PASS"
        report["api_health"] = "PASS" if wait_for_api_health() else "FAIL"
        report["status"] = "PASS" if report["api_health"] == "PASS" else "BLOCKED"
        print(json.dumps(report, indent=2, sort_keys=True), flush=True)
        return 0 if report["status"] == "PASS" else 1
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "command": args.command,
                    "status": "BLOCKED",
                    "diagnostic_code": str(exc),
                    "persistent_data_deleted": False,
                    "secrets_emitted": False,
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
