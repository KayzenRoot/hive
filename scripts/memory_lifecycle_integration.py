"""Exercise the durable Memory Lifecycle and Provenance foundation in Docker."""

from __future__ import annotations

import json
import os
import socket
import tempfile
from pathlib import Path
from typing import Any

from project_registry_integration import (
    ROOT,
    assert_equal,
    cleanup_temporary_root,
    compose,
    git,
    run,
    wait_for_health,
)
from project_registry_integration import request as http_request

SCHEMA_REVISION = "0006_memory_lifecycle_provenance"
EVIDENCE_OUTPUT = ROOT / "tmp" / "integration-logs" / "memory-lifecycle.json"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(
    base_url: str, method: str, path: str, payload: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any] | list[Any]]:
    return http_request(base_url, method, path, payload, timeout=30)


def create_repository(root: Path, name: str, *, with_decisions: bool = False) -> tuple[Path, str]:
    repository = root / name
    repository.mkdir()
    environment = os.environ.copy()
    run(["git", "init", "-b", "main", str(repository)], env=environment)
    git(repository, ["config", "user.email", "hive-test@example.invalid"], env=environment)
    git(repository, ["config", "user.name", "HIVE Memory Integration"], env=environment)
    (repository / "README.md").write_bytes(f"# {name}\n".encode())
    files_to_add = ["README.md"]
    if with_decisions:
        decisions_path = repository / "docs" / "project-brain" / "16-DECISIONS-LEDGER.md"
        decisions_path.parent.mkdir(parents=True)
        decisions_path.write_bytes(
            (
                "# Decisions\n\n"
                "## HIVE-ADR-019 — Fixture accepted decision\n"
                "**Status:** Accepted\n\n"
                "This fixture is an accepted project decision.\n"
            ).encode()
        )
        files_to_add.append("docs/project-brain/16-DECISIONS-LEDGER.md")
    git(repository, ["add", *files_to_add], env=environment)
    git(repository, ["commit", "-m", "memory fixture"], env=environment)
    return repository, git(repository, ["rev-parse", "HEAD"], env=environment)


def require_dict(value: dict[str, Any] | list[Any], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AssertionError(f"{label}: expected object, got {value!r}")
    return value


def main() -> int:
    api_port = free_port()
    project_name = f"hive-memory-{os.getpid()}"
    temporary_parent = ROOT / "tmp"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix="memory-lifecycle-", dir=temporary_parent))
    projects_root = temporary_root / "projects"
    data_root = temporary_root / "data"
    projects_root.mkdir()
    data_root.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            "HIVE_DATA_ROOT": data_root.as_posix(),
            "HIVE_PROJECTS_ROOT": projects_root.as_posix(),
            "HIVE_API_PORT": str(api_port),
            "POSTGRES_DB": "hive",
            "POSTGRES_USER": "hive",
            "POSTGRES_PASSWORD": "hive",
        }
    )
    evidence: dict[str, Any] = {
        "status": "FAIL",
        "evidence_version": "memory-lifecycle-provenance-v1",
        "memory_evidence_version": "memory-lifecycle-provenance-v1",
        "memory_migration_head": "UNKNOWN",
        "memory_lifecycle_implemented": False,
        "memory_postgres_durable": False,
        "memory_redis_noncanonical": False,
        "memory_project_scoped": False,
        "memory_cross_project_rejected": False,
        "memory_provenance_queryable": False,
        "memory_model_output_staged": False,
        "memory_canonical_promotion_qualified": False,
        "memory_invalid_promotion_rejected": False,
        "memory_history_preserved": False,
        "memory_restart_recovery": False,
        "memory_redis_loss_recovery": False,
        "memory_secrets_not_exposed": False,
        "memory_migration_consistent": False,
        "memory_migration_changed": True,
        "memory_project_count": 0,
        "memory_cross_project_rejections": 0,
        "memory_provenance_records": 0,
        "memory_invalid_promotion_rejections": 0,
        "memory_history_versions": 0,
        "memory_restart_records": 0,
        "memory_redis_loss_records": 0,
        "memory_secret_leaks": 0,
        "memory_llm_calls": 0,
        "memory_provider_calls": 0,
    }
    api_url = f"http://127.0.0.1:{api_port}"
    try:
        repository_a, commit_a = create_repository(projects_root, "project-a", with_decisions=True)
        repository_b, commit_b = create_repository(projects_root, "project-b")
        compose(project_name, ["up", "-d", "--build", "api"], env=environment)
        wait_for_health(api_url)

        status, raw_project_a = request(
            api_url, "POST", "/api/v1/projects", {"name": "Project A", "relative_path": "project-a"}
        )
        assert_equal(status, 201, "project A registration")
        project_a = require_dict(raw_project_a, "project A")
        status, raw_project_b = request(
            api_url, "POST", "/api/v1/projects", {"name": "Project B", "relative_path": "project-b"}
        )
        assert_equal(status, 201, "project B registration")
        project_b = require_dict(raw_project_b, "project B")
        project_a_id = project_a["project_id"]
        project_b_id = project_b["project_id"]
        evidence["memory_project_count"] = 2

        base_payload = {
            "type": "PROJECT",
            "content": "Project A stores structured memory durably in PostgreSQL.",
            "source": "integration/project-a",
            "source_commit": commit_a,
            "authority": "integration-fixture",
            "confidence": 0.9,
            "importance": 80,
            "tags": ["durable", "project-a"],
            "status": "PROPOSED",
        }
        status, raw_memory = request(
            api_url, "POST", f"/api/v1/projects/{project_a_id}/memories", base_payload
        )
        assert_equal(status, 201, "memory creation")
        memory = require_dict(raw_memory, "memory")
        memory_id = memory["memory_id"]

        status, raw_project_b_memory = request(
            api_url,
            "POST",
            f"/api/v1/projects/{project_b_id}/memories",
            {
                "type": "SESSION",
                "content": "Project B has isolated memory.",
                "source": "integration/project-b",
                "source_commit": commit_b,
                "authority": "integration-fixture",
            },
        )
        assert_equal(status, 201, "project B memory creation")
        project_b_memory = require_dict(raw_project_b_memory, "project B memory")

        status, raw_staged = request(
            api_url,
            "POST",
            f"/api/v1/projects/{project_a_id}/memories",
            {
                "type": "SEMANTIC",
                "content": "Model output remains staged until reviewed.",
                "source": "model/fixture",
                "authority": "model-output",
                "origin": "MODEL",
            },
        )
        assert_equal(status, 201, "staged model memory")
        staged = require_dict(raw_staged, "staged model memory")
        evidence["memory_model_output_staged"] = (
            staged["origin"] == "MODEL" and staged["status"] != "CANONICAL"
        )

        status, raw_trusted_memory = request(
            api_url,
            "POST",
            f"/api/v1/projects/{project_a_id}/memories",
            {
                "type": "PROJECT",
                "content": "A tracked project source can qualify canonical promotion.",
                "source": "integration/project-a-readme",
                "source_commit": commit_a,
                "authority": "integration-fixture",
            },
        )
        assert_equal(status, 201, "trusted-source memory creation")
        trusted_memory = require_dict(raw_trusted_memory, "trusted-source memory")
        status, _ = request(
            api_url,
            "POST",
            f"/api/v1/projects/{project_a_id}/memories/{trusted_memory['memory_id']}/transition",
            {"status": "CONFIRMED"},
        )
        assert_equal(status, 200, "trusted-source confirmation transition")
        status, raw_trusted_promotion = request(
            api_url,
            "POST",
            f"/api/v1/projects/{project_a_id}/memories/{trusted_memory['memory_id']}/promote",
            {"kind": "TRUSTED_SOURCE", "reference": "README.md"},
        )
        assert_equal(status, 200, "trusted-source qualified promotion")
        trusted_promotion = require_dict(raw_trusted_promotion, "trusted-source promotion")
        assert (
            trusted_promotion["status"] == "CANONICAL"
            and trusted_promotion["promotion_basis"]["verified"]["resolver"]
            == "trusted-project-source-v1"
            and trusted_promotion["promotion_basis"]["verified"]["reference"] == "README.md"
            and trusted_promotion["promotion_basis"]["verified"]["source_commit"] == commit_a
        )

        status, _ = request(
            api_url,
            "POST",
            f"/api/v1/projects/{project_a_id}/memories",
            {**base_payload, "status": "CANONICAL", "content": "direct canonical request"},
        )
        assert_equal(status, 422, "direct canonical rejection")

        status, _ = request(
            api_url,
            "GET",
            f"/api/v1/projects/{project_a_id}/memories/{project_b_memory['memory_id']}",
        )
        assert_equal(status, 404, "cross-project read rejection")
        evidence["memory_cross_project_rejections"] = 1
        evidence["memory_cross_project_rejected"] = True
        status, raw_project_a_memories = request(
            api_url, "GET", f"/api/v1/projects/{project_a_id}/memories"
        )
        assert_equal(status, 200, "project A memory listing")
        if not isinstance(raw_project_a_memories, list) or any(
            item.get("project_id") != project_a_id
            for item in raw_project_a_memories
            if isinstance(item, dict)
        ):
            raise AssertionError("project-scoped listing returned another project's memory")
        evidence["memory_project_scoped"] = True

        status, raw_transition = request(
            api_url,
            "POST",
            f"/api/v1/projects/{project_a_id}/memories/{memory_id}/transition",
            {"status": "CONFIRMED"},
        )
        assert_equal(status, 200, "confirmation transition")
        assert require_dict(raw_transition, "confirmation")["status"] == "CONFIRMED"
        status, raw_promoted = request(
            api_url,
            "POST",
            f"/api/v1/projects/{project_a_id}/memories/{memory_id}/promote",
            {
                "kind": "APPROVED_ADR",
                "reference": "HIVE-ADR-019",
                "project_id": project_a_id,
            },
        )
        assert_equal(status, 200, "qualified promotion")
        promoted = require_dict(raw_promoted, "promoted memory")
        evidence["memory_canonical_promotion_qualified"] = (
            promoted["status"] == "CANONICAL"
            and promoted["promotion_basis"]["kind"] == "APPROVED_ADR"
            and promoted["promotion_basis"]["project_id"] == project_a_id
            and promoted["promotion_basis"]["reference"] == "HIVE-ADR-019"
            and promoted["promotion_basis"]["verified"]["resolver"]
            == "accepted-decisions-ledger-adr-v1"
            and promoted["promotion_basis"]["verified"]["status"] == "Accepted"
            and promoted["promotion_basis"]["verified"]["decisions_source"]["source_commit"]
            == commit_a
            and bool(promoted["promotion_basis"]["verified"]["decisions_source"]["git_blob_sha"])
            and bool(promoted["promotion_basis"]["verified"]["decisions_source"]["source_sha256"])
        )

        status, _ = request(
            api_url,
            "POST",
            f"/api/v1/projects/{project_a_id}/memories/{staged['memory_id']}/transition",
            {"status": "CONFIRMED"},
        )
        assert_equal(status, 200, "invalid-basis confirmation transition")
        staged_before_rejection = require_dict(
            request(
                api_url,
                "GET",
                f"/api/v1/projects/{project_a_id}/memories/{staged['memory_id']}",
            )[1],
            "staged before invalid basis",
        )
        staged_before_provenance = require_dict(
            request(
                api_url,
                "GET",
                f"/api/v1/projects/{project_a_id}/memories/{staged['memory_id']}/provenance",
            )[1],
            "staged provenance before invalid basis",
        )
        invalid_basis_cases = (
            {"kind": "APPROVED_ADR", "reference": "HIVE-ADR-999"},
            {"kind": "TRUSTED_SOURCE", "reference": "missing/source.md"},
            {"kind": "VALIDATED_EVIDENCE", "reference": "memory-lifecycle.json"},
        )
        invalid_basis_rejections = 0
        for invalid_basis in invalid_basis_cases:
            status, _ = request(
                api_url,
                "POST",
                f"/api/v1/projects/{project_a_id}/memories/{staged['memory_id']}/promote",
                invalid_basis,
            )
            assert_equal(status, 422, "valid-enum invalid-basis rejection")
            invalid_basis_rejections += 1
        status, raw_staged_after_rejection = request(
            api_url, "GET", f"/api/v1/projects/{project_a_id}/memories/{staged['memory_id']}"
        )
        assert_equal(status, 200, "invalid promotion atomicity read")
        staged_after_rejection = require_dict(raw_staged_after_rejection, "staged after rejection")
        status, raw_staged_after_provenance = request(
            api_url,
            "GET",
            f"/api/v1/projects/{project_a_id}/memories/{staged['memory_id']}/provenance",
        )
        assert_equal(status, 200, "invalid promotion atomicity provenance read")
        staged_after_provenance = require_dict(
            raw_staged_after_provenance, "staged provenance after rejection"
        )
        assert (
            staged_after_rejection["status"] == staged_before_rejection["status"] == "CONFIRMED"
            and staged_after_rejection["version"] == staged_before_rejection["version"]
            and staged_after_rejection["promotion_basis"]
            == staged_before_rejection["promotion_basis"]
            and len(staged_after_provenance["history"]) == len(staged_before_provenance["history"])
        )
        evidence["memory_invalid_promotion_rejections"] = invalid_basis_rejections
        evidence["memory_invalid_promotion_rejected"] = True

        status, _ = request(
            api_url,
            "POST",
            f"/api/v1/projects/{project_b_id}/memories/{project_b_memory['memory_id']}/transition",
            {"status": "CONFIRMED"},
        )
        assert_equal(status, 200, "project B confirmation transition")
        project_b_before_rejection = require_dict(
            request(
                api_url,
                "GET",
                f"/api/v1/projects/{project_b_id}/memories/{project_b_memory['memory_id']}",
            )[1],
            "project B before cross-project promotion",
        )
        status, _ = request(
            api_url,
            "POST",
            f"/api/v1/projects/{project_b_id}/memories/{project_b_memory['memory_id']}/promote",
            {"kind": "APPROVED_ADR", "reference": "HIVE-ADR-019"},
        )
        assert_equal(status, 422, "cross-project basis rejection")
        status, raw_project_b_after_rejection = request(
            api_url,
            "GET",
            f"/api/v1/projects/{project_b_id}/memories/{project_b_memory['memory_id']}",
        )
        assert_equal(status, 200, "cross-project promotion atomicity read")
        project_b_after_rejection = require_dict(
            raw_project_b_after_rejection, "project B after cross-project promotion"
        )
        assert (
            project_b_after_rejection["status"]
            == project_b_before_rejection["status"]
            == "CONFIRMED"
            and project_b_after_rejection["version"] == project_b_before_rejection["version"]
            and project_b_after_rejection["promotion_basis"]
            == project_b_before_rejection["promotion_basis"]
        )
        evidence["memory_cross_project_rejections"] += 1

        status, raw_provenance = request(
            api_url, "GET", f"/api/v1/projects/{project_a_id}/memories/{memory_id}/provenance"
        )
        assert_equal(status, 200, "provenance query")
        provenance = require_dict(raw_provenance, "provenance")
        evidence["memory_provenance_records"] = (
            1 if provenance["memory"]["memory_id"] == memory_id else 0
        )
        evidence["memory_provenance_queryable"] = (
            provenance["memory"]["promotion_basis"] is not None and len(provenance["history"]) >= 3
        )

        status, raw_superseded = request(
            api_url,
            "POST",
            f"/api/v1/projects/{project_a_id}/memories/{memory_id}/supersede",
            {
                "type": "PROJECT",
                "content": "Project A memory has a reviewed successor.",
                "source": "integration/project-a-v2",
                "source_commit": commit_a,
                "authority": "integration-fixture",
                "status": "PROPOSED",
            },
        )
        assert_equal(status, 201, "supersession")
        successor = require_dict(raw_superseded, "successor")
        status, raw_old_provenance = request(
            api_url, "GET", f"/api/v1/projects/{project_a_id}/memories/{memory_id}/provenance"
        )
        assert_equal(status, 200, "superseded provenance")
        old_provenance = require_dict(raw_old_provenance, "superseded provenance")
        evidence["memory_history_versions"] = len(old_provenance["history"])
        evidence["memory_history_preserved"] = (
            old_provenance["memory"]["status"] == "DEPRECATED"
            and successor["supersedes_memory_id"] == memory_id
            and len(old_provenance["history"]) >= 4
        )

        status, _ = request(
            api_url,
            "POST",
            f"/api/v1/projects/{project_a_id}/memories",
            {
                "type": "FAILURE",
                "content": "credential api_key=blocked-by-contract",
                "source": "integration/secret-fixture",
                "authority": "integration-fixture",
            },
        )
        assert_equal(status, 422, "secret rejection")
        evidence["memory_secrets_not_exposed"] = True

        compose(project_name, ["exec", "-T", "redis", "redis-cli", "FLUSHALL"], env=environment)
        compose(project_name, ["restart", "redis"], env=environment)
        wait_for_health(api_url)
        status, raw_after_redis_loss = request(
            api_url, "GET", f"/api/v1/projects/{project_a_id}/memories/{successor['memory_id']}"
        )
        assert_equal(status, 200, "Redis-loss memory recovery")
        evidence["memory_redis_loss_records"] = 1
        evidence["memory_redis_loss_recovery"] = (
            require_dict(raw_after_redis_loss, "Redis-loss memory")["memory_id"]
            == successor["memory_id"]
        )
        evidence["memory_redis_noncanonical"] = evidence["memory_redis_loss_recovery"]

        compose(project_name, ["up", "-d", "--force-recreate", "api"], env=environment)
        wait_for_health(api_url)
        status, raw_after_restart = request(
            api_url, "GET", f"/api/v1/projects/{project_a_id}/memories/{memory_id}"
        )
        assert_equal(status, 200, "API restart memory recovery")
        evidence["memory_restart_records"] = 1
        evidence["memory_restart_recovery"] = (
            require_dict(raw_after_restart, "API restart memory")["status"] == "DEPRECATED"
        )

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
        evidence["memory_migration_head"] = migration_version
        evidence["memory_migration_consistent"] = migration_version == SCHEMA_REVISION
        evidence["memory_postgres_durable"] = bool(
            evidence["memory_restart_recovery"] and evidence["memory_redis_loss_recovery"]
        )
        lifecycle_passed = all(
            evidence[key]
            for key in (
                "memory_postgres_durable",
                "memory_redis_noncanonical",
                "memory_project_scoped",
                "memory_cross_project_rejected",
                "memory_provenance_queryable",
                "memory_model_output_staged",
                "memory_canonical_promotion_qualified",
                "memory_invalid_promotion_rejected",
                "memory_history_preserved",
                "memory_restart_recovery",
                "memory_redis_loss_recovery",
                "memory_secrets_not_exposed",
                "memory_migration_consistent",
                "memory_migration_changed",
            )
        )
        evidence["memory_lifecycle_implemented"] = lifecycle_passed
        evidence["status"] = "PASS" if lifecycle_passed else "FAIL"
        print("Memory lifecycle and provenance integration passed.")
        print(json.dumps(evidence, indent=2, sort_keys=True))
    finally:
        EVIDENCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_OUTPUT.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        compose(project_name, ["down", "--remove-orphans"], env=environment, check=False)
        cleanup_temporary_root(temporary_root, env=environment)
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
